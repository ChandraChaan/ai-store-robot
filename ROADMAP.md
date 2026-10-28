# Roadmap: a kirana shop that runs itself

Approved 28 Oct 2026. Simple words on purpose, so anyone can read it.

## The idea

A shop assistant that never sleeps. A customer walks in, the shop recognises
them, talks to them in Telugu, bills what they put on the counter, takes
payment by UPI or writes it on their khata, and records everything in the
owner's Google Sheet and phone. The owner restocks and checks the numbers.

## One visit

| Step | What happens | Who does it |
|---|---|---|
| ARRIVE | door camera sees a person; greeting | presence detection |
| IDENTIFY | member face matched: greet by name, remind khata balance | face recognition (v1.2) |
| SHOP | customer picks items; shop camera keeps track of them | person tracking |
| BILL | items placed on the counter are recognised; bill shown on screen and read aloud; voice corrections | counter camera + voice |
| PAY | UPI QR with exact amount, or "khata lo rasuko" for members | customer screen, payments |
| LEAVE | thank you; unpaid exit = voice warning + photo to owner (v1.4) | presence + alerts |

## Decisions

- Cameras: as many as needed. Normal setup is two: door (people) and counter (products). One camera can do both to start.
- Billing method: counter camera. Customer puts items on the counter, the shop recognises them. No shelf sensors.
- Products are learnt by photos, no model training: hold each product under the counter camera for a few seconds, done. New product = one minute.
- Google Sheets: included from v1.1, optional. Rows are sent to a free Google Apps Script link the owner creates once; no Google Cloud project.
- Payments: UPI deep-link QR, no gateway, no fee. Confirmation by owner tap, by a free notification forwarder on the owner's Android phone, or khata for face-verified members.
- Moving robot: parked in `future/robot/`, not wired in. Comes back later as "bring items to the counter".
- Scale for loose items: optional, later.
- Everything runs on the shop computer. Internet only for Sheets, Telegram and UPI.

## Phases

- **v1.1 Counter billing** (this release): repo restructured around the visit flow; product learning tool; counter recognition; bill by voice and screen; customer screen with UPI QR; payment states; Google Sheets sync; owner confirm from dashboard.
- **v1.2 Members**: face enrolment and recognition, greet by name, balance reminder, khata only with a face match, visit clips.
- **v1.3 Owner cloud**: Telegram alerts (low stock, unpaid exit, daily report), WhatsApp reminder links for khata, restock mode by voice.
- **v1.4 Truly unmanned**: unpaid-exit alarm, night mode door lock, 24/7 mini PC with auto-start, watchdog, backups.
- **v1.5 Smarter**: "your usual items?", reorder suggestions, better Telugu speech model, multi-camera tracking, optional scale, moving robot returns.

## Hardware (one time)

| Item | Why | Rough cost (INR) |
|---|---|---|
| 2 USB webcams or old Android phones | door camera, counter camera | 0 to 3,000 each |
| USB speakerphone | shop noise kills a laptop mic | 2,000 to 4,000 |
| Old tablet or phone | customer screen (bill + QR) | 0 |
| Mini PC or Mac mini (later) | runs 24/7 | 15,000 to 40,000 |
| Optional load-cell scale + ESP32 | loose items by weight | 600 |
| Optional electric door lock + ESP32 | night mode | 1,500 |

## Known limits

- Product recognition needs each product shown to the camera once (about a minute per product).
- Overlapping or stacked items on the counter are hard; the shop asks the customer to spread them out.
- Automatic UPI confirmation needs the free forwarder app on the owner's phone; until then the owner taps "paid".
- Unmanned still needs some trust. Cameras, face-verified khata and the exit alarm reduce loss, they do not make it zero.
