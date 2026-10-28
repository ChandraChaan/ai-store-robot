# AI Store Robot

A shop assistant robot for a small village kirana store. It watches the counter
with a camera, greets customers in Telugu, understands what they ask for in
Telugu / Tenglish / Hindi / English, answers prices and stock, keeps a credit
book (khata), records sales, and sends a robot cart to fetch items from shelves.

Everything runs on one laptop (tested on a MacBook M2, 8 GB) with **zero
running cost**: no cloud APIs, no keys, no subscriptions.

| Piece | What it uses | Cost |
|---|---|---|
| Person detection | YOLOv8-nano (ultralytics) on CPU | free, offline |
| Speech to text | faster-whisper (Whisper, CTranslate2) | free, offline |
| Text to speech | macOS `say` with the Telugu voice *Geeta* (Hindi *Lekha*, English *Rishi*) | free, offline |
| Understanding | rule-based parser + local LLM `qwen3:4b-instruct` via Ollama | free, offline |
| Store data | `data/products.json` + SQLite khata `data/store.db` | free |
| Owner dashboard | built-in web page on port 8008 (phone on same Wi-Fi) | free |
| Robot | simulated by default; Arduino + L298N over USB when you have one | free / hardware |

## Quick start

```bash
./run.sh --text            # talk to the robot by typing, no camera or mic needed
./run.sh --voice           # microphone + speaker only, no camera
./run.sh                   # camera + microphone (settings from config.json / env)
./run.sh --source 0        # use the Mac webcam
./run.sh --source http://192.168.43.196:4747/video --rotate 90    # phone camera (DroidCam)
```

`run.sh` creates the virtualenv, installs `requirements.txt`, starts Ollama and
pulls the language model the first time. The first voice session also
downloads the Whisper `small` model (about 460 MB, one time).

Without Ollama the robot still works with the rule-based parser alone.
Without a microphone use `--stt typed`. Without `say` (Linux) replies are printed.

Keys in the camera window: `q` quit, `g` start a conversation manually, `l` mark the customer as gone.

## What a visit looks like

```
customer walks up            -> camera sees a person close to the counter for ~1 s
robot: నమస్కారం! AI Kirana Storeకి స్వాగతం. మీకు ఏమి కావాలి?
customer: naaku rendu coke mariyu oka chips kavali
robot: 2 బాటిల్ Coca-Cola, 80 రూపాయలు. 1 ప్యాకెట్ Lays chips, 20 రూపాయలు. మొత్తం 100 రూపాయలు. ఇంకా ఏమైనా కావాలా?
          (robot cart drives to shelf A1 and B1 and brings the items back)
customer: khata lo rasuko          (put it on my credit)
robot: సరే. మీ పేరు చెప్పండి?
customer: Ramu
robot: సరే Ramu గారు, ఖాతాలో రాస్తాను. ఇంకా ఏమైనా కావాలా?
customer: antey                    (that's all)
robot: Ramu గారు, 100 రూపాయలు ఖాతాలో రాశాను. మొత్తం బాకీ 100 రూపాయలు. ధన్యవాదాలు, మళ్ళీ రండి!
customer walks away          -> stock reduced, khata updated, dashboard shows it
```

Things customers can say (any language, mixed is fine):

- buy: `rendu coke kavali`, `ఒక కిలో బియ్యం ఇవ్వండి`, `do sprite chahiye`, `2 chips`
- price / stock: `biscuit rate entha`, `thums up undha?`, `sugar kitna hai`
- credit book: `khata lo rasuko`, `appu`, `udhar`, `repu istanu`
- pay back: `100 rupayalu kattestanu`, `యాభై రూపాయలు ఇస్తున్నాను`
- balance: `naa khata entha`, `బాకీ ఎంత`, `kitna baaki`
- finish: `antey`, `bas`, `that's all`, `bye`

Numbers in Telugu, Hindi and English words are understood (`rendu`, `మూడు`, `paanch`, `half`, `ara kilo`).

## Owner tools

**Dashboard**: `http://<mac-ip>:8008` shows the live camera, who is at the
counter, the conversation, today's cash sales, khata balances, stock with
low-stock warnings, and lets you adjust stock or record a payment from your phone.

**Command line** (works while the robot runs):

```bash
venv/bin/python tools/khata.py balances
venv/bin/python tools/khata.py today
venv/bin/python tools/khata.py pay "Ramu" 100
venv/bin/python tools/khata.py credit "Ramu" rice 2
venv/bin/python tools/khata.py stock coke +12
venv/bin/python tools/khata.py price coke 45
```

**Products** live in `data/products.json`. Each has a price, stock, shelf and
aliases in English, Telugu and Hindi. Add a product by adding an entry; the
robot understands it immediately on restart.

## Configuration

Run `python main.py --write-config` to get `config.example.json` with every
setting, copy it to `config.json` and edit. Any setting can also be an
environment variable: `STORE_CAMERA_SOURCE=0 STORE_LANGUAGE=hi ./run.sh`.

Important ones:

| Setting | Default | Meaning |
|---|---|---|
| `camera_source` | `"0"` | webcam index or stream URL |
| `rotate` | `0` | 90 for a phone held upright |
| `near_area_ratio` | `0.06` | how big a person must be in frame to count as "at the counter" |
| `enter_frames` / `leave_seconds` | `6` / `4` | debounce for greeting and goodbye |
| `language` | `te` | te, hi or en |
| `stt_model` | `small` | tiny/base are faster, medium is more accurate |
| `ollama_model` | `qwen3:4b-instruct` | any Ollama model; set `use_llm=false` to disable |
| `robot_backend` | `sim` | `serial` with `robot_port` for a real robot |
| `tts_backend` | `say` | `edge` for neural voices (needs internet) |

## Project structure

```
main.py                  entry point (camera mode / --text mode)
camera/camera_stream.py  threaded camera reader with auto-reconnect
vision/person_detection.py  YOLOv8 person detector
vision/presence.py       debounced ENTER / LEAVE state machine
voice/speech_to_text.py  voice-activity recording + faster-whisper
voice/text_to_speech.py  macOS say / edge-tts speaker with a queue
ai/nlu.py                rule-based Telugu / Hindi / English parser (products, quantities, names, money)
ai/brain.py              combines the parser with the local LLM (Ollama)
ai/replies.py            reply templates (te / hi / en)
ai/conversation_engine.py  listen -> understand -> act -> speak loop
store/inventory.py       products + stock (data/products.json)
store/ledger.py          khata and sales (SQLite)
store/store_controller.py  dialog policy: cart, credit, payments, checkout
robot/robot_control.py   simulated robot + Arduino serial robot
arduino/robot_firmware.ino  motor firmware matching the serial protocol
dashboard/               owner web dashboard (stdlib http server)
tools/khata.py           owner command line
tests/                   pytest suite (run: venv/bin/python -m pytest)
```

## Robot hardware (optional)

Flash `arduino/robot_firmware.ino` to an Arduino with an L298N motor driver
(pins are at the top of the file) and a servo gripper. Start with
`--robot serial --port /dev/cu.usbserial-XXXX`. Shelf routes are the lists of
timed moves under `shelves` in `data/products.json`; tune the milliseconds for
your floor. The robot drives to the shelf, grabs, returns by the reverse route
and releases at the counter.

## Roadmap

- Face recognition so regular customers are greeted by name
- Product recognition by camera at checkout (no barcode)
- UPI QR on the dashboard for cash-less payment
- Telugu wake word so the robot can be called from across the shop

## Author

Chandra
