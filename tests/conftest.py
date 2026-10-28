import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from store.inventory import Inventory  # noqa: E402
from store.ledger import Ledger  # noqa: E402


@pytest.fixture
def inventory(tmp_path):
    src = json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))
    fixed = {"coke": 10, "sprite": 6, "thums_up": 0, "chips": 15, "biscuit": 30, "maggi": 12, "rice": 20,
             "sugar": 8, "soap": 10, "milk": 10, "oil": 6}
    for item in src["products"]:
        item["stock"] = fixed.get(item["key"], item["stock"])
    path = tmp_path / "products.json"
    path.write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
    return Inventory(path)


@pytest.fixture
def ledger(tmp_path):
    lg = Ledger(tmp_path / "store.db")
    yield lg
    lg.close()
