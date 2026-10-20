"""
Downloads daily Intraday Hourly Statistics from Nord Pool's data portal API,
for a date range and a set of bidding areas, caching each (day, area) response
locally, then compiles everything into one CSV. Also includes a terminal-only
feature/gap analysis of the resulting dataset.

Usage:
    pip install requests pandas
    python nordpool_intraday_export.py

Edit the CONFIG section below before running.
"""

import json
import time
import base64
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# Anchor all paths to the project root (two levels above this file:
# src/imports/ -> project), so this works from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/imports/<this file> -> project root

# ----------------------- CONFIG -----------------------
# Padded 1 day on each side vs. the true 2022-2025 analysis window, same
# reasoning as balancing_pipeline.py / import_da_forecasts_pipeline.py: the
# raw "...UTC" columns here are actually CET-labeled (fixed downstream in
# dataframe_building.py), so the true UTC boundary hours of the window fall
# just outside a CET-labeled request range unless padded. Without this,
# 2025-12-31's last 2 hours (UTC) were missing from the built dataframe
# (confirmed: id_* columns' last_non_null stopped at 21:00 UTC instead of
# 23:00 UTC before this fix).
START_DATE = date(2020, 12, 31)    # first day to pull (inclusive)
END_DATE = date(2026, 1, 1)        # last day to pull (inclusive)
AREAS = ["DK1", "DK2"]
CACHE_DIR = PROJECT_ROOT / "data/raw/intraday/intraday_stats"   # raw JSON, one file per (day, area)

# NOTE: this used to have an extra "intraday_stats" folder segment
# (data/processed/intraday/intraday_stats/...), which didn't match what
# dataframe_building.py's SOURCES["intraday"]["path"] actually looks for
# (data/processed/intraday/...) — so a completed run of this script would
# silently produce a file dataframe_building.py could never find, logging
# "[intraday] SKIPPED — file not found" instead of an error. Fixed to match
# the same one-folder-per-category convention every other source here uses
# (da_forecasts/, day_ahead/, etc.).
OUTPUT_CSV = PROJECT_ROOT / "data/processed/intraday/intraday_DK1_DK2_2021_2025.csv"
REQUEST_DELAY_SECONDS = 1.0          # base delay between requests
MAX_RETRIES_PER_REQUEST = 5          # for 429s before giving up on that (day, area)

# Paste a fresh bearer token here (with or without the leading "Bearer ").
# The script will also ask you interactively if/when this one expires.
BEARER_TOKEN = "PASTE_YOUR_TOKEN_HERE"
# --------------------------------------------------------

BASE_URL = "https://dataportal-api.nordpoolgroup.com/api/IntradayMarketStatistics/hourly"


def _clean_token(raw: str) -> str:
    """Strip an optional leading 'Bearer ' (any case) and surrounding
    whitespace, so pasting the token straight out of DevTools works either
    way."""
    raw = raw.strip()
    if raw[:7].lower() == "bearer ":
        raw = raw[7:].strip()
    return raw


def _decode_jwt_exp(token: str) -> datetime | None:
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    except Exception:
        return None


def get_headers(token: str) -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://data.nordpoolgroup.com",
        "Referer": "https://data.nordpoolgroup.com/",
        "Authorization": f"Bearer {token}",
    }


def prompt_for_new_token() -> str:
    print("\n" + "=" * 60)
    print("Access token expired or was rejected (401).")
    print("Grab a fresh one from DevTools (Network tab -> a 'hourly?date=...'")
    print("request -> Headers -> Request Headers -> authorization),")
    print("and paste it below (with or without 'Bearer ').")
    print("=" * 60)
    return _clean_token(input("New token: "))


