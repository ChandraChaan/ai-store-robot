def test_bill_lifecycle(ledger):
    bill_id = ledger.create_bill([("coke", 2, 80), ("chips", 1, 20)], visit_id="v1")
    bill = ledger.get_bill(bill_id)
    assert bill["status"] == "pending" and bill["total"] == 100
    ledger.settle_bill(bill_id, "paid", method="upi", ref="UTR")
    assert ledger.get_bill(bill_id)["status"] == "paid"
    assert ledger.summary()["sales"] == 100 and ledger.summary()["bills"] == 1
    # settling twice is a no-op
    ledger.settle_bill(bill_id, "paid", method="upi")
    assert ledger.summary()["sales"] == 100


def test_bill_on_khata_and_unpaid(ledger):
    b1 = ledger.create_bill([("rice", 1, 60)])
    ledger.settle_bill(b1, "khata", customer_name="Ramu")
    assert ledger.balance("Ramu") == 60 and ledger.get_bill(b1)["customer"] == "Ramu"
    b2 = ledger.create_bill([("soap", 1, 30)])
    ledger.settle_bill(b2, "unpaid", ref="walked away")
    s = ledger.summary()
    assert s["unpaid"] == 30 and s["sales"] == 30      # unpaid sales still reduce stock / count as sales lines
    assert [b["status"] for b in ledger.bills()] == ["unpaid", "khata"]
