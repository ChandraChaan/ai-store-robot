import pytest

from brain import nlu


def items(parsed):
    return {i.product.key: i.qty for i in parsed.items}


@pytest.mark.parametrize("text,intent,expected", [
    ("naaku rendu coke kavali", "buy", {"coke": 2}),
    ("2 coke and 3 chips", "buy", {"coke": 2, "chips": 3}),
    ("ఒక కిలో బియ్యం ఇవ్వండి", "buy", {"rice": 1}),
    ("రెండు బిస్కెట్ ప్యాకెట్లు కావాలి", "buy", {"biscuit": 2}),
    ("mujhe do sprite chahiye", "buy", {"sprite": 2}),
    ("ek kilo chawal de do", "buy", {"rice": 1}),
    ("coke rendu ivvandi", "buy", {"coke": 2}),
    ("ara kilo chakkera", "buy", {"sugar": 0.5}),
    ("thums up undha?", "ask_stock", {"thums_up": 1}),
    ("బియ్యం ఉందా", "ask_stock", {"rice": 1}),
    ("biscuit rate entha", "ask_price", {"biscuit": 1}),
    ("sugar kitna hai", "ask_price", {"sugar": 1}),
    ("నూనె ధర ఎంత", "ask_price", {"oil": 1}),
    ("rendu maggi khata lo rasuko", "credit", {"maggi": 2}),
    ("ఒక సబ్బు అప్పు రాయండి", "credit", {"soap": 1}),
    ("coke", "buy", {"coke": 1}),
    ("cokes", "buy", {"coke": 1}),
])
def test_items_and_intents(inventory, text, intent, expected):
    parsed = nlu.parse(text, inventory)
    assert parsed.intent == intent, parsed.describe()
    assert items(parsed) == expected, parsed.describe()


@pytest.mark.parametrize("text,intent", [
    ("hello", "greeting"), ("నమస్కారం", "greeting"), ("namaste", "greeting"),
    ("bye", "goodbye"), ("వెళ్తాను", "goodbye"),
    ("thanks", "thanks"), ("ధన్యవాదాలు", "thanks"),
    ("antey", "done"), ("అంతే", "done"), ("bas", "done"), ("that's all", "done"),
    ("em unnayi", "list_products"), ("ఏమి ఉన్నాయి", "list_products"), ("kya kya hai", "list_products"),
    ("naa khata entha", "check_balance"), ("బాకీ ఎంత", "check_balance"), ("kitna baaki hai", "check_balance"),
    ("100 rupayalu kattestanu", "pay_credit"), ("యాభై రూపాయలు ఇస్తున్నాను", "pay_credit"),
    ("khata lo rasuko", "credit"), ("ఖాతాలో రాయండి", "credit"),
    ("ledu", "deny"), ("వద్దు", "deny"), ("nahi", "deny"),
    ("avunu", "affirm"), ("సరే", "affirm"), ("haan", "affirm"),
    ("asdkjh qwe", "unknown"),
])
def test_plain_intents(inventory, text, intent):
    assert nlu.parse(text, inventory).intent == intent


def test_payment_amount(inventory):
    p = nlu.parse("100 rupayalu kattestanu", inventory)
    assert p.intent == "pay_credit" and p.amount == 100
    p = nlu.parse("యాభై రూపాయలు ఇస్తున్నాను", inventory)
    assert p.amount == 50


def test_amount_not_confused_with_quantity(inventory):
    p = nlu.parse("rendu coke kavali", inventory)
    assert p.amount is None and items(p) == {"coke": 2}


@pytest.mark.parametrize("text,name", [
    ("naa peru Ramu", "Ramu"), ("నా పేరు రాము", "రాము"), ("my name is Sita", "Sita"),
    ("mera naam Raju hai", "Raju"), ("nenu Lakshmi", "Lakshmi"), ("i am venkat", "Venkat"),
])
def test_name_extraction(inventory, text, name):
    p = nlu.parse(text, inventory)
    assert p.customer_name == name
    assert p.intent == "my_name"


def test_name_with_credit_order(inventory):
    p = nlu.parse("ఒక కిలో బియ్యం ఇవ్వండి, డబ్బులు రేపు ఇస్తాను, నా పేరు రాము", inventory)
    assert p.intent == "credit"
    assert items(p) == {"rice": 1}
    assert p.customer_name == "రాము"


def test_bare_name(inventory):
    assert nlu.bare_name("Ramu", inventory) == "Ramu"
    assert nlu.bare_name("ramu andi", inventory) == "Ramu"
    assert nlu.bare_name("రాము", inventory) == "రాము"
    assert nlu.bare_name("ledu", inventory) is None
    assert nlu.bare_name("rendu coke", inventory) is None
