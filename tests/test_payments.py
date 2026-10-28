from shop.payments import Payments, qr_svg, upi_link


class S:
    upi_id = "shop@okaxis"
    upi_payee_name = "Test Shop"
    store_name = "Test Shop"
    currency = "INR"
    payment_timeout_seconds = 1
    accept_cash = True


def test_upi_link_and_qr():
    link = upi_link("shop@okaxis", "Test Shop", 100, "bill 1")
    assert link.startswith("upi://pay?") and "am=100.00" in link and "pa=shop%40okaxis" in link
    assert "<svg" in qr_svg(link)


def test_request_and_settle(ledger):
    settled = []
    pay = Payments(S(), on_settled=settled.append)
    req = pay.request(bill_id=7, amount=55)
    assert pay.current is req and req.qr_svg and req.status == "pending"
    assert pay.mark_paid(method="upi", ref="UTR1") is req
    assert req.status == "paid" and pay.current is None and settled == [req]
    assert pay.mark_paid() is None                      # nothing pending


def test_cancel():
    pay = Payments(S())
    pay.request(1, 10)
    assert pay.cancel("left").status == "cancelled" and pay.current is None
