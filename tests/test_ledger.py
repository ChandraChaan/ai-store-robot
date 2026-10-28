def test_credit_and_payment_flow(ledger):
    assert ledger.balance("Ramu") == 0
    bal = ledger.add_credit("Ramu", [("rice", 1, 60), ("sugar", 1, 45)])
    assert bal == 105
    assert ledger.record_payment("ramu", 50) == 55          # case-insensitive customer match
    assert ledger.balance("Ramu") == 55
    balances = ledger.all_balances()
    assert balances[0]["name"] == "Ramu" and balances[0]["balance"] == 55


def test_sales_and_summary(ledger):
    ledger.record_sale([("coke", 2, 80)])
    ledger.add_credit("Sita", [("maggi", 2, 28)])
    ledger.record_payment("Sita", 10)
    s = ledger.summary()
    assert s["sales"] == 80 and s["credit"] == 28 and s["payments"] == 10
    assert s["total_outstanding"] == 18
    assert s["transactions"] == 3
    assert ledger.recent(1)[0]["kind"] == "payment"
