"""The brain: rule-based NLU first, local LLM (Ollama) for anything open-ended.

Everything runs on this machine. Ollama is free; if it isn't running the
robot still works with the rule-based parser alone.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from brain import nlu
from brain.nlu import INTENTS, Item, ParsedIntent
from shop.inventory import Inventory

SYSTEM_PROMPT = """You are the brain of a small Indian village kirana (general) store robot.
Customers speak Telugu (script or Latin letters / "Tenglish"), Hindi or English, often mixed.

Store info: {store_info}

Products in the store (key: name, price in rupees per unit, stock):
{products}

Conversation state: {state}
Recent conversation:
{history}

Classify the customer's latest message. Respond ONLY with a JSON object:
{{"intent": one of {intents},
 "items": [{{"name": "<product key from the list>", "qty": <number>}}],
 "customer_name": "<name if the customer said their name, else null>",
 "amount": <money amount in rupees if the customer mentioned paying an amount, else null>,
 "reply_te": "<one short friendly shopkeeper sentence in Telugu script>",
 "reply_en": "<the same reply in English>"}}

Rules: "buy" = wants to take items now. "credit" = wants items written on their khata / will pay later.
"pay_credit" = paying back money they owe. "check_balance" = asking how much they owe. "done" = finished ordering.
"my_name" = only telling their name. Use "chitchat" for small talk and "unknown" if unclear.
Never invent products that are not in the list; put unmatched items with their raw name."""


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen3:4b-instruct", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.available = False
        self.last_latency = 0.0

    def ping(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=3) as resp:
                tags = json.loads(resp.read())
        except (urllib.error.URLError, OSError, ValueError):
            self.available = False
            return False
        names = [m.get("name", "") for m in tags.get("models", [])]
        if self.model not in names and not any(n.startswith(self.model) for n in names):
            fallback = next((n for n in names if "qwen" in n or "llama" in n or "gemma" in n or "phi" in n), names[0] if names else None)
            if fallback:
                print(f"Ollama: model '{self.model}' not found, using '{fallback}' (ollama pull {self.model} to change)")
                self.model = fallback
            else:
                print("Ollama is running but has no models. Run: ollama pull qwen3:4b-instruct")
                self.available = False
                return False
        self.available = True
        return True

    def chat_json(self, system: str, user: str, max_tokens: int = 300) -> dict | None:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": "json",
            "think": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.1, "num_predict": max_tokens},
        }).encode()
        req = urllib.request.Request(f"{self.base_url}/api/chat", data=body, headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
            content = data.get("message", {}).get("content", "")
            self.last_latency = time.time() - t0
            return json.loads(content) if content else None
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            self.last_latency = time.time() - t0
            print(f"Ollama request failed ({exc}); using rule-based understanding")
            return None

    def warm_up(self) -> None:
        if self.available:
            self.chat_json("Reply with JSON {\"ok\": true}", "hi", max_tokens=10)


class Brain:
    def __init__(self, inventory: Inventory, settings=None, use_llm: bool = True, ollama: OllamaClient | None = None):
        self.inventory = inventory
        self.settings = settings
        self.ollama = ollama or OllamaClient(
            getattr(settings, "ollama_url", "http://localhost:11434"),
            getattr(settings, "ollama_model", "qwen3:4b-instruct"),
            getattr(settings, "ollama_timeout", 60.0),
        )
        self.use_llm = use_llm and (getattr(settings, "use_llm", True) if settings else True)
        if self.use_llm:
            if self.ollama.ping():
                print(f"Brain: local LLM ready ({self.ollama.model})")
            else:
                print("Brain: Ollama not reachable (run 'ollama serve'); using rule-based understanding only")

    @property
    def llm_ready(self) -> bool:
        return self.use_llm and self.ollama.available

    # ---- main entry ----
    def understand(self, text: str, history: list[tuple[str, str]] | None = None, state: str = "") -> ParsedIntent:
        parsed = nlu.parse(text, self.inventory)
        if parsed.confidence >= 0.75 or not self.llm_ready:
            return parsed
        llm = self._ask_llm(text, history or [], state)
        if llm is None:
            return parsed
        return self._merge(parsed, llm)

    # ---- LLM ----
    def _products_text(self) -> str:
        return "\n".join(
            f"- {p.key}: {p.name}, {p.price:g} rupees per {p.unit}, stock {p.stock:g}" for p in self.inventory.all()
        )

    def _ask_llm(self, text: str, history: list[tuple[str, str]], state: str) -> dict | None:
        hist = "\n".join(f"{who}: {what}" for who, what in history[-6:]) or "(start of conversation)"
        system = SYSTEM_PROMPT.format(
            products=self._products_text(), state=state or "none", history=hist, intents=json.dumps(sorted(INTENTS)),
            store_info=getattr(self.settings, "store_info", "") or "a small village general store",
        )
        return self.ollama.chat_json(system, text)

    def _merge(self, rules: ParsedIntent, llm: dict) -> ParsedIntent:
        merged = ParsedIntent(
            text=rules.text, intent=rules.intent, items=list(rules.items), customer_name=rules.customer_name,
            amount=rules.amount, confidence=max(rules.confidence, 0.7), source="rules+llm",
        )
        llm_intent = str(llm.get("intent", "unknown")).strip().lower()
        if llm_intent not in INTENTS:
            llm_intent = "unknown"

        known_keys = {i.product.key for i in merged.items}
        for raw in llm.get("items") or []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip()
            if not name:
                continue
            product = self.inventory.get(name) or self.inventory.find(name)
            if product is None:
                merged.unknown_items.append(name)
                continue
            if product.key in known_keys:
                continue  # rules already parsed this item (with a trustworthy quantity)
            try:
                qty = float(raw.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1
            merged.items.append(Item(product=product, qty=max(qty, 0.25)))
            known_keys.add(product.key)

        if rules.intent == "unknown" or (rules.intent == "buy" and rules.confidence < 0.75 and llm_intent not in ("unknown", "chitchat")):
            merged.intent = llm_intent
        if merged.items and merged.intent in ("unknown", "chitchat", "greeting", "my_name"):
            merged.intent = "buy"

        if not merged.customer_name and llm.get("customer_name"):
            name = str(llm["customer_name"]).strip()
            if name and name.lower() not in ("null", "none", "unknown"):
                merged.customer_name = name
        if merged.amount is None and llm.get("amount") not in (None, "", "null"):
            try:
                merged.amount = float(llm["amount"])
            except (TypeError, ValueError):
                pass
        reply_te, reply_en = llm.get("reply_te"), llm.get("reply_en")
        if reply_te or reply_en:
            merged.llm_reply = {"te": reply_te or reply_en, "en": reply_en or reply_te, "hi": reply_en or reply_te}
        return merged


def ask_ai(text: str) -> str:
    """Backwards compatible one-shot helper (used by the very first prototype)."""
    from core.config import load_settings

    settings = load_settings()
    inventory = Inventory(settings.products_file)
    brain = Brain(inventory, settings)
    parsed = brain.understand(text)
    if parsed.llm_reply:
        return parsed.llm_reply.get(settings.language) or parsed.llm_reply["en"]
    return parsed.describe()