def fetch_day_area(day: date, area: str, session: requests.Session, token_holder: dict) -> dict | None:
    """Fetch one (day, area)'s data, using local cache if already downloaded."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{day.isoformat()}_{area}.json"

    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    params = {"date": day.isoformat(), "deliveryArea": area}

    retries = 0
    while retries <= MAX_RETRIES_PER_REQUEST:
        print(f"  -> requesting {day} {area}", flush=True)
        try:
            resp = session.get(
                BASE_URL,
                headers=get_headers(token_holder["token"]),
                params=params,
                timeout=15,
            )
        except requests.exceptions.RequestException as e:
            print(f"     connection error ({e!r}), retrying in 5s...", flush=True)
            time.sleep(5)
            retries += 1
            continue

        if resp.status_code == 200:
            data = resp.json()
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            print(f"     ok ({day} {area})", flush=True)
            return data

        if resp.status_code == 401:
            print(f"     401 (token expired) ({day} {area})", flush=True)
            token_holder["token"] = prompt_for_new_token()
            continue

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else min(60, 5 * (2 ** retries))
            print(f"     429, waiting {wait:.0f}s...", flush=True)
            time.sleep(wait)
            retries += 1
            continue

        print(f"     HTTP {resp.status_code} — skipping ({day} {area})", flush=True)
        return None

    print(f"     gave up on {day} {area} after {MAX_RETRIES_PER_REQUEST} retries (429s)", flush=True)
    return None


def flatten(data: dict) -> list[dict]:
    """Turn one (day, area)'s nested JSON into flat rows, one per hour."""
    rows = []
    if not data:
        return rows

    area = data.get("deliveryArea")
    delivery_date = data.get("deliveryDateCET")
    price_unit = data.get("priceUnit")
    volume_unit = data.get("volumeUnit")

    for h in data.get("hourlyStatistics", []):
        rows.append({
            "DeliveryDateCET": delivery_date,
            "Area": area,
            "DeliveryStartUTC": h.get("deliveryStart"),
            "DeliveryEndUTC": h.get("deliveryEnd"),
            "HighPrice": h.get("highPrice"),
            "LowPrice": h.get("lowPrice"),
            "OpenPrice": h.get("openPrice"),
            "ClosePrice": h.get("closePrice"),
            "VWAP": h.get("averagePrice"),
            "VWAP1H": h.get("averagePriceLast1H"),
            "VWAP3H": h.get("averagePriceLast3H"),
            "TransactionVolume_MWh": h.get("volume"),
            "BuyVolume_MWh": h.get("buyVolume"),
            "SellVolume_MWh": h.get("sellVolume"),
            "OpenTradeTime": h.get("openTradeTime"),
            "CloseTradeTime": h.get("closeTradeTime"),
            "PriceUnit": price_unit,
            "VolumeUnit": volume_unit,
        })
    return rows


def daterange(start: date, end: date):
    days = (end - start).days
    for i in range(days + 1):
        yield start + timedelta(days=i)


