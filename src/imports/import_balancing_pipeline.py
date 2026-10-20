"""
Downloads DK1/DK2 balancing-market data — Nord Pool mFRR, plus aFRR from
Energinet (pre-PICASSO) and ENTSO-E (post-PICASSO) — and processes it into
clean per-domain CSVs, with a terminal-only feature/gap analysis along the
way.

Structure:
  - One section per data source, each exposing a single download_<source>_*()
    function that does everything for that source (fetch, cache, process to
    its own CSV).
  - An ANALYTICS section reads the two aFRR sources' CSVs and prints a
    feature overview + gap report for each, side by side.
  - A COMBINE section merges the two aFRR sources into one continuous hourly
    series — full column union, NaN wherever a feature genuinely doesn't
    exist for that period (e.g. ENTSO-E's Offered/Unavailable columns don't
    exist in the Energinet era).
  - main() has a RUN CONFIG block where you flip which parts actually run.

DATE PADDING NOTE: NORDPOOL_START_DATE/END_DATE are padded one calendar day
on each side of the actual analysis window (2022-01-01 to 2025-12-31). This
is because Nord Pool's "DeliveryStartUTC" column is actually Europe/
Copenhagen wall-clock CET/CEST (mislabeled as UTC) — dataframe_building.py
converts it to true UTC. Without this padding, requesting exactly
2022-01-01 to 2025-12-31 in CET-labeled terms would miss the true UTC hours
at each end of the window (e.g. the true last UTC hour of 2025-12-31 is
labeled "2026-01-01 00:00" in CET). The padding days are harmless surplus —
dataframe_building.py's grid only keeps rows inside the true UTC analysis
window, so the extra day on each end is simply dropped during the merge.

Usage:
    pip install requests pandas
    python balancing_pipeline.py
"""

import json
import time
import base64
import xml.etree.ElementTree as ET
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# Anchor all paths to the project root (two levels above this file:
# src/imports/ -> project), so this works from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/imports/<this file> -> project root


def daterange(start: date, end: date):
    days = (end - start).days
    for i in range(days + 1):
        yield start + timedelta(days=i)


def resample_to_hourly(df: pd.DataFrame, time_col: str, group_col: str, agg_map: dict, label: str) -> pd.DataFrame:
    """Shared defensive resampling helper. Groups by (group_col, clock-hour)
    and applies agg_map (column -> aggregation function/string) — a no-op
    when the data is already hourly (each group has exactly 1 row, so every
    aggregation just returns that row's own value). Always applied, rather
    than assumed unnecessary, so a resolution change anywhere in the range
    (now or introduced later by the source) is handled automatically instead
    of silently producing wrong output. Prints what it actually found.
    """
    df = df.copy()
    hour_col = "_HourFloor"
    df[hour_col] = df[time_col].dt.floor("1h")
    rows_before = len(df)

    out = df.groupby([group_col, hour_col], sort=False).agg(agg_map).reset_index()
    out = out.rename(columns={hour_col: time_col})
    out = out.sort_values([time_col, group_col]).reset_index(drop=True)

    rows_after = len(out)
    if rows_after < rows_before:
        print(f"{label} Resampled {rows_before} raw rows -> {rows_after} hourly rows "
              f"({rows_before - rows_after} sub-hourly rows collapsed — a resolution change was detected).")
    else:
        print(f"{label} All {rows_before} rows were already hourly — resampling was a no-op.")

    return out


# ============================================================
# NORD POOL — mFRR (Manual Frequency Restoration Reserve)
# ============================================================
# Already downloaded in full and combined to CSV. Left fully working here in
# case a backfill or new date range is ever needed — see RUN_NORDPOOL_MFRR
# in main() to toggle it back on.

# Padded one day on each side of the true analysis window (2022-01-01 to
# 2025-12-31) — see the DATE PADDING NOTE in the module docstring.
NORDPOOL_START_DATE = date(2021, 1, 3)
NORDPOOL_END_DATE = date(2026, 1, 1)
NORDPOOL_AREAS = ["DK1", "DK2"]
NORDPOOL_CACHE_DIR = PROJECT_ROOT / "data/raw/balancing"
NORDPOOL_OUTPUT_CSV = PROJECT_ROOT / "data/processed/mfrr/mfrr_DK1_DK2_2021_2025_MW.csv"
NORDPOOL_REQUEST_DELAY_SECONDS = 1.0
NORDPOOL_MAX_RETRIES_PER_DAY = 5
NORDPOOL_BASE_URL = "https://dataportal-api.nordpoolgroup.com/ManualFrequencyRestorationReserve/multiple"

# Paste a fresh bearer token here (with or without the leading "Bearer ")
# before running, or leave as-is and the script will prompt for one
# interactively.
NORDPOOL_BEARER_TOKEN = "PASTE_YOUR_TOKEN_HERE"


def _clean_token(raw: str) -> str:
    """Strip an optional leading 'Bearer ' (any case) and surrounding
    whitespace, so pasting the token straight out of DevTools works either
    way. Used for both the Nord Pool and the ENTSO-E token."""
    raw = raw.strip()
    if raw[:7].lower() == "bearer ":
        raw = raw[7:].strip()
    return raw


