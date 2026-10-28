def test_find_exact_and_fuzzy(inventory):
    assert inventory.find("coke").key == "coke"
    assert inventory.find("thums up").key == "thums_up"
    assert inventory.find("బియ్యం").key == "rice"
    assert inventory.find("biscit").key == "biscuit"       # typo -> fuzzy
    assert inventory.find("laptop") is None


def test_find_all_longest_alias_wins(inventory):
    hits = inventory.find_all("thums up and coke")
    assert [h[0].key for h in hits] == ["thums_up", "coke"]


def test_stock_changes_persist(inventory):
    inventory.reduce_stock("coke", 3)
    assert inventory.get("coke").stock == 7
    inventory.add_stock("coke", 10)
    reloaded = type(inventory)(inventory.path)
    assert reloaded.get("coke").stock == 17


def test_low_stock(inventory):
    keys = {p.key for p in inventory.low_stock()}
    assert "thums_up" in keys and "coke" not in keys
