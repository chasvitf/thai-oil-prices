"""Fill data/daily.csv with past PTT prices (GetOilPrice returns the prices in effect on a day).

usage: python backfill.py 2025-10-19 2026-10-18     (one request per day, 1 per second)
Bangchak only publishes today's and tomorrow's price, so its history starts when update.py first ran.
"""
import sys
import time
from datetime import date, timedelta

import sources
import store


def main() -> None:
    start, end = (date.fromisoformat(a) for a in sys.argv[1:3])
    rows = store.load()
    day, total, errors = start, 0, 0
    while day <= end:
        try:
            total += store.upsert(rows, day, sources.fetch_ptt(day))
        except Exception as err:
            errors += 1
            print(f"{day}: {err}", file=sys.stderr)
        if day.day == 1:
            print(day, total, "rows so far", flush=True)
            store.save(rows)
        day += timedelta(days=1)
        time.sleep(1)  # be gentle with PTT's server
    store.save(rows)
    print(f"done: {total} rows added or changed, {errors} days failed")


if __name__ == "__main__":
    main()
