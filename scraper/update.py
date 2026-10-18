"""Daily job: fetch today's prices from PTT and Bangchak, update the data files, and send an
alert when a brand announces tomorrow's price (if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set).

usage: python update.py            (GitHub Actions runs this at 05:30 and 19:00 Bangkok time)
"""
import json
import os
import sys
from datetime import datetime, timedelta

import requests

import sources
import store


def main() -> int:
    day = sources.bangkok_today()
    prices, failed = [], []
    for name, fetch in (("ptt", sources.fetch_ptt), ("bangchak", sources.fetch_bangchak)):
        try:
            got = fetch()
            if not got:
                raise ValueError("no prices in the response")
            prices += got
            print(f"{name}: {len(got)} products")
        except Exception as err:  # one brand down should not stop the other
            failed.append(name)
            print(f"{name}: FAILED {err}", file=sys.stderr)
    if not prices:
        return 1

    unknown = sorted({p.name for p in prices if p.product.startswith("other:")})
    if unknown:
        print("new product names (add them to products.py):", ", ".join(unknown), file=sys.stderr)

    rows = store.load()
    changed = store.upsert(rows, day, prices)
    store.save(rows)
    latest = store.write_latest(prices, datetime.utcnow() + timedelta(hours=7), day)
    store.write_excel(rows, latest)
    print(f"{day}: {changed} rows new or changed, {len(rows)} rows in daily.csv")

    alert = tomorrow_alert(latest)
    if alert:
        print(alert)
        notify(alert, day.isoformat())
    return 2 if failed else 0


def tomorrow_alert(latest: dict) -> str:
    lines = []
    for brand in latest["brands"].values():
        for p in brand["products"]:
            if p["tomorrow"] is not None:
                diff = p["tomorrow"] - p["price"]
                lines.append(f"{brand['name']} {p['label']}: {p['price']:.2f} → {p['tomorrow']:.2f} ({diff:+.2f})")
    if not lines:
        return ""
    return "⛽ ราคาน้ำมันพรุ่งนี้ 05:00 น. เปลี่ยน\n" + "\n".join(lines)


def notify(text: str, day: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("(Telegram not configured, alert only printed)")
        return
    sent = store.DATA / "last_alert.json"
    if sent.exists() and json.loads(sent.read_text()).get("text") == text:
        print("(alert already sent)")
        return
    res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=30,
                        json={"chat_id": chat, "text": text})
    res.raise_for_status()
    sent.write_text(json.dumps({"day": day, "text": text}, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