def _decode_jwt_exp(token: str) -> datetime | None:
    """Best-effort read of a JWT's exp claim, without a jwt library."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad for base64
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    except Exception:
        return None


def _nordpool_headers(token: str) -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://data.nordpoolgroup.com",
        "Referer": "https://data.nordpoolgroup.com/",
        "Authorization": f"Bearer {token}",
    }


def _nordpool_prompt_for_new_token() -> str:
    print("\n" + "=" * 60)
    print("Access token expired or was rejected (401).")
    print("Grab a fresh one from DevTools (Network tab -> a 'multiple?date=...'")
    print("request -> Headers -> Request Headers -> authorization),")
    print("and paste it below (with or without 'Bearer ').")
    print("=" * 60)
    return _clean_token(input("New token: "))


def _fetch_nordpool_mfrr_day(day: date, session: requests.Session, token_holder: dict) -> dict | None:
    """Fetch one day's data, using local cache if already downloaded.
    token_holder is a mutable dict {'token': str} so we can update the token
    in place and have callers see the new value."""
    NORDPOOL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = NORDPOOL_CACHE_DIR / f"{day.isoformat()}.json"

    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    params = {
        "date": day.isoformat(),
        "deliveryAreas": ",".join(NORDPOOL_AREAS),
    }

    retries = 0
    while retries <= NORDPOOL_MAX_RETRIES_PER_DAY:
        print(f"  -> requesting {day}", flush=True)
        try:
            resp = session.get(
                NORDPOOL_BASE_URL,
                headers=_nordpool_headers(token_holder["token"]),
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
            print(f"     ok ({day})", flush=True)
            return data

        if resp.status_code == 401:
            print(f"     401 (token expired) ({day})", flush=True)
            token_holder["token"] = _nordpool_prompt_for_new_token()
            continue  # retry this same day immediately with the new token

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else min(60, 5 * (2 ** retries))
            print(f"     429, waiting {wait:.0f}s...", flush=True)
            time.sleep(wait)
            retries += 1
            continue

        print(f"     HTTP {resp.status_code} — skipping ({day})", flush=True)
        return None

    print(f"  [!] {day}: gave up after {NORDPOOL_MAX_RETRIES_PER_DAY} retries (429s)")
    return None


def _hourly_dominating_direction(df: pd.DataFrame) -> pd.Series:
    """One DominatingDirection per (Area, clock hour), computed only from
    that zone's own sub-hourly rows within that one hour — hours and zones
    are never mixed.

    Majority vote of the non-empty values. A TIE (e.g. 2x Up, 2x Down) is
    broken by the same hour's net mFRR activation (sum of activated up
    minus activated down over that hour's rows): positive -> "Up",
    negative -> "Down", zero or missing -> left empty. This replaces the
    old pandas .mode().iloc[0], which broke ties alphabetically — always
    "Down" — and so inflated the Down count."""
    hours = df["DeliveryStartUTC"].dt.floor("1h")
    stats = {"tie_up": 0, "tie_down": 0, "tie_empty": 0}

    def pick(g: pd.DataFrame):
        counts = g["DominatingDirection"].value_counts()  # ignores empty values
        if counts.empty:
            return None
        top = counts.index[counts == counts.max()]
        if len(top) == 1:
            return top[0]
        net = (g["ActivatedUpVolume_MW"].sum(min_count=1)
               - g["ActivatedDownVolume_MW"].sum(min_count=1))
        if pd.isna(net) or net == 0:
            stats["tie_empty"] += 1
            return None
        stats["tie_up" if net > 0 else "tie_down"] += 1
        return "Up" if net > 0 else "Down"

    cols = ["DominatingDirection", "ActivatedUpVolume_MW", "ActivatedDownVolume_MW"]
    out = df[cols].groupby([df["Area"], hours.rename("DeliveryStartUTC")], sort=False).apply(pick)
    n_ties = sum(stats.values())
    print(f"[Nord Pool mFRR] DominatingDirection: {n_ties} tied hour(s) resolved by net activation "
          f"-> Up {stats['tie_up']}, Down {stats['tie_down']}, left empty {stats['tie_empty']}.")
    return out.rename("DominatingDirection")


def _flatten_nordpool_mfrr_day(data: dict) -> list[dict]:
    """Turn one day's nested JSON into flat rows, one per hour per area."""
    rows = []
    if not data:
        return rows

    currency = data.get("currencyCode")
    delivery_date = data.get("deliveryDateCET")

    for entry in data.get("contentPerArea", []):
        start = entry.get("deliveryStart")
        end = entry.get("deliveryEnd")
        for area, vals in entry.get("entryPerArea", {}).items():
            rows.append({
                "DeliveryDateCET": delivery_date,
                "DeliveryStartUTC": start,
                "DeliveryEndUTC": end,
                "Area": area,
                "AcceptedUpBidVolume_MW": vals.get("acceptedUpBidVolume"),
                "AcceptedDownBidVolume_MW": vals.get("acceptedDownBidVolume"),
                "ActivatedUpVolume_MW": vals.get("activatedUpVolume"),
                "ActivatedDownVolume_MW": vals.get("activatedDownVolume"),
                "DownPrice": vals.get("downPrice"),
                "UpPrice": vals.get("upPrice"),
                "ImbalancePrice": vals.get("imbalancePrice"),
                "DominatingDirection": vals.get("dominatingDirection"),
                "Currency": currency,
            })
    return rows


