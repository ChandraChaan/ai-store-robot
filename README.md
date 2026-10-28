# AI Store Robot

A kirana (village general store) that runs itself. Cameras see the customer,
the shop talks in Telugu, Hindi or English, recognises the items placed on the
counter, shows a UPI QR for the exact amount or writes the bill on a member's
khata, and records everything in the owner's phone dashboard and Google Sheet.

Everything runs on one computer (tested on a MacBook M2, 8 GB) with **zero
running cost**: no cloud APIs, no keys, no subscriptions. See [ROADMAP.md](ROADMAP.md)
for the full idea and the phases.

| Piece | What it uses | Cost |
|---|---|---|
| Customer detection | YOLOv8-nano (ultralytics) on CPU | free, offline |
| Product recognition | empty-counter difference + DINOv2 embeddings (timm), learnt from photos, no training | free, offline |
| Speech to text | faster-whisper | free, offline |
| Text to speech | macOS `say`, Telugu voice *Geeta* (Hindi *Lekha*, English *Rishi*) | free, offline |
| Understanding | rule-based parser + local LLM `qwen3:4b-instruct` via Ollama | free, offline |
| Payments | UPI deep-link QR, no gateway | free |
| Store data | `data/products.json` + SQLite `data/store.db` | free |
| Owner dashboard, customer screen | built-in web pages on port 8008 | free |
| Google Sheets | free Apps Script web app | free |
| Cameras | old Android phones with DroidCam / IP Webcam, or USB webcams | free / cheap |

## Quick start

```bash
./run.sh --text                       # no hardware: type as a customer, simulate the counter and payment
./run.sh --voice                      # microphone + speaker, no camera
venv/bin/python tools/find_phones.py  # find your phones on Wi-Fi and save them as door / counter cameras
./run.sh                              # the real thing: cameras + voice + counter billing + screen
```

`run.sh` creates the virtualenv, installs `requirements.txt`, starts Ollama
and pulls the language model the first time. First voice use downloads the
Whisper `small` model (460 MB); first counter use downloads the embedding model (90 MB).

### Phones as cameras (1, 2 or 3 phones)

1. On each old phone install **DroidCam** or **IP Webcam** (free), start it, same Wi-Fi as the computer.
2. Run `venv/bin/python tools/find_phones.py`. It scans the network, tests each stream and asks which phone is the
   **door** camera (sees customers), the **counter** camera (sees items; optional, the door camera is used if missing)
   and an optional **shop** camera. Saved to `config.json`.
3. Or by hand: `python main.py --door http://192.168.1.21:4747/video --counter http://192.168.1.22:4747/video --rotate 90`.
4. A spare phone or tablet becomes the **customer screen**: open `http://<computer-ip>:8008/screen` on it (double tap for full screen).

### Teach it your products (once, about a minute per product)

Products live in `data/products.json` (price, stock, aliases in Telugu, Hindi and English). To recognise them on the counter:

- From the dashboard: with the counter empty tap **Counter is empty now**. Put one product on the counter, pick its
  name, tap **Learn this product**, rotate it, tap again 5 to 10 times. Done.
- Or in a window: `venv/bin/python tools/learn_products.py` (keys: `r` empty counter, `l` learn, `t` test, `q` quit).

Tips: a plain, single-colour counter top works best; keep items apart; re-do "counter is empty" when the light changes
(it also refreshes itself when the counter has been empty for a while).

### Payments

Set your UPI ID once (`"upi_id": "yourshop@okaxis"` in `config.json`, or `--upi`). The customer screen then shows a QR for
the exact bill amount, readable by any UPI app. The bill is marked paid when:

- you tap **Mark paid (UPI)** on the dashboard, or
- your Android phone forwards the bank/UPI notification: with the free MacroDroid or Tasker app, on notification
  containing "credited", POST JSON `{"token": "<payment_webhook_token>", "amount": <amount>, "ref": "<text>"}` to
  `http://<computer-ip>:8008/api/payment_received`, or
- a member says "khata lo rasuko" (goes on their account), or the customer pays cash and you tap **Paid cash**.

If a customer walks away with items unpaid, the shop warns them aloud, the bill is marked **unpaid** and shows in red.

### Google Sheets (optional)

Create a Google Sheet, Extensions > Apps Script, paste `integrations/apps_script.gs`, set `TOKEN`, deploy as a web app
(execute as you, anyone can access). Put the URL and token in `config.json` (`sheets_webhook_url`, `sheets_token`).
Bills, khata, payments, stock changes and visits appear in tabs. Offline rows wait in `data/outbox.jsonl` and go later.

## What a visit looks like