def _resample_intraday_to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse to exactly one row per (Area, clock-hour). A no-op when the
    data is already hourly (each group has exactly 1 row and every
    aggregation below just returns that row's own value unchanged) — safe
    to always apply, in case any period in the range has sub-hourly data
    (e.g. if intraday follows day-ahead's Oct 2025 15-min MTU switch).

    Different columns need genuinely different aggregations, not a blanket
    mean:
      - HighPrice/LowPrice: max/min across sub-periods (the true hourly
        high/low IS the max/min of the sub-period highs/lows)
      - OpenPrice/OpenTradeTime: from the earliest sub-period
      - ClosePrice/CloseTradeTime: from the latest sub-period
      - VWAP/VWAP1H/VWAP3H: volume-weighted recombination of the
        sub-period VWAPs (weighted by TransactionVolume_MWh), not a plain
        mean, since VWAP is itself already a volume-weighted quantity
      - TransactionVolume_MWh/BuyVolume_MWh/SellVolume_MWh: SUM, not mean —
        these are confirmed MWh (energy), which is additive across time,
        unlike the MW (power) columns in the other pipelines
    """
    df = df.copy()
    df["HourFloor"] = df["DeliveryStartUTC"].dt.floor("1h")

    def _vwap(group: pd.DataFrame, col: str) -> float:
        w = group["TransactionVolume_MWh"]
        if w.sum() == 0:
            return group[col].mean()
        return (group[col] * w).sum() / w.sum()

    rows = []
    for (area, hour), group in df.groupby(["Area", "HourFloor"], sort=False):
        group = group.sort_values("DeliveryStartUTC")
        rows.append({
            "DeliveryDateCET": group["DeliveryDateCET"].iloc[0],
            "Area": area,
            "DeliveryStartUTC": hour,
            "DeliveryEndUTC": hour + pd.Timedelta(hours=1),
            "HighPrice": group["HighPrice"].max(),
            "LowPrice": group["LowPrice"].min(),
            "OpenPrice": group["OpenPrice"].iloc[0],
            "ClosePrice": group["ClosePrice"].iloc[-1],
            "VWAP": _vwap(group, "VWAP"),
            "VWAP1H": _vwap(group, "VWAP1H"),
            "VWAP3H": _vwap(group, "VWAP3H"),
            "TransactionVolume_MWh": group["TransactionVolume_MWh"].sum(),
            "BuyVolume_MWh": group["BuyVolume_MWh"].sum(),
            "SellVolume_MWh": group["SellVolume_MWh"].sum(),
            "OpenTradeTime": group["OpenTradeTime"].iloc[0],
            "CloseTradeTime": group["CloseTradeTime"].iloc[-1],
            "PriceUnit": group["PriceUnit"].iloc[0],
            "VolumeUnit": group["VolumeUnit"].iloc[0],
        })
    return pd.DataFrame(rows).sort_values(["DeliveryStartUTC", "Area"]).reset_index(drop=True)


def download_intraday():
    session = requests.Session()
    all_rows = []
    failed = []

    token = _clean_token(BEARER_TOKEN)
    if token == "PASTE_YOUR_TOKEN_HERE" or not token:
        token = prompt_for_new_token()
    exp = _decode_jwt_exp(token)
    if exp:
        remaining = (exp - datetime.now(timezone.utc)).total_seconds()
        print(f"Token expires at {exp.isoformat()} (~{remaining/60:.0f} min from now).")
        if remaining < 0:
            print("That token is already expired.")
            token = prompt_for_new_token()

    token_holder = {"token": token}

    days = list(daterange(START_DATE, END_DATE))
    total_requests = len(days) * len(AREAS)
    print(f"Fetching {len(days)} days x {len(AREAS)} areas = {total_requests} requests...")

    i = 0
    for day in days:
        for area in AREAS:
            i += 1
            data = fetch_day_area(day, area, session, token_holder)
            if data is None:
                failed.append((day, area))
            else:
                all_rows.extend(flatten(data))
            if i % 100 == 0:
                print(f"--- progress: {i}/{total_requests} requests processed ---", flush=True)
            time.sleep(REQUEST_DELAY_SECONDS)

    if not all_rows:
        print("No data retrieved — aborting.")
        return

    df = pd.DataFrame(all_rows)
    df["DeliveryStartUTC"] = pd.to_datetime(df["DeliveryStartUTC"])
    df["DeliveryEndUTC"] = pd.to_datetime(df["DeliveryEndUTC"])
    df = df.sort_values(["DeliveryStartUTC", "Area"]).reset_index(drop=True)

    # Check whether any sub-hourly rows actually exist before/after resampling,
    # so the log is honest about whether this step did anything.
    rows_before = len(df)
    df = _resample_intraday_to_hourly(df)
    rows_after = len(df)
    if rows_after < rows_before:
        print(f"\nResampled {rows_before} raw rows -> {rows_after} hourly rows "
              f"({rows_before - rows_after} sub-hourly rows were collapsed).")
    else:
        print(f"\nAll {rows_before} rows were already hourly — resampling was a no-op.")

    out_path = Path(OUTPUT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Done. Wrote {len(df)} rows to {out_path}")

    if failed:
        print(f"\n{len(failed)} (day, area) pair(s) failed to download:")
        for d, a in failed:
            print(f"  - {d} {a}")
        print("Re-run the script and it will retry only the missing ones (cache skips the rest).")


# ============================================================
# ANALYTICS — feature overview + gap detection (terminal only)
# ============================================================

def analyze_intraday():
    """Print a feature overview and gap report for the processed intraday
    CSV. Terminal output only — no plots, no extra files."""
    p = Path(OUTPUT_CSV)
    if not p.exists():
        print(f"[skip] file not found: {p} — run download_intraday() first.")
        return

    df = pd.read_csv(p)
    df["DeliveryStartUTC"] = pd.to_datetime(df["DeliveryStartUTC"], utc=True)

    print(f"\n{'=' * 70}")
    print("INTRADAY (Nord Pool): FEATURE OVERVIEW")
    print("=" * 70)
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"Columns: {list(df.columns)}")
    print(f"Data starts: {df['DeliveryStartUTC'].min()}")
    print(f"Data ends:   {df['DeliveryStartUTC'].max()}")

    for area in AREAS:
        n = (df["Area"] == area).sum()
        print(f"  {area}: {n} rows")

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if numeric_cols:
        print("\nSummary statistics:")
        print(df[numeric_cols].describe())

    print("\nFirst 5 rows:")
    print(df.head())

    print("\nMissing values per column:")
    print(df.isna().sum())

    print(f"\nPriceUnit values: {df['PriceUnit'].unique().tolist()}")
    print(f"VolumeUnit values: {df['VolumeUnit'].unique().tolist()}")

    # gap detection — expected hourly resolution
    print(f"\n{'-' * 70}")
    print("GAP DETECTION (expected frequency: 1h)")
    print("-" * 70)
    for area in AREAS:
        sub = df[df["Area"] == area].sort_values("DeliveryStartUTC")
        if sub.empty:
            print(f"  {area}: no data at all")
            continue
        expected = pd.date_range(sub["DeliveryStartUTC"].min(), sub["DeliveryStartUTC"].max(), freq="1h")
        actual = pd.DatetimeIndex(sub["DeliveryStartUTC"].unique())
        missing = expected.difference(actual)
        pct_missing = 100 * len(missing) / len(expected) if len(expected) else 0
        print(f"  {area}: {len(expected)} expected, {len(missing)} missing ({pct_missing:.2f}%)")

        if len(missing) > 0:
            missing_sorted = missing.sort_values()
            gaps = []
            gap_start = missing_sorted[0]
            prev = missing_sorted[0]
            step = pd.Timedelta("1h")
            for ts in missing_sorted[1:]:
                if ts - prev > step:
                    gaps.append((gap_start, prev))
                    gap_start = ts
                prev = ts
            gaps.append((gap_start, prev))

            print(f"    {len(gaps)} contiguous gap range(s):")
            for g_start, g_end in gaps[:15]:
                print(f"      {g_start}  ->  {g_end}")
            if len(gaps) > 15:
                print(f"      ... and {len(gaps) - 15} more")


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    RUN_DOWNLOAD = True     # extending range with the padded START/END_DATE above; already-cached days are skipped
    RUN_ANALYTICS = True    # terminal-only feature + gap report

    if RUN_DOWNLOAD:
        download_intraday()

    if RUN_ANALYTICS:
        analyze_intraday()


if __name__ == "__main__":
    main()