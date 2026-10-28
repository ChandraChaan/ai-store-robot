import pytest

from ai import nlu
from store.store_controller import StoreController


class FakeRobot:
    def __init__(self):
        self.fetched = []

    def fetch(self, shelf, label="", wait=False):
        self.fetched.append((shelf, label))


@pytest.fixture
def store(inventory, ledger):
    class S:
        language = "en"
        store_name = "Test Store"

    return StoreController(inventory, ledger, robot=FakeRobot(), settings=S())


def say(store, text):
    return store.handle(nlu.parse(text, store.inventory))


def test_cash_purchase_flow(store, ledger, inventory):
    assert "Welcome" in store.begin_session()
    r = say(store, "2 coke and 1 chips")
    assert "Total 100" in r.text and not r.end
    assert store.robot.fetched == [("A1", "Coca-Cola"), ("B1", "Lays chips")]
    r = say(store, "that's all")
    assert "Cash, or on your khata" in r.text
    r = say(store, "cash")
    assert r.end and "Total 100" in r.text
    assert inventory.get("coke").stock == 8 and inventory.get("chips").stock == 14
    assert ledger.summary()["sales"] == 100


def test_credit_flow_asks_name_then_records(store, ledger):
    store.begin_session()
    r = say(store, "ek kilo chawal khata mein likh do")
    assert "What is your name" in r.text
    r = say(store, "Ramu")
    assert "Okay Ramu" in r.text and not r.end
    r = say(store, "bas")
    assert r.end and "60 rupees added to your khata" in r.text
    assert ledger.balance("Ramu") == 60


def test_done_then_credit_then_name_checks_out(store, ledger):
    store.begin_session()
    say(store, "one sugar")
    r = say(store, "antey")
    assert "khata" in r.text
    r = say(store, "khata lo rasuko")
    assert "What is your name" in r.text
    r = say(store, "naa peru Sita")
    assert r.end and ledger.balance("Sita") == 45


def test_balance_and_payment(store, ledger):
    ledger.add_credit("Ramu", [("rice", 2, 120)])
    store.begin_session()
    r = say(store, "naa khata entha")
    assert "name" in r.text
    r = say(store, "Ramu")
    assert "120" in r.text
    r = say(store, "100 rupayalu kattestanu")
    assert "100 rupees received" in r.text and "20" in r.text
    assert ledger.balance("Ramu") == 20


def test_out_of_stock_and_not_enough(store):
    store.begin_session()
    assert "out of stock" in say(store, "thums up kavali").text
    assert "only 6" in say(store, "10 sprite").text


def test_price_and_stock_questions(store):
    store.begin_session()
    assert "40 rupees" in say(store, "coke rate entha").text
    assert "available" in say(store, "rice undha").text


def test_walk_away_with_cart_records_cash_sale(store, ledger, inventory):
    store.begin_session()
    say(store, "one soap")
    store.end_session()
    assert inventory.get("soap").stock == 9
    assert ledger.summary()["sales"] == 30


def test_goodbye_with_empty_cart_ends(store):
    store.begin_session()
    r = say(store, "bye")
    assert r.end and "come again" in r.text
