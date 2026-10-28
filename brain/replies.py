"""Reply templates in Telugu (te), Hindi (hi) and English (en).

Prices and stock in replies always come from the store data, never from the
language model, so the robot can't invent a price.
"""
from __future__ import annotations

TEMPLATES: dict[str, dict[str, str]] = {
    "greet": {
        "te": "నమస్కారం! {store}కి స్వాగతం. మీకు ఏమి కావాలి?",
        "hi": "नमस्ते! {store} में आपका स्वागत है। आपको क्या चाहिए?",
        "en": "Welcome to {store}! What would you like?",
    },
    "greet_again": {"te": "చెప్పండి, ఏమి కావాలి?", "hi": "बोलिए, क्या चाहिए?", "en": "Yes, what would you like?"},
    "price": {
        "te": "{name} ఒక {unit} {price} రూపాయలు.",
        "hi": "{name} एक {unit} {price} रुपये।",
        "en": "{name} is {price} rupees per {unit}.",
    },
    "in_stock": {"te": "{name} ఉంది, {stock} {unit} ఉన్నాయి.", "hi": "{name} है, {stock} {unit} हैं।", "en": "Yes, {name} is available, {stock} {unit} left."},
    "out_of_stock": {"te": "క్షమించండి, {name} అయిపోయింది.", "hi": "माफ़ कीजिए, {name} खत्म हो गया।", "en": "Sorry, {name} is out of stock."},
    "not_enough": {
        "te": "క్షమించండి, {name} {stock} {unit} మాత్రమే ఉంది.",
        "hi": "माफ़ कीजिए, {name} सिर्फ {stock} {unit} है।",
        "en": "Sorry, only {stock} {unit} of {name} left.",
    },
    "added": {
        "te": "{qty} {unit} {name}, {line} రూపాయలు.",
        "hi": "{qty} {unit} {name}, {line} रुपये।",
        "en": "{qty} {unit} {name}, {line} rupees.",
    },
    "cart_total": {
        "te": "మొత్తం {total} రూపాయలు. ఇంకా ఏమైనా కావాలా?",
        "hi": "कुल {total} रुपये। और कुछ चाहिए?",
        "en": "Total {total} rupees. Anything else?",
    },
    "not_found": {"te": "క్షమించండి, {name} మా దగ్గర లేదు.", "hi": "माफ़ कीजिए, {name} हमारे पास नहीं है।", "en": "Sorry, we don't have {name}."},
    "ask_name": {"te": "సరే. మీ పేరు చెప్పండి?", "hi": "ठीक है। आपका नाम क्या है?", "en": "Sure. What is your name?"},
    "ask_name_again": {"te": "మీ పేరు మళ్ళీ చెప్పండి?", "hi": "अपना नाम फिर से बताइए?", "en": "Please tell me your name again?"},
    "credit_ok": {
        "te": "సరే {name} గారు, ఖాతాలో రాస్తాను. ఇంకా ఏమైనా కావాలా?",
        "hi": "ठीक है {name} जी, खाते में लिख दूंगा। और कुछ चाहिए?",
        "en": "Okay {name}, I'll put it on your khata. Anything else?",
    },
    "balance": {"te": "{name} గారు, మీ ఖాతాలో బాకీ {balance} రూపాయలు.", "hi": "{name} जी, आपके खाते में {balance} रुपये बाकी हैं।", "en": "{name}, your khata balance is {balance} rupees."},
    "balance_zero": {"te": "{name} గారు, మీ ఖాతాలో బాకీ ఏమీ లేదు.", "hi": "{name} जी, आपके खाते में कुछ बाकी नहीं है।", "en": "{name}, you have no balance on your khata."},
    "ask_amount": {"te": "ఎంత ఇస్తున్నారు?", "hi": "कितना दे रहे हैं?", "en": "How much are you paying?"},
    "payment_ok": {
        "te": "ధన్యవాదాలు {name} గారు. {amount} రూపాయలు జమ చేశాను. ఇప్పుడు బాకీ {balance} రూపాయలు.",
        "hi": "धन्यवाद {name} जी। {amount} रुपये जमा किए। अब बाकी {balance} रुपये।",
        "en": "Thank you {name}. {amount} rupees received. Remaining balance {balance} rupees.",
    },
    "ask_payment": {
        "te": "మొత్తం {total} రూపాయలు. డబ్బులు ఇస్తారా, ఖాతాలో రాయమంటారా?",
        "hi": "कुल {total} रुपये। पैसे देंगे या खाते में लिखूं?",
        "en": "Total {total} rupees. Cash, or on your khata?",
    },
    "bill_cash": {"te": "మొత్తం {total} రూపాయలు. ధన్యవాదాలు, మళ్ళీ రండి!", "hi": "कुल {total} रुपये। धन्यवाद, फिर आइए!", "en": "Total {total} rupees. Thank you, come again!"},
    "bill_credit": {
        "te": "{name} గారు, {total} రూపాయలు ఖాతాలో రాశాను. మొత్తం బాకీ {balance} రూపాయలు. ధన్యవాదాలు, మళ్ళీ రండి!",
        "hi": "{name} जी, {total} रुपये खाते में लिख दिए। कुल बाकी {balance} रुपये। धन्यवाद, फिर आइए!",
        "en": "{name}, {total} rupees added to your khata. Total balance {balance} rupees. Thank you, come again!",
    },
    "bye": {"te": "ధన్యవాదాలు, మళ్ళీ రండి!", "hi": "धन्यवाद, फिर आइए!", "en": "Thank you, come again!"},
    "list": {"te": "మా దగ్గర {items} ఉన్నాయి.", "hi": "हमारे पास {items} है।", "en": "We have {items}."},
    "unknown": {"te": "క్షమించండి, అర్థం కాలేదు. మళ్ళీ చెప్పండి?", "hi": "माफ़ कीजिए, समझ नहीं आया। फिर से बोलिए?", "en": "Sorry, I didn't understand. Could you say that again?"},
    "idle_end": {"te": "సరే, అవసరమైతే పిలవండి.", "hi": "ठीक है, ज़रूरत हो तो बुलाइए।", "en": "Okay, call me if you need anything."},
    "welcome_back": {"te": "{name} గారు, మళ్ళీ స్వాగతం! ఏమి కావాలి?", "hi": "{name} जी, फिर से स्वागत है! क्या चाहिए?", "en": "Welcome back {name}! What would you like?"},
    "fetching": {"te": "{name} తీసుకొస్తున్నాను.", "hi": "{name} ला रहा हूं।", "en": "Fetching {name}."},
    "thanks": {"te": "సంతోషం! ఇంకా ఏమైనా కావాలా?", "hi": "खुशी हुई! और कुछ चाहिए?", "en": "You're welcome! Anything else?"},
    "ok_anything_else": {"te": "సరే. ఇంకా ఏమైనా కావాలా?", "hi": "ठीक है। और कुछ चाहिए?", "en": "Okay. Anything else?"},
    "counter_bill": {
        "te": "కౌంటర్ మీద: {items}. మొత్తం {total} రూపాయలు. ఇంకా ఏమైనా ఉంటే పెట్టండి, అయిపోతే 'అంతే' అనండి.",
        "hi": "काउंटर पर: {items}। कुल {total} रुपये। और कुछ हो तो रखिए, हो गया तो 'बस' बोलिए।",
        "en": "On the counter: {items}. Total {total} rupees. Add more items, or say 'that's all'.",
    },
    "counter_unknown": {
        "te": "ఒక వస్తువు గుర్తుపట్టలేకపోయాను. దయచేసి వస్తువులను విడివిడిగా పెట్టండి, లేదా పేరు చెప్పండి.",
        "hi": "एक चीज़ पहचान नहीं पाया। कृपया चीज़ें अलग-अलग रखिए, या नाम बताइए।",
        "en": "I could not recognise one item. Please spread the items out, or tell me its name.",
    },
    "counter_empty": {"te": "కౌంటర్ ఖాళీగా ఉంది. వస్తువులు పెట్టండి.", "hi": "काउंटर खाली है। चीज़ें रखिए।", "en": "The counter is empty. Please place your items."},
    "qty_set": {"te": "సరే, {name} {qty} {unit}.", "hi": "ठीक है, {name} {qty} {unit}।", "en": "Okay, {qty} {unit} {name}."},
    "removed": {"te": "సరే, {name} తీసేశాను.", "hi": "ठीक है, {name} हटा दिया।", "en": "Okay, removed {name}."},
    "pay_upi": {
        "te": "మొత్తం {total} రూపాయలు. స్క్రీన్ మీద QR స్కాన్ చేసి చెల్లించండి.",
        "hi": "कुल {total} रुपये। स्क्रीन पर QR स्कैन करके भुगतान कीजिए।",
        "en": "Total {total} rupees. Please scan the QR on the screen to pay.",
    },
    "pay_upi_or_khata": {
        "te": "మొత్తం {total} రూపాయలు. స్క్రీన్ మీద QR స్కాన్ చేసి చెల్లించండి, లేదా ఖాతాలో రాయమంటే చెప్పండి.",
        "hi": "कुल {total} रुपये। स्क्रीन पर QR स्कैन करके भुगतान कीजिए, या खाते में लिखने को बोलिए।",
        "en": "Total {total} rupees. Scan the QR on the screen to pay, or say khata to put it on your account.",
    },
    "pay_reminder": {"te": "QR స్కాన్ చేసి చెల్లించండి. ఖాతా అయితే 'ఖాతా' అనండి.", "hi": "QR स्कैन करके भुगतान कीजिए। खाता हो तो 'खाता' बोलिए।", "en": "Please scan the QR to pay, or say khata."},
    "pay_wait_confirm": {"te": "చెల్లింపు కోసం చూస్తున్నాను, ఒక్క క్షణం.", "hi": "भुगतान की पुष्टि देख रहा हूं, एक पल।", "en": "Checking for the payment, one moment."},
    "paid_thanks": {"te": "{amount} రూపాయలు అందాయి. ధన్యవాదాలు, మళ్ళీ రండి!", "hi": "{amount} रुपये मिल गए। धन्यवाद, फिर आइए!", "en": "{amount} rupees received. Thank you, come again!"},
    "cash_received": {"te": "{amount} రూపాయలు నగదు. ధన్యవాదాలు, మళ్ళీ రండి!", "hi": "{amount} रुपये नकद। धन्यवाद, फिर आइए!", "en": "{amount} rupees cash. Thank you, come again!"},
    "unpaid_warning": {
        "te": "దయచేసి {total} రూపాయలు చెల్లించండి! చెల్లింపు ఇంకా అందలేదు.",
        "hi": "कृपया {total} रुपये का भुगतान कीजिए! भुगतान अभी नहीं मिला।",
        "en": "Please pay {total} rupees! Payment has not been received.",
    },
    "bill_reopened": {"te": "కొత్త వస్తువు కనిపించింది, బిల్లు మారుస్తున్నాను.", "hi": "नई चीज़ दिखी, बिल बदल रहा हूं।", "en": "I see a new item, updating the bill."},
    "owner_low_stock": {"te": "గమనిక: {items} తక్కువగా ఉన్నాయి.", "hi": "ध्यान दें: {items} कम हैं।", "en": "Note: low stock on {items}."},
}

UNIT_NAMES = {
    "te": {"kg": "కిలో", "litre": "లీటర్", "packet": "ప్యాకెట్", "bottle": "బాటిల్", "piece": "", "sachet": "ప్యాకెట్", "box": "బాక్స్"},
    "hi": {"kg": "किलो", "litre": "लीटर", "packet": "पैकेट", "bottle": "बोतल", "piece": "", "sachet": "पैकेट", "box": "डिब्बा"},
    "en": {},
}


def fmt_num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def unit_name(unit: str, lang: str) -> str:
    return UNIT_NAMES.get(lang, {}).get(unit, unit)


def t(key: str, lang: str = "te", **kwargs) -> str:
    table = TEMPLATES.get(key, {})
    template = table.get(lang) or table.get("en") or key
    clean = {}
    for k, v in kwargs.items():
        if isinstance(v, (int, float)):
            clean[k] = fmt_num(v)
        else:
            clean[k] = v
    if "unit" in clean:
        clean["unit"] = unit_name(clean["unit"], lang)
    text = template.format(**clean)
    return " ".join(text.split())