```
customer walks up           door camera sees a person at the counter for ~1 s
robot: నమస్కారం! AI Kirana Storeకి స్వాగతం. మీకు ఏమి కావాలి?
customer puts 2 coke, 1 chips on the counter
robot: కౌంటర్ మీద: 2 Coca-Cola, 1 Lays chips. మొత్తం 100 రూపాయలు. ఇంకా ఏమైనా ఉంటే పెట్టండి, అయిపోతే 'అంతే' అనండి.
customer: coke okati                     (correction: one coke)
robot: సరే, Coca-Cola 1 బాటిల్.
customer: antey
robot: మొత్తం 60 రూపాయలు. స్క్రీన్ మీద QR స్కాన్ చేసి చెల్లించండి, లేదా ఖాతాలో రాయమంటే చెప్పండి.
          screen shows the QR for ₹60; payment arrives
robot: 60 రూపాయలు అందాయి. ధన్యవాదాలు, మళ్ళీ రండి!
```

Things customers can say (any language, mixed is fine): buy `rendu coke kavali`, correct `coke okati`, remove
`chips vaddu`, price `biscuit rate entha`, stock `thums up undha?`, khata `khata lo rasuko`, pay back
`100 rupayalu kattestanu`, balance `naa khata entha`, finish `antey` / `bas` / `that's all`.

## Testing without hardware

`./run.sh --text` runs the whole flow with typed input. Extra commands: `/counter coke 2, chips 1` (the counter camera
sees these), `/counter clear`, `/paid` (UPI arrived), `/cash`, `/leave` (customer walked away), `/screen` (what the
customer screen shows). The dashboard and screen pages work in this mode too.

Keys in a camera window: `q` quit, `g` start a conversation, `l` customer left, `r` counter is empty, `p` paid by UPI, `c` paid cash.

## Owner tools

- Dashboard `http://<computer-ip>:8008`: cameras, who is at the counter, bill and payment state, counter items,
  learn products, today's totals, khata, stock, bills, events, Sheets status.
- `venv/bin/python tools/khata.py balances | today | pay "Ramu" 100 | credit "Ramu" rice 2 | stock coke +12 | price coke 45`

## Configuration

`python main.py --write-config` writes `config.example.json` with every setting; copy to `config.json`. Any setting is
also an environment variable: `STORE_LANGUAGE=hi ./run.sh`. Important ones:

| Setting | Default | Meaning |
|---|---|---|
| `cameras` | `{"door": {"source": "0"}}` | named cameras: door, counter, shop |
| `near_area_ratio` | `0.06` | how big a person must be in frame to count as "at the counter" |
| `counter_match_threshold` | `0.62` | how sure the product match must be (lower = more matches, more mistakes) |
| `counter_diff_threshold` | `32` | sensitivity of the empty-counter difference |
| `upi_id` | empty | your UPI ID; empty disables the QR (cash or khata question instead) |
| `accept_cash` | `true` | owner present; set false when fully unmanned |
| `language` | `te` | te, hi or en |
| `ollama_model` | `qwen3:4b-instruct` | local LLM; `use_llm=false` to disable |
| `sheets_webhook_url` | empty | Apps Script URL |

## Project structure

```
main.py                 entry point: camera mode, --text, --voice
core/config.py          settings (config.json / env / flags), camera roles
core/visit.py           the visit: ARRIVE -> SHOP -> BILL -> PAY -> LEAVE
perception/camera.py    threaded camera reader with auto-reconnect
perception/person.py    YOLOv8 person detector
perception/presence.py  debounced ENTER / LEAVE
perception/counter.py   counter item segmentation + recognition + stabiliser
perception/products.py  learned product library     perception/embeddings.py  DINOv2 embeddings
voice/                  speaker (say / edge-tts) and listener (VAD + faster-whisper)
brain/nlu.py            Telugu / Hindi / English parser   brain/llm.py  Ollama   brain/replies.py  templates
brain/conversation.py   listen -> understand -> act -> speak loop
shop/inventory.py       products + stock     shop/ledger.py  khata, sales, bills (SQLite)
shop/controller.py      dialog policy: cart, corrections, credit, UPI / cash / khata settlement
shop/payments.py        UPI deep link + QR, payment requests
integrations/sheets.py  Google Sheets sync (Apps Script), offline outbox
ui/server.py            dashboard + customer screen server   ui/dashboard.html   ui/customer.html
tools/find_phones.py    phone camera finder   tools/learn_products.py   tools/khata.py
future/robot/           moving robot (simulator + Arduino), parked until v1.5
tests/                  pytest suite: venv/bin/python -m pytest
```

## Author

Chandra