def download_nordpool_mfrr():
    """Full mFRR download (with local caching + resume) and combine to one CSV."""
    session = requests.Session()
    all_rows = []
    failed_days = []

    token = _clean_token(NORDPOOL_BEARER_TOKEN)
    if token == "PASTE_YOUR_TOKEN_HERE" or not token:
        token = _nordpool_prompt_for_new_token()
    exp = _decode_jwt_exp(token)
    if exp:
        remaining = (exp - datetime.now(timezone.utc)).total_seconds()
        print(f"Token expires at {exp.isoformat()} (~{remaining/60:.0f} min from now).")
        if remaining < 0:
            print("That token is already expired.")
            token = _nordpool_prompt_for_new_token()

    token_holder = {"token": token}

    days = list(daterange(NORDPOOL_START_DATE, NORDPOOL_END_DATE))
    print(f"[Nord Pool mFRR] Fetching {len(days)} days ({NORDPOOL_START_DATE} to "
          f"{NORDPOOL_END_DATE}) for areas {NORDPOOL_AREAS}...")

    for i, day in enumerate(days, 1):
        data = _fetch_nordpool_mfrr_day(day, session, token_holder)
        if data is None:
            failed_days.append(day)
            continue
        all_rows.extend(_flatten_nordpool_mfrr_day(data))
        if i % 50 == 0:
            print(f"--- progress: {i}/{len(days)} days processed ---", flush=True)
        time.sleep(NORDPOOL_REQUEST_DELAY_SECONDS)

    if not all_rows:
        print("[Nord Pool mFRR] No data retrieved — aborting.")
        return

    df = pd.DataFrame(all_rows)
    df["DeliveryStartUTC"] = pd.to_datetime(df["DeliveryStartUTC"])
    df["DeliveryEndUTC"] = pd.to_datetime(df["DeliveryEndUTC"])
    df = df.sort_values(["DeliveryStartUTC", "Area"]).reset_index(drop=True)

    mfrr_agg_map = {
        "DeliveryDateCET": "first",
        "DeliveryEndUTC": "last",
        "AcceptedUpBidVolume_MW": "mean",
        "AcceptedDownBidVolume_MW": "mean",
        "ActivatedUpVolume_MW": "mean",
        "ActivatedDownVolume_MW": "mean",
        "DownPrice": "mean",
        "UpPrice": "mean",
        "ImbalancePrice": "mean",
        # DominatingDirection is aggregated separately below: its tie-break
        # needs the activation columns, which a per-column agg can't see.
        "Currency": "first",
    }
    direction = _hourly_dominating_direction(df)
    df = resample_to_hourly(df, "DeliveryStartUTC", "Area", mfrr_agg_map, "[Nord Pool mFRR]")
    df = df.merge(direction.reset_index(), on=["Area", "DeliveryStartUTC"], how="left")
    df.insert(df.columns.get_loc("Currency"), "DominatingDirection", df.pop("DominatingDirection"))

    out_path = Path(NORDPOOL_OUTPUT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\n[Nord Pool mFRR] Done. Wrote {len(df)} rows to {out_path}")

    if failed_days:
        print(f"\n[Nord Pool mFRR] {len(failed_days)} day(s) failed to download:")
        for d in failed_days:
            print(f"  - {d}")
        print("Re-run to retry only the missing days (cache skips the rest).")


# ============================================================
# ENERGINET — aFRR Activated (Energi Data Service, pre-PICASSO period)
# ============================================================
# Public API, no auth needed. Confirmed via dataset metadata: "dataFrom":
# "2022-01-01T00:00:00" — the dataset genuinely does not go back to 2021, so
# this starts there rather than at 2021-01-01 like mFRR. Also confirmed via
# metadata: aFRR_UpActivated / aFRR_DownActivated are in MWh (energy, not
# power) — see the ANALYTICS section note below on why this matters for
# combining with ENTSO-E later.
#
# NOTE: this source is genuinely UTC (HourUTC is real UTC, confirmed) — no
# CET-fix padding needed, unlike the Nord Pool sources above/below.
#
# API accepts real date ranges directly (not one-request-per-day like Nord
# Pool), so this pulls monthly chunks instead of daily ones. Each chunk is
# cached to disk, and a chunk is auto-paginated (via offset) if its "total"
# is bigger than what came back in one page — in practice a month of hourly
# DK1+DK2 data (~1,500 rows) always fits in a single page, so this is just a
# safety net rather than something expected to trigger.

ENERGINET_AFRR_START_DATE = date(2022, 1, 1)   # confirmed dataset start (metadata: dataFrom)
# PICASSO went live 2024-10-02, and ENTSO-E's post-PICASSO window (below)
# starts on that same date — so this must end the day BEFORE, not on it.
# It used to end ON 2024-10-02 too, which meant both sources genuinely
# fetched that calendar day, and the combine step produced 44 (DK1+DK2,
# ~hourly) duplicate rows from each side for it. Ending here instead
# gives the two sources a clean handoff with no shared day, so the
# combined file has zero PICASSO-boundary duplicates instead of relying
# on dataframe_building.py's keep="first" to silently drop half of them.
ENERGINET_AFRR_END_DATE = date(2024, 10, 1)
ENERGINET_AFRR_AREAS = ["DK1", "DK2"]
ENERGINET_AFRR_CACHE_DIR = PROJECT_ROOT / "data/raw/afrr/energinet_pre_picasso"
ENERGINET_AFRR_OUTPUT_CSV = PROJECT_ROOT / "data/processed/afrr/energinet_pre_picasso_DK1_DK2_2022_2024.csv"
ENERGINET_AFRR_BASE_URL = "https://api.energidataservice.dk/dataset/AfrrActivatedAutomatic"
ENERGINET_AFRR_REQUEST_DELAY_SECONDS = 3.0   # small extra safety margin between chunk requests
ENERGINET_AFRR_PAGE_LIMIT = 20000   # generous — a full year of hourly DK1+DK2 is ~17,500 rows, so pagination rarely triggers
ENERGINET_AFRR_MAX_RETRIES = 5


def _chunk_ranges(start: date, end: date, months: int = 12):
    """Yield (chunk_start, chunk_end) pairs covering [start, end] in blocks
    of `months` months, with chunk_end being the day AFTER the last day to
    include (the API's 'end' parameter is exclusive). Defaults to yearly
    chunks — the API accepts arbitrary date ranges in one call, so there's
    no need to chunk monthly; fewer, bigger requests avoid tripping
    Energinet's per-minute rate limit (429 with a ~5min Retry-After)."""
    cur = date(start.year, start.month, 1)
    while cur <= end:
        y, m = cur.year, cur.month + months
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
        nxt = date(y, m, 1)
        chunk_start = max(cur, start)
        chunk_end = min(nxt, end + timedelta(days=1))
        yield chunk_start, chunk_end
        cur = nxt


def _fetch_energinet_afrr_chunk(chunk_start: date, chunk_end: date, session: requests.Session) -> list[dict]:
    """Fetch all records for one chunk, using local cache if already
    downloaded, paginating within the chunk if needed. Only caches on full
    success — a chunk that fails partway through pagination is NOT cached,
    so a re-run will retry it properly instead of silently treating a
    partial result as complete."""
    ENERGINET_AFRR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = ENERGINET_AFRR_CACHE_DIR / f"{chunk_start.isoformat()}_{chunk_end.isoformat()}.json"

    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    all_records = []
    offset = 0
    succeeded = True
    while True:
        params = {
            "start": chunk_start.isoformat(),
            "end": chunk_end.isoformat(),
            "filter": json.dumps({"PriceArea": ENERGINET_AFRR_AREAS}),
            "sort": "HourUTC asc",
            "limit": ENERGINET_AFRR_PAGE_LIMIT,
            "offset": offset,
        }

        retries = 0
        while retries <= ENERGINET_AFRR_MAX_RETRIES:
            print(f"  -> requesting {chunk_start} to {chunk_end} (offset {offset})", flush=True)
            try:
                resp = session.get(ENERGINET_AFRR_BASE_URL, params=params, timeout=30)
            except requests.exceptions.RequestException as e:
                print(f"     connection error ({e!r}), retrying in 5s...", flush=True)
                time.sleep(5)
                retries += 1
                continue

            if resp.status_code == 200:
                data = resp.json()
                break

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else min(60, 5 * (2 ** retries))
                print(f"     429, waiting {wait:.0f}s...", flush=True)
                time.sleep(wait)
                retries += 1
                continue

            print(f"     HTTP {resp.status_code} — giving up on this chunk", flush=True)
            data = None
            break
        else:
            data = None

        if data is None:
            succeeded = False
            break

        records = data.get("records", [])
        total = data.get("total", len(records))
        all_records.extend(records)
        print(f"     ok ({len(records)} records, total for chunk: {total})", flush=True)

        if len(all_records) >= total or not records:
            break
        offset += ENERGINET_AFRR_PAGE_LIMIT
        time.sleep(ENERGINET_AFRR_REQUEST_DELAY_SECONDS)

    if succeeded:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(all_records, f)
    else:
        print(f"     [!] chunk {chunk_start} to {chunk_end} incomplete — NOT cached, will retry on next run", flush=True)

    return all_records if succeeded else []


def _flatten_energinet_afrr_record(rec: dict) -> dict:
    return {
        "HourUTC": rec.get("HourUTC"),
        "HourDK": rec.get("HourDK"),
        "Area": rec.get("PriceArea"),
        "aFRR_DownActivated": rec.get("aFRR_DownActivated"),
        "aFRR_UpActivated": rec.get("aFRR_UpActivated"),
    }


def download_energinet_afrr():
    """Full aFRR-activated download (yearly chunks, cached, resumable) and
    combine to one CSV."""
    session = requests.Session()
    all_rows = []
    failed_chunks = []

    chunks = list(_chunk_ranges(ENERGINET_AFRR_START_DATE, ENERGINET_AFRR_END_DATE, months=12))
    print(f"[Energinet aFRR] Fetching {len(chunks)} yearly chunks "
          f"({ENERGINET_AFRR_START_DATE} to {ENERGINET_AFRR_END_DATE}) for areas {ENERGINET_AFRR_AREAS}...")

    for chunk_start, chunk_end in chunks:
        records = _fetch_energinet_afrr_chunk(chunk_start, chunk_end, session)
        if not records:
            failed_chunks.append((chunk_start, chunk_end))
            continue
        all_rows.extend(_flatten_energinet_afrr_record(r) for r in records)
        time.sleep(ENERGINET_AFRR_REQUEST_DELAY_SECONDS)

    if not all_rows:
        print("[Energinet aFRR] No data retrieved — aborting.")
        return

    df = pd.DataFrame(all_rows)
    df["HourUTC"] = pd.to_datetime(df["HourUTC"])
    df["HourDK"] = pd.to_datetime(df["HourDK"])
    df = df.sort_values(["HourUTC", "Area"]).reset_index(drop=True)

    # aFRR_UpActivated/aFRR_DownActivated are confirmed MWh (energy, from
    # dataset metadata) — SUM is the physically correct aggregation if any
    # sub-hourly rows are ever found (energy is additive across time,
    # unlike the MW/power columns elsewhere which need averaging). This
    # dataset's own metadata says it's always hourly, so in practice this
    # is expected to be a no-op — but checked every run rather than assumed.
    energinet_afrr_agg_map = {
        "HourDK": "first",
        "aFRR_DownActivated": "sum",
        "aFRR_UpActivated": "sum",
    }
    df = resample_to_hourly(df, "HourUTC", "Area", energinet_afrr_agg_map, "[Energinet aFRR]")

    out_path = Path(ENERGINET_AFRR_OUTPUT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\n[Energinet aFRR] Done. Wrote {len(df)} rows to {out_path}")

    if failed_chunks:
        print(f"\n[Energinet aFRR] {len(failed_chunks)} chunk(s) failed to download:")
        for s, e in failed_chunks:
            print(f"  - {s} to {e}")
        print("Re-run to retry only the missing chunks (cache skips the rest).")


# ============================================================
# ENTSO-E — aFRR activated energy, post-PICASSO (2024-10-02 -> today)
# ============================================================
# Separate platform: own account/token, returns XML, one request per
# (day, area). Requires a free security token from
# https://transparencyplatform.entsoe.eu/ account settings ("Web Api
# Security Token") — paste it below.
#
# Confirmed: documentType=A24 ("Aggregated Balancing Energy Bids"),
# processType=A67 ("Central Selection aFRR" — the PICASSO mechanism;
# A83/A51/A16 were wrong guesses along the way, confirmed wrong via direct
# testing). Data confirmed present from 2024-09-16 onward (binary search),
# with no internal gaps through 2026-09-23 (spot-checked monthly), so this
# single source covers the whole post-PICASSO period, not just the old
# Oct 2024 - Mar 2025 gap. 15-minute resolution.
#
# NOTE: this source is genuinely UTC (confirmed) — no CET-fix padding
# needed, unlike the Nord Pool sources above.

ENTSOE_AFRR_START_DATE = date(2024, 10, 2)
ENTSOE_AFRR_END_DATE = date(2025, 12, 31)   # capped to match the 2021-2025 analysis window — not pulling into 2026
ENTSOE_AFRR_AREAS = {
    "DK1": "10YDK-1--------W",   # confirmed via successful query (note: ends in W, not M)
    "DK2": "10YDK-2--------M",   # confirmed via successful query
}
ENTSOE_AFRR_CACHE_DIR = PROJECT_ROOT / "data/raw/afrr/entsoe_post_picasso"
ENTSOE_AFRR_OUTPUT_CSV = PROJECT_ROOT / "data/processed/afrr/entsoe_post_picasso_DK1_DK2_2024_2025.csv"
ENTSOE_AFRR_BASE_URL = "https://web-api.tp.entsoe.eu/api"
ENTSOE_AFRR_DOCUMENT_TYPE = "A24"
ENTSOE_AFRR_PROCESS_TYPE = "A67"
ENTSOE_AFRR_REQUEST_DELAY_SECONDS = 1.0
ENTSOE_AFRR_MAX_RETRIES = 5

# Paste your ENTSO-E security token here (a GUID, not a JWT — doesn't expire
# the way Nord Pool's did, but treat it like a password).
ENTSOE_SECURITY_TOKEN = "PASTE_YOUR_TOKEN_HERE"


def _entsoe_prompt_for_new_token() -> str:
    print("\n" + "=" * 60)
    print("ENTSO-E token expired or was rejected (401).")
    print("Grab a fresh one from your ENTSO-E account settings")
    print("(Web Api Security Token) and paste it below (with or without 'Bearer ').")
    print("=" * 60)
    return _clean_token(input("New token: "))


def _fetch_entsoe_afrr_day(day: date, area_code: str, area_name: str, session: requests.Session, token_holder: dict) -> str | None:
    """Fetch one day's raw XML for one area, using local cache if already
    downloaded."""
    ENTSOE_AFRR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = ENTSOE_AFRR_CACHE_DIR / f"{day.isoformat()}_{area_name}.xml"

    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    period_start = day.strftime("%Y%m%d") + "0000"
    period_end = (day + timedelta(days=1)).strftime("%Y%m%d") + "0000"

    retries = 0
    while retries <= ENTSOE_AFRR_MAX_RETRIES:
        params = {
            "securityToken": token_holder["token"],
            "documentType": ENTSOE_AFRR_DOCUMENT_TYPE,
            "processType": ENTSOE_AFRR_PROCESS_TYPE,
            "area_Domain": area_code,
            "periodStart": period_start,
            "periodEnd": period_end,
        }
        print(f"  -> requesting {day} {area_name}", flush=True)
        try:
            resp = session.get(ENTSOE_AFRR_BASE_URL, params=params, timeout=30)
        except requests.exceptions.RequestException as e:
            print(f"     connection error ({e!r}), retrying in 5s...", flush=True)
            time.sleep(5)
            retries += 1
            continue

        if resp.status_code == 200:
            cache_file.write_text(resp.text, encoding="utf-8")
            print(f"     ok ({day} {area_name})", flush=True)
            return resp.text

        if resp.status_code == 401:
            print(f"     401 (token expired) ({day} {area_name})", flush=True)
            token_holder["token"] = _entsoe_prompt_for_new_token()
            continue  # retry this same day immediately with the new token

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else min(60, 5 * (2 ** retries))
            print(f"     429, waiting {wait:.0f}s...", flush=True)
            time.sleep(wait)
            retries += 1
            continue

        # ENTSO-E returns a readable <Reason><text>...</text></Reason> body
        # on errors — print it so a wrong param is obvious immediately.
        print(f"     HTTP {resp.status_code} — skipping ({day} {area_name})", flush=True)
        print(f"     response: {resp.text[:500]}", flush=True)
        return None

    print(f"  [!] {day} {area_name}: gave up after {ENTSOE_AFRR_MAX_RETRIES} retries (429s)")
    return None


_ENTSOE_NS = {"ns": "urn:iec62325.351:tc57wg16:451-6:balancingdocument:4:1"}
_ENTSOE_DIRECTION = {"A01": "Up", "A02": "Down"}


def _flatten_entsoe_afrr_day(xml_text: str, day: date, area_name: str) -> list[dict]:
    """Parse one day's raw XML into flat 15-min rows, one per (timestamp, area).

    Each <TimeSeries> is one flow direction (Up or Down). Each <Point> gives
    quantity (offered/bid volume, unit MAW = MW, confirmed), secondaryQuantity
    (ACTIVATED volume — the one matching Energinet's aFRR_UpActivated /
    aFRR_DownActivated), and unavailable_Quantity.quantity. ENTSO-E only
    emits a <Point> when a value CHANGES — missing positions mean "same as
    the last listed value" — so positions are forward-filled across all 96
    quarter-hours of the day.
    """
    root = ET.fromstring(xml_text)
    rows_by_time: dict[datetime, dict] = {}

    for ts in root.findall("ns:TimeSeries", _ENTSOE_NS):
        direction_code = ts.findtext("ns:flowDirection.direction", default="", namespaces=_ENTSOE_NS)
        direction = _ENTSOE_DIRECTION.get(direction_code, direction_code)

        period = ts.find("ns:Period", _ENTSOE_NS)
        if period is None:
            continue
        start_str = period.findtext("ns:timeInterval/ns:start", namespaces=_ENTSOE_NS)
        period_start = datetime.strptime(start_str, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)

        pos_values = {}
        for pt in period.findall("ns:Point", _ENTSOE_NS):
            pos = int(pt.findtext("ns:position", namespaces=_ENTSOE_NS))
            offered = float(pt.findtext("ns:quantity", namespaces=_ENTSOE_NS))
            activated = float(pt.findtext("ns:secondaryQuantity", default="0", namespaces=_ENTSOE_NS) or 0)
            unavailable = float(pt.findtext("ns:unavailable_Quantity.quantity", default="0", namespaces=_ENTSOE_NS) or 0)
            pos_values[pos] = (offered, activated, unavailable)

        current = None
        for pos in range(1, 97):  # 96 quarter-hours in a day
            if pos in pos_values:
                current = pos_values[pos]
            if current is None:
                continue  # no value seen yet this day — leave unset rather than guess
            offered, activated, unavailable = current
            ts_dt = period_start + timedelta(minutes=15 * (pos - 1))
            row = rows_by_time.setdefault(ts_dt, {
                "HourUTC": ts_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "Area": area_name,
            })
            row[f"aFRR_{direction}Offered_MW"] = offered
            row[f"aFRR_{direction}Activated_MW"] = activated
            row[f"aFRR_{direction}Unavailable_MW"] = unavailable

    return list(rows_by_time.values())


def download_entsoe_afrr_post_picasso():
    """Fetch + cache raw XML for the full post-PICASSO period, parse to
    15-min rows, and combine into one CSV."""
    session = requests.Session()
    token = _clean_token(ENTSOE_SECURITY_TOKEN)
    if token == "PASTE_YOUR_TOKEN_HERE" or not token:
        token = _entsoe_prompt_for_new_token()
    token_holder = {"token": token}

    days = list(daterange(ENTSOE_AFRR_START_DATE, ENTSOE_AFRR_END_DATE))
    print(f"[ENTSO-E aFRR post-PICASSO] Fetching {len(days)} days x {len(ENTSOE_AFRR_AREAS)} areas "
          f"({ENTSOE_AFRR_START_DATE} to {ENTSOE_AFRR_END_DATE})...")

    all_rows = []
    failed = []
    for day in days:
        for area_name, area_code in ENTSOE_AFRR_AREAS.items():
            xml_text = _fetch_entsoe_afrr_day(day, area_code, area_name, session, token_holder)
            if xml_text is None:
                failed.append((day, area_name))
                continue
            all_rows.extend(_flatten_entsoe_afrr_day(xml_text, day, area_name))
            time.sleep(ENTSOE_AFRR_REQUEST_DELAY_SECONDS)

    if not all_rows:
        print("[ENTSO-E aFRR post-PICASSO] No rows parsed — nothing to write.")
        return

    df = pd.DataFrame(all_rows)
    df["HourUTC"] = pd.to_datetime(df["HourUTC"])
    df = df.sort_values(["HourUTC", "Area"]).reset_index(drop=True)

    out_path = Path(ENTSOE_AFRR_OUTPUT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\n[ENTSO-E aFRR post-PICASSO] Done. Wrote {len(df)} rows to {out_path}")

    if failed:
        print(f"\n[ENTSO-E aFRR post-PICASSO] {len(failed)} (day, area) pair(s) failed:")
        for d, a in failed:
            print(f"  - {d} {a}")
        print("Re-run to retry only the missing days (cache skips the rest).")


# ============================================================
# ENERGINET — aFRR Activated, from ImbalancePrice (2025-03-04 onward)
# ============================================================
# Optional extra variables (imbalance price, spot price, mFRR marginal
# price) — NOT needed for aFRR activation continuity, since ENTSO-E already
# covers the whole post-PICASSO period. Not yet implemented.

def download_energinet_afrr_imbalanceprice():
    print("[Energinet ImbalancePrice] not implemented yet.")


# ============================================================
# ANALYTICS — feature overview + gap detection (terminal only)
# ============================================================
# Deliberately NOT combining Energinet and ENTSO-E into one series yet.
# Units are now confirmed (via dataset metadata) to genuinely differ:
#   - Energinet aFRR_UpActivated/aFRR_DownActivated: MWh (energy)
#   - ENTSO-E aFRR_UpActivated_MW/aFRR_DownActivated_MW: MW (power, unit
#     "MAW" in the raw XML)
# To combine, ENTSO-E's 15-min MW readings need converting to hourly MWh —
# because a quarter-hour is exactly 1/4 hour, this works out to simply
# averaging the 4 quarterly MW values for each hour (mean(MW_i) equals the
# total hourly MWh here; see conversation notes for the derivation). NOT
# yet implemented here on purpose — combine only once you've decided this
# is the right approach for your analysis.

AFRR_AREAS = ["DK1", "DK2"]


def _load_csv(path: str, time_col: str) -> pd.DataFrame | None:
    p = Path(path)
    if not p.exists():
        print(f"[skip] file not found: {p}")
        return None
    df = pd.read_csv(p)
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    return df


def _feature_overview(df: pd.DataFrame, name: str, time_col: str) -> dict:
    """Print a detailed feature overview and return a short summary dict for
    the side-by-side table."""
    print(f"\n{'=' * 70}")
    print(f"{name}: FEATURE OVERVIEW")
    print("=" * 70)
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"Columns: {list(df.columns)}")
    print(f"Date range: {df[time_col].min()} to {df[time_col].max()}")

    per_area_counts = {}
    for area in AFRR_AREAS:
        n = (df["Area"] == area).sum()
        per_area_counts[area] = n
        print(f"  {area}: {n} rows")

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if numeric_cols:
        print("\nSummary statistics:")
        print(df[numeric_cols].describe())

    print("\nFirst 5 rows:")
    print(df.head())

    print("\nMissing values per column:")
    print(df.isna().sum())

    return {
        "name": name,
        "rows": df.shape[0],
        "cols": df.shape[1],
        "start": df[time_col].min(),
        "end": df[time_col].max(),
        "per_area": per_area_counts,
    }


def _detect_gaps(df: pd.DataFrame, time_col: str, freq: str, name: str) -> dict:
    """For each area, compare actual timestamps against the expected full
    range at `freq` and print any missing stretches. No files written —
    everything goes to the terminal."""
    print(f"\n{'-' * 70}")
    print(f"{name}: GAP DETECTION (expected frequency: {freq})")
    print("-" * 70)

    gap_summary = {}
    for area in AFRR_AREAS:
        sub = df[df["Area"] == area].sort_values(time_col)
        if sub.empty:
            print(f"  {area}: no data at all")
            gap_summary[area] = None
            continue

        expected = pd.date_range(sub[time_col].min(), sub[time_col].max(), freq=freq)
        actual = pd.DatetimeIndex(sub[time_col].unique())
        missing = expected.difference(actual)
        pct_missing = 100 * len(missing) / len(expected) if len(expected) else 0
        gap_summary[area] = pct_missing

        print(f"  {area}: {len(expected)} expected, {len(missing)} missing ({pct_missing:.2f}%)")

        if len(missing) > 0:
            missing_sorted = missing.sort_values()
            gaps = []
            gap_start = missing_sorted[0]
            prev = missing_sorted[0]
            step = pd.Timedelta(freq)
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

    return gap_summary


def _print_side_by_side(summaries: list[dict]):
    print(f"\n{'=' * 70}")
    print("SIDE-BY-SIDE SUMMARY")
    print("=" * 70)
    label_w = 22
    col_w = 28
    headers = [s["name"] for s in summaries]
    print(" " * label_w + "".join(h[:col_w].ljust(col_w) for h in headers))
    print("-" * (label_w + col_w * len(summaries)))

    def row(label, values):
        print(label.ljust(label_w) + "".join(str(v)[:col_w].ljust(col_w) for v in values))

    row("Rows", [s["rows"] for s in summaries])
    row("Columns", [s["cols"] for s in summaries])
    row("Start", [s["start"] for s in summaries])
    row("End", [s["end"] for s in summaries])
    for area in AFRR_AREAS:
        row(f"  {area} rows", [s["per_area"].get(area, 0) for s in summaries])


def run_afrr_analytics():
    """Load both aFRR sources' output CSVs and print feature overview + gap
    detection for each, plus a side-by-side comparison. No combining, no
    plots, no extra files written — terminal output only."""
    energinet_df = _load_csv(ENERGINET_AFRR_OUTPUT_CSV, "HourUTC")
    entsoe_df = _load_csv(ENTSOE_AFRR_OUTPUT_CSV, "HourUTC")

    summaries = []

    if energinet_df is not None:
        s = _feature_overview(energinet_df, "Energinet (pre-PICASSO, hourly)", "HourUTC")
        _detect_gaps(energinet_df, "HourUTC", "1h", "Energinet (pre-PICASSO)")
        summaries.append(s)

    if entsoe_df is not None:
        s = _feature_overview(entsoe_df, "ENTSO-E (post-PICASSO, 15-min)", "HourUTC")
        _detect_gaps(entsoe_df, "HourUTC", "15min", "ENTSO-E (post-PICASSO)")
        summaries.append(s)

    if len(summaries) == 2:
        _print_side_by_side(summaries)
    elif not summaries:
        print("\nNo aFRR data found yet — run the download functions first.")


# ============================================================
# COMBINE — full feature union, hourly, nulls where a feature doesn't
# exist yet for that period
# ============================================================
# Keeps every column from both sources. Energinet only ever published
# Up/Down Activated (MWh) — Offered/Unavailable don't exist pre-PICASSO, so
# those columns are genuinely NaN for 2022-01 -> 2024-10-02 rows, not
# dropped. ENTSO-E is 15-min MW — resampled to hourly by averaging the 4
# quarters, which (since a quarter-hour is exactly 1/4 hour) gives exactly
# the equivalent hourly MWh figure. The Activated columns are renamed to
# match Energinet's naming, since they're the same underlying quantity
# across the PICASSO boundary — Offered/Unavailable have no Energinet
# equivalent, so they keep their own names and are NaN before 2024-10-02.

AFRR_COMBINED_OUTPUT_CSV = PROJECT_ROOT / "data/processed/afrr/afrr_DK1_DK2_2022_2025_hourly.csv"


def combine_afrr_common_subset():
    """Build the single continuous hourly aFRR series: full feature union,
    NaN wherever a feature genuinely doesn't exist for that period."""
    energinet_df = _load_csv(ENERGINET_AFRR_OUTPUT_CSV, "HourUTC")
    entsoe_df = _load_csv(ENTSOE_AFRR_OUTPUT_CSV, "HourUTC")

    if energinet_df is None or entsoe_df is None:
        print("[Combine aFRR] Missing one or both source files — run the downloads first.")
        return None

    e = energinet_df[["HourUTC", "Area", "aFRR_UpActivated", "aFRR_DownActivated"]].copy()
    e["Source"] = "Energinet"

    entsoe_value_cols = [
        "aFRR_UpActivated_MW", "aFRR_DownActivated_MW",
        "aFRR_UpOffered_MW", "aFRR_DownOffered_MW",
        "aFRR_UpUnavailable_MW", "aFRR_DownUnavailable_MW",
    ]
    rows = []
    for area in AFRR_AREAS:
        sub = entsoe_df[entsoe_df["Area"] == area].set_index("HourUTC")
        present_cols = [c for c in entsoe_value_cols if c in sub.columns]
        rows_before = len(sub)
        hourly = sub[present_cols].resample("1h").mean()
        rows_after = len(hourly)
        if rows_after < rows_before:
            print(f"[Combine aFRR] {area}: resampled {rows_before} raw rows -> {rows_after} "
                  f"hourly rows ({rows_before - rows_after} sub-hourly rows collapsed).")
        else:
            print(f"[Combine aFRR] {area}: all {rows_before} rows were already hourly.")
        hourly = hourly.rename(columns={
            "aFRR_UpActivated_MW": "aFRR_UpActivated",
            "aFRR_DownActivated_MW": "aFRR_DownActivated",
        })
        hourly["Area"] = area
        rows.append(hourly.reset_index())
    t = pd.concat(rows, ignore_index=True)
    t["Source"] = "ENTSO-E"

    # outer union of columns — pandas NaN-fills whatever's missing on either side
    combined = pd.concat([e, t], ignore_index=True, sort=False)
    combined = combined.sort_values(["HourUTC", "Area"]).reset_index(drop=True)

    out_path = Path(AFRR_COMBINED_OUTPUT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out_path, index=False)
    print(f"[Combine aFRR] Wrote {len(combined)} rows to {out_path}")
    print(f"  columns: {list(combined.columns)}")

    print(f"\nDate range: {combined['HourUTC'].min()} to {combined['HourUTC'].max()}")
    for area in AFRR_AREAS:
        n = (combined["Area"] == area).sum()
        print(f"  {area}: {n} rows")

    print("\nNull count per column (expected: Offered/Unavailable columns are")
    print("null for the whole Energinet-sourced period, by design):")
    print(combined.isna().sum())

    return combined


# ============================================================
# FEATURE INVENTORY — what's actually available to build the model dataset
# ============================================================

def print_feature_inventory():
    """Print a plain overview of every processed table available for
    building the model dataset: what it covers, at what resolution, and
    what columns it contributes."""
    print(f"\n{'=' * 70}")
    print("FEATURE INVENTORY")
    print("=" * 70)

    sources = [
        ("mFRR (Nord Pool)", NORDPOOL_OUTPUT_CSV, "DeliveryStartUTC"),
        ("aFRR combined (Energinet + ENTSO-E, common subset)", AFRR_COMBINED_OUTPUT_CSV, "HourUTC"),
    ]

    for name, path, time_col in sources:
        p = Path(path)
        if not p.exists():
            print(f"\n{name}: NOT YET BUILT ({p})")
            continue
        df = pd.read_csv(p)
        df[time_col] = pd.to_datetime(df[time_col], utc=True)
        feature_cols = [c for c in df.columns if c not in (time_col, "Area", "Source",
                                                             "DeliveryDateCET", "DeliveryEndUTC", "HourDK")]
        print(f"\n{name}")
        print(f"  file: {p}")
        print(f"  range: {df[time_col].min()} to {df[time_col].max()}")
        print(f"  rows: {len(df)}")
        print(f"  features: {feature_cols}")


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    # ---- choose what to run ----
    RUN_NORDPOOL_MFRR = True                      # fully cached; re-run to write CSV at new data/processed/mfrr/ path
    RUN_ENERGINET_AFRR = True                     # fully cached; re-run to write CSV at new data/processed/afrr/ path
    RUN_ENTSOE_AFRR_POST_PICASSO = True           # fully cached; re-run to write CSV at new data/processed/afrr/ path
    RUN_ENERGINET_AFRR_IMBALANCEPRICE = False     # optional extra variables — not yet implemented
    RUN_AFRR_ANALYTICS = True                     # terminal-only feature + gap report for both aFRR sources
    RUN_AFRR_COMBINE = True                       # build the full-union hourly series (nulls where a feature doesn't exist yet)
    RUN_FEATURE_INVENTORY = True                  # overview of what's available for the model dataset

    if RUN_NORDPOOL_MFRR:
        download_nordpool_mfrr()

    if RUN_ENERGINET_AFRR:
        download_energinet_afrr()

    if RUN_ENTSOE_AFRR_POST_PICASSO:
        download_entsoe_afrr_post_picasso()

    if RUN_ENERGINET_AFRR_IMBALANCEPRICE:
        download_energinet_afrr_imbalanceprice()

    if RUN_AFRR_ANALYTICS:
        run_afrr_analytics()

    if RUN_AFRR_COMBINE:
        combine_afrr_common_subset()

    if RUN_FEATURE_INVENTORY:
        print_feature_inventory()

    if not (RUN_NORDPOOL_MFRR or RUN_ENERGINET_AFRR or RUN_ENTSOE_AFRR_POST_PICASSO
            or RUN_ENERGINET_AFRR_IMBALANCEPRICE or RUN_AFRR_ANALYTICS
            or RUN_AFRR_COMBINE or RUN_FEATURE_INVENTORY):
        print("Nothing selected to run — flip a RUN_* flag to True in main().")


if __name__ == "__main__":
    main()