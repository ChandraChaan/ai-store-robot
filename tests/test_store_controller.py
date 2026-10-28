import pytest

from brain import nlu
from perception.counter import CounterItem
from shop.controller import StoreController
from shop.payments import Payments


class S:
    language = "en"
    store_name = "Test Store"
    accept_cash = True
    upi_id = ""
    upi_payee_name = ""
    currency = "INR"
    payment_timeout_seconds = 60


class SUpi(S):
    upi_id = "shop@okaxis"


def make_store(inventory, ledger, settings):
    payments = Payments(settings)
    store = StoreController(inventory, ledger, payments=payments, settings=settings)
    # same glue as VisitManager: a settled payment finalises the bill
    payments.on_settled = lambda req: store.settle_bill(req.bill_id, "paid", method=req.method, ref=req.ref)
    return store


@pytest.fixture
def store(inventory, ledger):
    return make_store(inventory, ledger, S())


@pytest.fixture
def upi_store(inventory, ledger):
    return make_store(inventory, ledger, SUpi())


def say(store, text):
    return store.handle(nlu.parse(text, store.inventory))


def counter(store, *pairs):
    items = [CounterItem(k, store.inventory.get(k).name, 0.95, (0, 0, 1, 1), q) for k, q in pairs]
    return store.set_counter_items(items)


# ---------------------------------------------------------------- voice-only flows (no UPI configured)
def test_cash_purchase_flow(store, ledger, inventory):
    assert "Welcome" in store.begin_session()
    r = say(store, "2 coke and 1 chips")
    assert "Total 100" in r.text and not r.end
    r = say(store, "that's all")
    assert "Cash, or on your khata" in r.text and store.awaiting_payment
    r = say(store, "cash")
    assert r.end and "100 rupees cash" in r.text
    assert inventory.get("coke").stock == 8 and inventory.get("chips").stock == 14
    assert ledger.summary()["sales"] == 100 and ledger.bills()[0]["status"] == "paid"


def test_credit_flow_asks_name_then_records(store, ledger):
    store.begin_session()
    r = say(store, "ek kilo chawal khata mein likh do")
    assert "What is your name" in r.text
    r = say(store, "Ramu")
    assert "Okay Ramu" in r.text and not r.end
    r = say(store, "bas")
    assert r.end and "60 rupees added to your khata" in r.text
    assert ledger.balance("Ramu") == 60 and ledger.bills()[0]["status"] == "khata"


def test_done_then_khata_then_name_checks_out(store, ledger):
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


def test_walk_away_with_items_is_unpaid(store, ledger, inventory):
    store.begin_session()
    say(store, "one soap")
    result = store.end_session(items_taken=True)
    assert result["status"] == "unpaid" and inventory.get("soap").stock == 9
    assert ledger.summary()["unpaid"] == 30 and store.session is None


def test_walk_away_leaving_items_is_cancelled(store, ledger, inventory):
    store.begin_session()
    counter(store, ("soap", 1))
    result = store.end_session(items_taken=False)
    assert result["status"] == "cancelled" and inventory.get("soap").stock == 10
    assert ledger.summary()["unpaid"] == 0


def test_goodbye_with_empty_cart_ends(store):
    store.begin_session()
    r = say(store, "bye")
    assert r.end and "come again" in r.text


# ---------------------------------------------------------------- counter camera + UPI
def test_counter_items_build_the_bill(upi_store):
    s = upi_store
    s.begin_session()
    text = counter(s, ("coke", 2), ("chips", 1))
    assert "On the counter" in text and "Total 100" in text
    assert counter(s, ("coke", 2), ("chips", 1)) is None          # unchanged: say nothing
    text = counter(s, ("coke", 2), ("chips", 1), ("soap", 1))
    assert "Total 130" in text


def test_voice_corrects_camera_quantity_and_removes(upi_store):
    s = upi_store
    s.begin_session()
    counter(s, ("coke", 2), ("chips", 1))
    r = say(s, "coke okati")                       # "one coke": camera saw 2, customer says 1
    assert "Okay, 1 bottle Coca-Cola" in r.text and s.session.total == 60
    counter(s, ("coke", 2), ("chips", 1))          # camera still sees 2: voice wins
    assert s.session.total == 60
    r = say(s, "chips vaddu")                      # remove chips
    assert "removed Lays chips" in r.text and s.session.total == 40
    assert counter(s, ("coke", 2), ("chips", 1)) is None and s.session.total == 40


def test_unknown_item_on_counter_is_mentioned(upi_store):
    s = upi_store
    s.begin_session()
    text = s.set_counter_items([CounterItem(None, "unknown item", 0.3, (0, 0, 1, 1), 1)])
    assert "could not recognise" in text


def test_upi_payment_flow(upi_store, ledger, inventory):
    s = upi_store
    s.begin_session()
    counter(s, ("coke", 2))
    r = say(s, "antey")
    assert "scan the qr" in r.text.lower() and not r.end
    req = s.payments.current
    assert req is not None and req.amount == 80 and req.qr_svg
    assert "scan" in say(s, "ok").text.lower()                   # waiting: gentle reminder
    s.payments.mark_paid(method="upi", ref="UTR123")             # dashboard tap / webhook
    assert not s.conversation_active
    bill = ledger.get_bill(req.bill_id)
    assert bill["status"] == "paid" and bill["method"] == "upi" and bill["ref"] == "UTR123"
    assert inventory.get("coke").stock == 8
    result = s.end_session()
    assert result["status"] == "paid"


def test_new_item_while_paying_reopens_bill(upi_store, ledger):
    s = upi_store
    s.begin_session()
    counter(s, ("coke", 1))
    say(s, "antey")
    first_bill = s.session.bill_id
    text = counter(s, ("coke", 1), ("maggi", 1))
    assert "updating the bill" in text and s.payments.current is None and not s.awaiting_payment
    assert ledger.get_bill(first_bill)["status"] == "cancelled"
    r = say(s, "antey")
    assert s.payments.current.amount == 54 and s.session.bill_id != first_bill
    counter(s, ("coke", 1))                                      # customer picks up the maggi: no change while paying
    assert s.payments.current is not None and s.payments.current.amount == 54


def test_khata_during_upi_wait(upi_store, ledger):
    s = upi_store
    s.begin_session()
    s.session.customer_name = "Ramu"
    counter(s, ("rice", 1))
    say(s, "antey")
    r = say(s, "khata lo rasuko")
    assert r.end and ledger.balance("Ramu") == 60 and s.payments.current is None


def test_unpaid_exit_during_upi_wait(upi_store, ledger, inventory):
    s = upi_store
    s.begin_session()
    counter(s, ("soap", 2))
    say(s, "antey")
    result = s.end_session(items_taken=True)
    assert result["status"] == "unpaid" and result["total"] == 60
    assert ledger.summary()["unpaid"] == 60 and inventory.get("soap").stock == 8 and s.payments.current is None
