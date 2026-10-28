"""Rule based natural language understanding for Telugu / Tenglish / Hindi / English.

Fast, offline and deterministic. It owns the things a small LLM gets wrong
(quantities, product names, money amounts) and leaves open-ended sentences to
the LLM in ai/brain.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from shop.inventory import Inventory, Product, normalize

INTENTS = {
    "greeting", "goodbye", "thanks", "done", "affirm", "deny",
    "ask_price", "ask_stock", "buy", "remove", "credit", "pay_credit", "check_balance",
    "list_products", "my_name", "chitchat", "unknown",
}


@dataclass
class Item:
    product: Product
    qty: float = 1

    @property
    def line_total(self) -> float:
        return round(self.product.price * self.qty, 2)


@dataclass
class ParsedIntent:
    text: str = ""
    intent: str = "unknown"
    items: list[Item] = field(default_factory=list)
    unknown_items: list[str] = field(default_factory=list)
    customer_name: str | None = None
    amount: float | None = None
    confidence: float = 0.0
    source: str = "rules"
    llm_reply: dict | None = None

    def describe(self) -> str:
        items = ", ".join(f"{i.qty:g} {i.product.key}" for i in self.items)
        bits = [self.intent]
        if items:
            bits.append(items)
        if self.customer_name:
            bits.append(f"name={self.customer_name}")
        if self.amount is not None:
            bits.append(f"amount={self.amount:g}")
        return f"{' | '.join(bits)} ({self.source} {self.confidence:.1f})"


# ---------------------------------------------------------------- keyword tables
KEYWORDS: dict[str, list[str]] = {
    "pay_credit": [
        "kattestanu", "kadutunnanu", "kattestunnanu", "kadathanu", "కట్టేస్తాను", "కడుతున్నాను", "కడతాను",
        "appu teerustunnanu", "teerustunnanu", "తీరుస్తున్నాను", "teerchestanu", "తీర్చేస్తాను",
        "istunnanu", "ఇస్తున్నాను", "pay", "paying", "payment", "jama", "జమ", "जमा", "chukta", "chuka", "clear cheyyi",
        "udhar de raha", "udhaar de raha", "paise de raha", "paisa de raha", "वापस",
    ],
    "check_balance": [
        "balance", "బ్యాలెన్స్", "baaki", "baki", "బాకీ", "khata entha", "ఖాతా ఎంత", "appu entha", "అప్పు ఎంత",
        "entha undi", "ఎంత ఉంది", "entha unnadi", "ఎంత ఉన్నది", "hisab", "hisaab", "హిసాబ్", "lekka", "లెక్క",
        "kitna baaki", "kitna baki", "kitna udhar", "कितना बाकी", "कितना उधार", "how much do i owe", "my account",
    ],
    "credit": [
        "appu", "అప్పు", "khata", "khaata", "ఖాతా", "udhar", "udhaar", "उधार", "credit", "on credit",
        "repu istanu", "రేపు ఇస్తాను", "repu istha", "tarvata istanu", "తర్వాత ఇస్తాను", "later", "baad mein",
        "rasuko", "raasuko", "rasi pettu", "raasi pettu", "రాసుకో", "రాసి పెట్టు", "rayandi", "రాయండి", "likh do", "likh lo", "लिख",
        "book lo", "బుక్ లో", "pustakam lo",
    ],
    "ask_price": [
        "rate", "price", "cost", "entha", "yentha", "enta", "ఎంత", "dhara", "ధర", "kitna hai", "kitne ka", "kitne ki",
        "kitna", "कितना", "कितने", "how much", "velа", "vela", "వెల",
    ],
    "ask_stock": [
        "undha", "unda", "undaa", "unnaya", "unnayaa", "ఉందా", "ఉన్నాయా", "dorukutunda", "దొరుకుతుందా",
        "available", "stock", "hai kya", "है क्या", "milega", "मिलेगा", "do you have", "have you got", "is there",
    ],
    "buy": [
        "kavali", "kaavali", "kavaali", "కావాలి", "kavalandi", "ivvandi", "ఇవ్వండి", "ivvu", "ఇవ్వు", "ivvara", "ఇవ్వరా",
        "ippinchandi", "ఇప్పించండి", "tesko", "teesko", "తీసుకో", "pampandi", "పంపండి", "pettandi", "పెట్టండి",
        "chahiye", "chaiye", "चाहिए", "de do", "dedo", "dena", "दे दो", "दो", "दे", "give", "want", "need", "buy", "get me", "i'll take",
        "pack", "pack cheyyi", "ప్యాక్", "konta", "కొంటా", "kontanu", "కొంటాను",
    ],
    "list_products": [
        "emi unnayi", "ఏమి ఉన్నాయి", "em unnayi", "ఏం ఉన్నాయి", "emunnayi", "ఏముంన్నాయి", "ఏమున్నాయి", "kya kya hai", "क्या क्या है",
        "what do you have", "what is available", "what all", "list", "menu", "items", "products",
    ],
    "done": [
        "antey", "anthe", "ante", "అంతే", "chalu", "చాలు", "bas", "बस", "that's all", "thats all", "that is all", "nothing else",
        "enough", "inka edi vaddu", "ఇంకా ఏమీ వద్దు", "inkem vaddu", "ఇంకేం వద్దు", "bill", "బిల్", "total", "మొత్తం",
    ],
    "goodbye": [
        "bye", "బై", "goodbye", "good bye", "veltanu", "వెళ్తాను", "vellosta", "వెళ్ళొస్తా", "vastanu", "వస్తాను", "malli vasta",
        "మళ్ళీ వస్తా", "చూస్తా", "alvida", "अलविदा", "chalta hoon", "चलता हूं", "see you", "ok bye",
    ],
    "thanks": ["thanks", "thank you", "thankyou", "dhanyavadalu", "dhanyavaadalu", "ధన్యవాదాలు", "shukriya", "शुक्रिया", "dhanyavad", "धन्यवाद"],
    "greeting": [
        "hello", "hi", "hey", "namaste", "namaskaram", "namaskar", "నమస్కారం", "నమస్తే", "नमस्ते", "నమస్కారము", "good morning",
        "good evening", "bagunnara", "బాగున్నారా", "ela unnaru", "ఎలా ఉన్నారు", "kaise ho", "कैसे हो",
    ],
    "affirm": ["avunu", "అవును", "aa", "ఆ", "sare", "సరే", "ok", "okay", "yes", "yeah", "haan", "हाँ", "हां", "ha", "theek hai", "ठीक है", "sari", "kaavali", "correct"],
    "deny": ["ledu", "లేదు", "vaddu", "వద్దు", "no", "nope", "nahi", "nahin", "नहीं", "mat", "kaadu", "కాదు", "nako", "నాకొద్దు", "akkarledu", "అక్కర్లేదు"],
}

# words that mean "cash" when we ask cash-or-khata
CASH_WORDS = ["cash", "క్యాష్", "nagadu", "నగదు", "dabbulu", "డబ్బులు", "dabbu", "డబ్బు", "paisa", "paise", "पैसे", "पैसा", "ippude", "ఇప్పుడే", "now", "abhi", "अभी", "upi", "phonepe", "gpay", "google pay", "paytm"]

NUMBER_WORDS: dict[str, float] = {
    # Telugu (latin + script)
    "oka": 1, "okati": 1, "okka": 1, "ఒక": 1, "ఒకటి": 1, "ఒక్క": 1,
    "rendu": 2, "randu": 2, "రెండు": 2, "moodu": 3, "mudu": 3, "మూడు": 3, "nalugu": 4, "naalugu": 4, "నాలుగు": 4,
    "aidu": 5, "ayidu": 5, "ఐదు": 5, "aaru": 6, "ఆరు": 6, "edu": 7, "ఏడు": 7, "enimidi": 8, "ఎనిమిది": 8,
    "tommidi": 9, "తొమ్మిది": 9, "padi": 10, "పది": 10, "padihenu": 15, "పదిహేను": 15, "iravai": 20, "ఇరవై": 20,
    "muppai": 30, "ముప్పై": 30, "nalabhai": 40, "నలభై": 40, "yabhai": 50, "yaabhai": 50, "యాభై": 50,
    "aravai": 60, "అరవై": 60, "debbai": 70, "డెబ్బై": 70, "enabhai": 80, "ఎనభై": 80, "tombhai": 90, "తొంభై": 90,
    "vanda": 100, "nooru": 100, "వంద": 100, "నూరు": 100, "rendu vandalu": 200, "రెండు వందలు": 200, "aidu vandalu": 500, "ఐదు వందలు": 500, "veyyi": 1000, "వెయ్యి": 1000,
    "ara": 0.5, "అర": 0.5, "sagam": 0.5, "సగం": 0.5, "pavu": 0.25, "పావు": 0.25,
    # Hindi
    "ek": 1, "एक": 1, "do": 2, "दो": 2, "teen": 3, "तीन": 3, "char": 4, "chaar": 4, "चार": 4, "paanch": 5, "panch": 5, "पांच": 5, "पाँच": 5,
    "che": 6, "chhe": 6, "छह": 6, "saat": 7, "सात": 7, "aath": 8, "आठ": 8, "nau": 9, "नौ": 9, "das": 10, "दस": 10,
    "bees": 20, "बीस": 20, "pachas": 50, "पचास": 50, "sau": 100, "सौ": 100, "aadha": 0.5, "आधा": 0.5,
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "half": 0.5, "quarter": 0.25, "dozen": 12,
}
UNIT_WORDS = {"kg", "kilo", "kilos", "కిలో", "కేజీ", "किलो", "litre", "liter", "litres", "లీటర్", "लीटर", "packet", "packets", "ప్యాకెట్", "पैकेट", "bottle", "bottles", "బాటిల్", "बोतल", "piece", "pieces", "ముక్క", "rupees", "rupayalu", "రూపాయలు", "रुपये", "rs"}

NAME_PATTERNS = [
    r"\bnaa?\s+peru\s+(\S+)", r"నా\s+పేరు\s+(\S+)", r"\bmy\s+name\s+is\s+(\S+)", r"\bi\s+am\s+(\S+)", r"\bi'?m\s+(\S+)",
    r"\bmera\s+naam\s+(\S+)", r"मेरा\s+नाम\s+(\S+)", r"\bthis\s+is\s+(\S+)", r"\bperu\s+(\S+)", r"పేరు\s+(\S+)",
]
NAME_STOPWORDS = {"andi", "అండి", "garu", "గారు", "sir", "madam", "hai", "है", "hoon", "हूं", "హూ", "nenu", "నేను", "naa", "na", "peru", "పేరు", "ok", "sare", "the", "a"}


# ---------------------------------------------------------------- helpers
def _contains(norm: str, keyword: str) -> bool:
    keyword = normalize(keyword)
    if not keyword:
        return False
    if keyword[0].isascii():
        return re.search(rf"(?<![\w']){re.escape(keyword)}(?![\w'])", norm) is not None
    return keyword in norm


def _match_keywords(norm: str, intent: str) -> int:
    return sum(1 for kw in KEYWORDS[intent] if _contains(norm, kw))


def _number_at(token: str) -> float | None:
    token = token.strip()
    if not token:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[a-zఀ-౿ऀ-ॿ]*", token)
    if m:
        return float(m.group(1))
    return NUMBER_WORDS.get(token)


def extract_numbers(text: str) -> list[tuple[float, int, int]]:
    """All numbers in text (digits or words) with their character spans."""
    norm = normalize(text)
    found: list[tuple[float, int, int]] = []
    for m in re.finditer(r"\d+(?:\.\d+)?", norm):
        found.append((float(m.group()), m.start(), m.end()))
    for word, value in sorted(NUMBER_WORDS.items(), key=lambda kv: -len(kv[0])):
        for m in re.finditer(re.escape(word), norm):
            s, e = m.span()
            if word[0].isascii() and ((s > 0 and norm[s - 1].isalnum()) or (e < len(norm) and norm[e].isalnum())):
                continue
            if any(not (e <= fs or s >= fe) for _, fs, fe in found):
                continue
            found.append((value, s, e))
    return sorted(found, key=lambda t: t[1])


def _qty_for(product_span: tuple[int, int], numbers: list[tuple[float, int, int]], norm: str, used: set[int]) -> float:
    start, end = product_span
    best = None
    for idx, (value, s, e) in enumerate(numbers):
        if idx in used:
            continue
        gap_before = norm[e:start] if e <= start else None
        gap_after = norm[end:s] if s >= end else None
        gap = gap_before if gap_before is not None else gap_after
        if gap is None:
            continue
        between = [t for t in gap.split() if t not in UNIT_WORDS]
        if len(between) <= 1 and len(gap) <= 14:
            distance = len(gap) + (0 if gap_before is not None else 4)  # prefer number before product
            if best is None or distance < best[0]:
                best = (distance, idx, value)
    if best is None:
        return 1
    used.add(best[1])
    return best[2]


def extract_name(text: str) -> str | None:
    norm = normalize(text)
    for pattern in NAME_PATTERNS:
        m = re.search(pattern, norm)
        if m:
            name = m.group(1).strip("'")
            if name and name not in NAME_STOPWORDS and _number_at(name) is None:
                return name.title() if name.isascii() else name
    tokens = norm.split()
    if len(tokens) <= 2 and tokens and tokens[0] in ("nenu", "నేను") and len(tokens) == 2:
        return tokens[1].title() if tokens[1].isascii() else tokens[1]
    return None


def bare_name(text: str, inventory: Inventory | None = None) -> str | None:
    """When we asked for a name, treat the utterance itself as the name."""
    explicit = extract_name(text)
    if explicit:
        return explicit
    norm = normalize(text)
    tokens = [t for t in norm.split() if t not in NAME_STOPWORDS and _number_at(t) is None]
    if not tokens or len(tokens) > 3:
        return None
    if inventory and inventory.find_all(norm):
        return None
    for intent in ("deny", "affirm", "goodbye", "done", "greeting"):
        if any(_contains(norm, kw) for kw in KEYWORDS[intent]):
            return None
    name = " ".join(tokens)
    return name.title() if name.isascii() else name


# ---------------------------------------------------------------- main entry
def mentions_cash(text: str) -> bool:
    norm = normalize(text)
    return any(_contains(norm, w) for w in CASH_WORDS)


def mentions_upi(text: str) -> bool:
    norm = normalize(text)
    return any(_contains(norm, w) for w in ("upi", "qr", "scan", "స్కాన్", "phonepe", "gpay", "google pay", "paytm", "online", "ఆన్లైన్", "కట్టేశాను", "kattesanu", "chellinchanu", "చెల్లించాను", "paid", "done payment", "payment chesanu", "పేమెంట్"))


def parse(text: str, inventory: Inventory) -> ParsedIntent:
    norm = normalize(text)
    result = ParsedIntent(text=text)
    if not norm:
        return result

    numbers = extract_numbers(norm)
    used_numbers: set[int] = set()
    for product, start, end in inventory.find_all(norm):
        qty = _qty_for((start, end), numbers, norm, used_numbers)
        result.items.append(Item(product=product, qty=qty))

    scores = {intent: _match_keywords(norm, intent) for intent in KEYWORDS}
    result.customer_name = extract_name(norm)

    # money amount = a number not consumed as a quantity (prefer one followed by "rupees")
    leftover = [n for i, n in enumerate(numbers) if i not in used_numbers]
    if leftover:
        result.amount = leftover[-1][0]

    if result.items:
        if scores["deny"] and not scores["buy"] and not scores["credit"]:
            result.intent = "remove"            # "coke vaddu" = take the coke off the bill
            result.confidence = 0.9
            return result
        for intent in ("pay_credit", "check_balance", "credit", "ask_price", "ask_stock", "buy"):
            if scores[intent]:
                result.intent = intent
                result.confidence = 0.9
                break
        else:
            result.intent = "buy"
            result.confidence = 0.6  # products mentioned without a verb: assume they want them
        if result.intent == "pay_credit" and result.amount is None:
            # "coke appu kattestanu" is odd; treat as buy on credit instead
            result.intent = "credit"
        return result

    order = ("pay_credit", "check_balance", "credit", "list_products", "done", "goodbye", "thanks", "greeting", "deny", "affirm", "ask_price", "ask_stock", "buy")
    for intent in order:
        if scores[intent]:
            result.intent = intent
            result.confidence = 0.85 if intent not in ("ask_price", "ask_stock", "buy") else 0.3
            if intent in ("ask_price", "ask_stock", "buy"):
                result.intent = "unknown"  # a verb with no product; let the LLM figure out what they mean
            break

    if result.intent == "unknown" and result.customer_name:
        result.intent = "my_name"
        result.confidence = 0.8
    return result
