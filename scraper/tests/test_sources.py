import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sources  # noqa: E402
import store  # noqa: E402
from products import PRODUCTS, product_key  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def test_ptt_current():
    prices = sources.parse_ptt((FIX / "ptt_current.xml").read_text())
    assert len(prices) == 9
    assert {p.product for p in prices} <= set(PRODUCTS)
    diesel = next(p for p in prices if p.product == "diesel")
    assert diesel.price == 42.94 and diesel.effective == datetime(2026, 10, 9, 5, 0)


def test_ptt_history_dates_are_month_first():
    prices = sources.parse_ptt((FIX / "ptt_2026-04-15.xml").read_text())
    assert prices, "GetOilPrice fixture should hold prices"
    # PTT answers "04/11/2026 5:00:00 AM" = 11 April, the last change on or before 15 April
    assert all(p.effective == datetime(2026, 4, 11, 5, 0) for p in prices)


def test_ptt_skips_products_listed_at_zero():
    xml = (FIX / "ptt_current.xml").read_text().replace("&lt;PRICE&gt;49.79&lt;/PRICE&gt;", "&lt;PRICE&gt;0.00&lt;/PRICE&gt;")
    prices = sources.parse_ptt(xml)
    assert len(prices) == 8 and all(p.price > 0 for p in prices)


def test_bangchak_today():
    prices = sources.parse_bangchak((FIX / "bangchak.json").read_text())
    assert len(prices) == 8
    assert all(not p.product.startswith("other:") for p in prices)
    assert all(p.tomorrow is None for p in prices)
    assert prices[0].effective == datetime(2026, 10, 9, 5, 0)


def test_bangchak_tomorrow_announced():
    data = json.loads((FIX / "bangchak.json").read_text())
    oils = json.loads(data[0]["OilList"])
    oils[1]["PriceTomorrow"] = oils[1]["PriceToday"] + 0.5
    data[0]["OilList"] = json.dumps(oils, ensure_ascii=False)
    data[0]["OilRemark2"] = "ราคามีผล ณ วันที่ 20 ต.ค. 69 เวลา 05.00 น."  # tomorrow, seen from 19 Oct
    prices = sources.parse_bangchak(json.dumps(data, ensure_ascii=False))
    assert prices[1].tomorrow == round(oils[1]["PriceToday"] + 0.5, 2)
    assert prices[1].effective is None  # today's price started at an earlier, unknown change
    assert prices[0].tomorrow is None


def test_product_names_from_both_brands():
    expected = {
        "ดีเซล B20": "diesel_b20", "ดีเซล": "diesel", "ไฮดีเซล S": "diesel",
        "Super Power Diesel": "premium_diesel", "ไฮ พรีเมียม ดีเซล พลัส": "premium_diesel",
        "เบนซินแก๊สโซฮอล์ E20": "gasohol_e20", "แก๊สโซฮอล์ E20 S EVO": "gasohol_e20",
        "แก๊สโซฮอล์ E85 S EVO": "gasohol_e85", "เบนซินแก๊สโซฮอล์ 91": "gasohol_91",
        "แก๊สโซฮอล์ 91 S EVO": "gasohol_91", "เบนซินแก๊สโซฮอล์ 95": "gasohol_95",
        "แก๊สโซฮอล์ 95 S EVO": "gasohol_95", "Super Power GSH95": "premium_gasohol_95",
        "เบนซิน": "benzine_95", "Super Power X99": "premium_98", "ไฮ พรีเมียม 98 พลัส": "premium_98",
    }
    for name, key in expected.items():
        assert product_key(name) == key, name
    assert product_key("น้ำมันใหม่") == "other:น้ำมันใหม่"


def test_upsert_is_idempotent():
    prices = sources.parse_ptt((FIX / "ptt_current.xml").read_text())
    rows = {}
    assert store.upsert(rows, date(2026, 10, 19), prices) == 9
    assert store.upsert(rows, date(2026, 10, 19), prices) == 0
