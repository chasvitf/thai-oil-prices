"""Fetch Bangkok retail fuel prices from PTT and Bangchak.

PTT:      official public SOAP web service https://orapiweb.pttor.com/oilservice/OilPrice.asmx
          (CurrentOilPrice = prices now, GetOilPrice = prices in effect on a given day)
Bangchak: the JSON its own price page loads, https://oil-price.bangchak.co.th/ApiOilPrice2/th
          (today's price and, once announced, tomorrow's)

Parsing is kept separate from fetching so tests can run on saved responses.
"""
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

import requests

from products import product_key

USER_AGENT = "thai-oil-prices/1.0 (+https://github.com/chasvitf/thai-oil-prices)"
PTT_URL = "https://orapiweb.pttor.com/oilservice/OilPrice.asmx"
BANGCHAK_URL = "https://oil-price.bangchak.co.th/ApiOilPrice2/th"
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
MONTH_RE = "|".join(re.escape(m) for m in THAI_MONTHS)


@dataclass
class Price:
    brand: str               # "ptt" | "bangchak"
    product: str             # key from products.PRODUCTS (or "other:<name>")
    name: str                # the brand's own product name
    price: float             # baht per litre, Bangkok retail
    effective: Optional[datetime]  # when this price started (Bangkok time), None if unknown
    tomorrow: Optional[float] = None  # announced price for tomorrow, if the brand publishes it


# ---------- PTT ----------

def _soap(action: str, body: str) -> str:
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        f'<{action} xmlns="http://www.pttor.com">{body}</{action}>'
        "</soap:Body></soap:Envelope>"
    )
    res = requests.post(PTT_URL, data=envelope.encode(), timeout=30, headers={
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"http://www.pttor.com/{action}"',
        "User-Agent": USER_AGENT,
    })
    res.raise_for_status()
    return res.text


def parse_ptt(xml_text: str) -> List[Price]:
    """The SOAP result is itself an XML document (PTTOR_DS > FUEL) sent as an escaped string."""
    root = ET.fromstring(xml_text)
    result = next((el.text for el in root.iter() if el.tag.endswith("Result")), None)
    if not result:
        return []
    prices = []
    for fuel in ET.fromstring(result).iter("FUEL"):
        name = (fuel.findtext("PRODUCT") or "").strip()
        value = fuel.findtext("PRICE")
        # PTT lists a product it is not selling at 0.00 (Super Power X99, 4-22 Jun 2026)
        if not name or not value or float(value) <= 0:
            continue
        prices.append(Price("ptt", product_key(name), name, float(value), _ptt_date(fuel.findtext("PRICE_DATE"))))
    return prices


def _ptt_date(text: str) -> datetime:
    # CurrentOilPrice: "2026-10-09T05:00"; GetOilPrice: "04/11/2026 5:00:00 AM" (month first)
    text = text.strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ValueError(f"unknown PTT date format: {text!r}")


def fetch_ptt(day: Optional[date] = None) -> List[Price]:
    """Prices now, or the prices in effect on `day`."""
    if day is None:
        return parse_ptt(_soap("CurrentOilPrice", "<Language>th</Language>"))
    body = f"<Language>th</Language><DD>{day.day}</DD><MM>{day.month}</MM><YYYY>{day.year}</YYYY>"
    return parse_ptt(_soap("GetOilPrice", body))


# ---------- Bangchak ----------

def parse_bangchak(json_text: str) -> List[Price]:
    data = json.loads(json_text)[0]
    effective = _bangchak_effective(data.get("OilRemark2") or "") or _buddhist_date(data["OilPriceDate"])
    today = _buddhist_date(data["OilDateNow"]).date()
    prices = []
    for item in json.loads(data["OilList"]):
        name = item["OilName"].strip()
        now, tomorrow = float(item["PriceToday"]), float(item["PriceTomorrow"])
        # Once tomorrow's price is announced, OilRemark2 already names tomorrow as the
        # effective date; today's price then started at an earlier change we don't know.
        start = effective if effective.date() <= today else None
        prices.append(Price("bangchak", product_key(name), name, now, start,
                            tomorrow if abs(tomorrow - now) > 0.001 else None))
    return prices


def _buddhist_date(text: str) -> datetime:
    d, m, y = (int(x) for x in text.split("/"))
    return datetime(y - 543, m, d)


def _bangchak_effective(remark: str) -> Optional[datetime]:
    # "ราคามีผล ณ วันที่ 9 ต.ค. 69 เวลา 05.00 น." (Buddhist year, 2 or 4 digits)
    m = re.search(rf"(\d{{1,2}})\s*({MONTH_RE})\s*(\d{{2,4}})(?:\D*?(\d{{1,2}})[.:](\d{{2}}))?", remark)
    if not m:
        return None
    year = int(m.group(3))
    year = (year + 2500 if year < 100 else year) - 543
    hour, minute = int(m.group(4) or 5), int(m.group(5) or 0)
    return datetime(year, THAI_MONTHS.index(m.group(2)) + 1, int(m.group(1)), hour, minute)


def fetch_bangchak() -> List[Price]:
    res = requests.get(BANGCHAK_URL, timeout=30, headers={"User-Agent": USER_AGENT})
    res.raise_for_status()
    return parse_bangchak(res.text)


def bangkok_today() -> date:
    return (datetime.utcnow() + timedelta(hours=7)).date()
