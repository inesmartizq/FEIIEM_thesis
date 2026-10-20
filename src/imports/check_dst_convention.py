"""
One-off, read-only diagnostic: figure out whether Nord Pool's "...UTC"
timestamp columns actually observe real CET/CEST daylight saving, or use a
flat, fixed offset (e.g. always CET/UTC+1) that never switches.

How it works: on a real DST spring-forward day (last Sunday of March), true
local wall-clock time has NO 02:00-03:00 hour at all (clocks jump straight
from 02:00 to 03:00) — a genuinely DST-aware file would have 23 rows that
day for a given zone, and NO row labeled "02:00". On a real DST fall-back
day (last Sunday of October), the local 02:00-03:00 hour happens TWICE —
a genuinely DST-aware file would have 25 rows that day.

If instead you see 24 rows on BOTH days (no skip, no repeat), the source is
using a flat, non-DST-varying offset, and the fix in dataframe_building.py
needs to change from full Europe/Copenhagen tz-aware conversion to a simple
fixed offset instead.

Run this directly (no arguments): python check_dst_convention.py
It only reads your existing processed CSVs — writes nothing, changes nothing.
"""

from pathlib import Path
from datetime import date, timedelta

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/imports/<this file> -> project root
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def _last_sunday(year: int, month: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    d = next_month - timedelta(days=1)
    while d.weekday() != 6:  # Sunday
        d -= timedelta(days=1)
    return d


def check_source(label: str, path: Path, time_col: str, area_col: str, years: range):
    print(f"\n{'=' * 70}\n{label}: {path}\n{'=' * 70}")
    if not path.exists():
        print("  FILE NOT FOUND — skipping.")
        return

    df = pd.read_csv(path, usecols=[time_col, area_col])
    # The raw column's date portion is the real CET calendar date (it's the
    # bogus-offset-but-correct-wall-clock string) — just take the first 10
    # characters as YYYY-MM-DD, no datetime parsing needed for this check.
    df["_date"] = df[time_col].astype(str).str[:10]

    for year in years:
        spring = _last_sunday(year, 3)
        fall = _last_sunday(year, 10)
        for label_name, d in [("SPRING-FORWARD", spring), ("FALL-BACK", fall)]:
            day_str = d.isoformat()
            sub = df[df["_date"] == day_str]
            for area in sorted(sub[area_col].unique()) if not sub.empty else []:
                n = (sub[area_col] == area).sum()
                verdict = {23: "23 -> real DST (hour skipped)",
                           24: "24 -> FLAT OFFSET (no DST switch)",
                           25: "25 -> real DST (hour repeated)"}.get(n, f"{n} -> UNEXPECTED")
                print(f"  {year} {label_name:15s} {day_str}  {area}: {n:3d} rows   [{verdict}]")
            if sub.empty:
                print(f"  {year} {label_name:15s} {day_str}: no rows found (out of range?)")


if __name__ == "__main__":
    check_source(
        "mfrr", PROCESSED_DIR / "mfrr" / "mfrr_DK1_DK2_2021_2025_MW.csv",
        "DeliveryStartUTC", "Area", range(2021, 2026),
    )
    check_source(
        "da_forecasts_and_actual", PROCESSED_DIR / "da_forecasts" / "da_forecasts_and_actual.csv",
        "time_utc", "area", range(2022, 2026),
    )
    print("\nDone. Paste this whole output back — it tells us definitively "
          "which timezone model is correct.")