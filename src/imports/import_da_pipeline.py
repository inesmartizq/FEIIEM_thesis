"""
Downloads Nord Pool day-ahead Prices, Volumes, and Flows for DK1/DK2,
2021-01-01 to 2025-12-31, caching raw JSON locally, then processes into
hourly-normalized CSVs.

Handles the SDAC 15-minute MTU transition (go-live 2025-10-01): all three
reports return 15-min resolution after that date, 60-min before. Processing
always resamples to hourly by AVERAGING the (up to 4) sub-hourly values,
since these are all power quantities (MW) — averaging gives the correct
equivalent hourly figure (same reasoning as the aFRR MW->MWh conversion
worked out earlier). SDAC_15MIN_DATE is used below to compute the EXPECTED
raw-entry count per day for the completeness check, so it's no longer just
a reference comment.

TIMEZONE NOTE: like the other Nord Pool sources in this project, the raw
"...UTC" fields here ("DeliveryStartUTC", "HourUTC") are actually
Europe/Copenhagen wall-clock time (CET) with a bogus "+00:00" appended, not
real UTC — confirmed via dataframe/building.py's SOURCES config
(nordpool_cet_fix=True for all three of these) and cross-checked against a
real file header. The fix is applied downstream in dataframe/building.py,
not here — this script's job is just to get the raw CET-labeled values into
clean hourly CSVs.

DATE RANGE PADDING: padded 1 day on each side vs. the true 2022-2025
analysis window, same reasoning as the other import_* pipelines: because
the "...UTC" columns are actually CET-labeled, the true UTC boundary hours
of the analysis window fall just outside a CET-labeled request range unless
padded (e.g. the true last UTC hour of 2025-12-31 falls under the
CET-labeled date 2026-01-01). Confirmed this was biting: with the
un-padded range, da_price/da_flow_*/da_buy_volume_mw/da_sell_volume_mw all
had last_non_null stuck at 2025-12-31 21:00:00+00:00 in the built
dataframe, a full 2 hours short of 23:00. The padding days are harmless
surplus — dataframe/building.py's grid only keeps rows inside the true UTC
analysis window, so the extra day on each end is simply dropped at merge.

That 2-hour (not 1-hour) shortfall was one hour more than a missing
padding day alone would explain (a bare CET mislabeling costs at most 1
hour, landing on 22:00, not 21:00). Rather than guess at the extra hour,
_check_daily_completeness() below now reports the actual raw-entry count
per (area, day) for every fetch, so a short day (e.g. the last day of the
range genuinely coming back with fewer than 24/96 entries) is visible
directly in the run log instead of being inferred later from the merged
dataframe's coverage report.

Usage:
    pip install requests pandas
    python nordpool_dayahead_export.py
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
START_DATE = date(2020, 12, 31)    # padded 1 day early (see DATE RANGE PADDING note above)
END_DATE = date(2026, 1, 1)        # padded 1 day late (see DATE RANGE PADDING note above)
AREAS = ["DK1", "DK2"]             # NOTE: not independently verified this far back for these
SDAC_15MIN_DATE = date(2025, 10, 1)  # go-live of 15-min MTU — now used by _check_daily_completeness()

RAW_DIR = PROJECT_ROOT / "data/raw/day_ahead"
PRICES_RAW_DIR = RAW_DIR / "prices"
VOLUMES_RAW_DIR = RAW_DIR / "volumes"
FLOWS_RAW_DIR = RAW_DIR / "flows"

PROCESSED_DIR = PROJECT_ROOT / "data/processed/day_ahead"
PRICES_OUTPUT_CSV = PROCESSED_DIR / "prices_DK1_DK2_2021_2025_hourly.csv"
VOLUMES_OUTPUT_CSV = PROCESSED_DIR / "volumes_DK1_DK2_2021_2025_hourly.csv"
FLOWS_OUTPUT_CSV = PROCESSED_DIR / "flows_DK1_DK2_2021_2025_hourly.csv"

PRICES_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
VOLUMES_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadVolumes/multiple"
FLOWS_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadFlow"

REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 5

# Paste a fresh bearer token here (with or without the leading "Bearer ").
# Same Nord Pool token flow as the other scripts.
BEARER_TOKEN = "PASTE_YOUR_TOKEN_HERE"
# --------------------------------------------------------


def daterange(start: date, end: date):
    days = (end - start).days
    for i in range(days + 1):
        yield start + timedelta(days=i)


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
    print("Grab a fresh one from DevTools (Network tab -> any day-ahead")
    print("request -> Headers -> Request Headers -> authorization),")
    print("and paste it below (with or without 'Bearer ').")
    print("=" * 60)
    return _clean_token(input("New token: "))


def _fetch(url: str, params: dict, session: requests.Session, token_holder: dict, label: str) -> dict | None:
    """Generic fetch-with-retry, shared by all three report types."""
    retries = 0
    while retries <= MAX_RETRIES:
        print(f"  -> requesting {label}", flush=True)
        try:
            resp = session.get(url, headers=get_headers(token_holder["token"]), params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            print(f"     connection error ({e!r}), retrying in 5s...", flush=True)
            time.sleep(5)
            retries += 1
            continue

        if resp.status_code == 200:
            print(f"     ok ({label})", flush=True)
            return resp.json()

        if resp.status_code == 401:
            print(f"     401 (token expired) ({label})", flush=True)
            token_holder["token"] = prompt_for_new_token()
            continue

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else min(60, 5 * (2 ** retries))
            print(f"     429, waiting {wait:.0f}s...", flush=True)
            time.sleep(wait)
            retries += 1
            continue

        print(f"     HTTP {resp.status_code} — skipping ({label})", flush=True)
        return None

    print(f"     gave up on {label} after {MAX_RETRIES} retries (429s)", flush=True)
    return None


# ============================================================
# SHARED DIAGNOSTICS — applied to every raw (pre-resample) dataset, so
# problems are visible at the source instead of being inferred later from
# the merged dataframe's coverage report.
# ============================================================

def _expected_daily_count(day_ts) -> int:
    """24 raw hourly entries/day before the SDAC 15-min MTU go-live, up to
    96 (15-min resolution) from that date on."""
    d = day_ts.date() if hasattr(day_ts, "date") else day_ts
    return 96 if d >= SDAC_15MIN_DATE else 24


def _check_daily_completeness(df: pd.DataFrame, time_col: str, area_col: str, label: str):
    """Per (area, calendar day), compare the actual raw-entry count against
    what's expected (see _expected_daily_count). Flags exactly which
    day(s) came back short — e.g. this is what will show, on the next run,
    whether the run's last day genuinely has fewer than 24 entries (a real
    source-side boundary) or not (pointing at something else)."""
    d = df.copy()
    d["_day"] = d[time_col].dt.floor("1D")
    counts = d.groupby([area_col, "_day"]).size().reset_index(name="n_raw_entries")
    counts["expected"] = counts["_day"].apply(_expected_daily_count)
    short = counts[counts["n_raw_entries"] < counts["expected"]].sort_values("_day")
    if not short.empty:
        print(f"{label} WARNING — {len(short)} (area, day) combination(s) have FEWER raw entries than expected:")
        print(short.to_string(index=False))
    else:
        print(f"{label} all {len(counts)} (area, day) combinations have the expected raw entry count "
              f"(24 pre-SDAC / 96 post-SDAC {SDAC_15MIN_DATE}).")


def _check_raw_duplicates(df: pd.DataFrame, time_col: str, area_col: str, label: str):
    """resample('1h').mean() silently averages away any duplicate raw
    (area, timestamp) rows with no warning — unlike mfrr/afrr elsewhere in
    this project, which both warn loudly on duplicates. This closes that
    gap: report duplicates here too, before they're invisibly absorbed."""
    dupe_mask = df.duplicated(subset=[area_col, time_col], keep=False)
    n = dupe_mask.sum()
    if n:
        print(f"{label} WARNING — {n} duplicate raw ({area_col}, {time_col}) rows found "
              f"BEFORE hourly resampling — resample().mean() will silently average these "
              f"together rather than flag them:")
        print(df.loc[dupe_mask, [area_col, time_col]].drop_duplicates()
              .sort_values([area_col, time_col]).to_string(index=False))
    else:
        print(f"{label} no duplicate raw timestamps found.")


# ============================================================
# PRICES
# ============================================================

def fetch_prices_day(day: date, session: requests.Session, token_holder: dict) -> dict | None:
    PRICES_RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = PRICES_RAW_DIR / f"{day.isoformat()}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    params = {"date": day.isoformat(), "market": "DayAhead", "deliveryArea": ",".join(AREAS), "currency": "EUR"}
    data = _fetch(PRICES_URL, params, session, token_holder, f"prices {day}")
    if data is not None:
        cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def flatten_prices_day(data: dict) -> list[dict]:
    rows = []
    if not data:
        return rows
    for entry in data.get("multiAreaEntries", []):
        start, end = entry.get("deliveryStart"), entry.get("deliveryEnd")
        for area, price in entry.get("entryPerArea", {}).items():
            rows.append({"DeliveryStartUTC": start, "DeliveryEndUTC": end, "Area": area, "Price_EUR": price})
    return rows


# ============================================================
# VOLUMES
# ============================================================

def fetch_volumes_day(day: date, session: requests.Session, token_holder: dict) -> dict | None:
    VOLUMES_RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = VOLUMES_RAW_DIR / f"{day.isoformat()}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    params = {"date": day.isoformat(), "market": "DayAhead", "deliveryAreas": ",".join(AREAS)}
    data = _fetch(VOLUMES_URL, params, session, token_holder, f"volumes {day}")
    if data is not None:
        cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def flatten_volumes_day(data: dict) -> list[dict]:
    rows = []
    if not data:
        return rows
    for entry in data.get("multiAreaEntries", []):
        start, end = entry.get("deliveryStart"), entry.get("deliveryEnd")
        for area, vals in entry.get("entryPerArea", {}).items():
            rows.append({
                "DeliveryStartUTC": start, "DeliveryEndUTC": end, "Area": area,
                "BuyVolume_MW": vals.get("buy"), "SellVolume_MW": vals.get("sell"),
            })
    return rows


# ============================================================
# FLOWS — one request per (day, area)
# ============================================================

def fetch_flows_day_area(day: date, area: str, session: requests.Session, token_holder: dict) -> dict | None:
    FLOWS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = FLOWS_RAW_DIR / f"{day.isoformat()}_{area}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    params = {"date": day.isoformat(), "market": "DayAhead", "deliveryArea": area}
    data = _fetch(FLOWS_URL, params, session, token_holder, f"flows {day} {area}")
    if data is not None:
        cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def flatten_flows_day_area(data: dict, area: str) -> list[dict]:
    rows = []
    if not data:
        return rows
    for entry in data.get("flows", []):
        row = {
            "DeliveryStartUTC": entry.get("deliveryStart"),
            "DeliveryEndUTC": entry.get("deliveryEnd"),
            "Area": area,
            "TotalImport_MW": entry.get("totalImport"),
            "TotalExport_MW": entry.get("totalExport"),
            "TotalNetPosition_MW": entry.get("totalNetPosition"),
        }
        # NOTE: this only creates columns for neighbors actually present in
        # THIS entry's byConnectionArea. RESOLVED: the ~50% missingness in
        # NL/SE3/NO2/DK1/DK2/SE4 (GER stays ~0% missing) is not a reporting
        # gap or a coverage change over time (a per-year breakdown was flat
        # at 50.0% for every year 2020-2026, ruling that out). It's
        # structural: DK1 and DK2 don't share the same set of physical
        # interconnectors. DK1 is linked to GER, NO2 (Skagerrak), SE3
        # (Konti-Skan), NL (COBRAcable), and DK2 (Storebaelt/Great Belt).
        # DK2 is linked to GER (Kontek), SE4 (Oresund), and DK1
        # (Storebaelt). Both areas link to GER, which is why GER is the
        # one neighbor column that's always present. byConnectionArea
        # simply never reports a neighbor an area has no cable to — there's
        # no flow to report, not a missing one. See
        # _fix_structural_flow_zeros() below, which turns these
        # always-NaN-for-that-area columns into 0.0 (no interconnector =
        # genuinely zero flow) rather than leaving them as missing.
        for neighbor, vals in entry.get("byConnectionArea", {}).items():
            row[f"{neighbor}_Import_MW"] = vals.get("import")
            row[f"{neighbor}_Export_MW"] = vals.get("export")
            row[f"{neighbor}_NetPosition_MW"] = vals.get("netPosition")
        rows.append(row)
    return rows


def _fix_structural_flow_zeros(hourly_df: pd.DataFrame) -> pd.DataFrame:
    """A neighbor column that's NaN for every single row of one Area (but
    populated for the other Area) isn't a data gap — it means that Area has
    no physical interconnector to that neighbor zone at all (see the note
    above flatten_flows_day_area for the DK1/DK2 topology). Filling those
    with 0.0 makes that explicit: a genuinely nonexistent interconnector
    has zero flow, by definition, not an unknown value. Leaving it as NaN
    risks a downstream step (interpolation, a model's missing-value
    handling) inventing a nonzero "phantom" flow across a cable that
    doesn't exist.

    Only a column that is NaN for ALL of an area's rows gets filled this
    way. A column with SOME but not all rows missing for an area is a
    genuine reporting gap and is left as NaN, untouched — that distinction
    is exactly what would be lost by a blanket fillna(0) over the whole
    dataframe.
    """
    fixed = hourly_df.copy()
    neighbor_cols = [c for c in fixed.columns
                      if c not in ("DeliveryStartUTC", "Area") and not c.startswith("Total")]
    filled_by_area: dict[str, list[str]] = {}
    for area, g in fixed.groupby("Area"):
        idx = g.index
        for col in neighbor_cols:
            n = len(g)
            n_missing = g[col].isna().sum()
            if n > 0 and n_missing == n:
                fixed.loc[idx, col] = 0.0
                filled_by_area.setdefault(area, []).append(col)
    if filled_by_area:
        print("\n[Flows] Structural zero-fill (area has no interconnector to this neighbor — "
              "filled NaN -> 0.0 instead of leaving it as missing):")
        for area, cols in filled_by_area.items():
            print(f"  {area}: {', '.join(sorted(cols))}")
    else:
        print("\n[Flows] No fully-absent (area, neighbor) column found — nothing to structurally zero-fill.")
    return fixed


def _check_flow_total_reconciliation(hourly_df: pd.DataFrame):
    """Sanity-check TotalImport/Export_MW against the sum of the
    per-neighbor *_Import/Export_MW columns. Informational only — sum()
    uses skipna=True, which treats a genuinely-missing neighbor as 0 in
    the sum, so don't expect a clean match during periods where neighbor
    columns have real gaps (see the missingness note above). What matters
    is whether the two track closely whenever neighbor data IS present:
    if so, that's evidence Total* is trustworthy and the gap is a real
    reporting-coverage change, not a bug in how this script builds
    Total*."""
    import_cols = [c for c in hourly_df.columns
                   if c.endswith("_Import_MW") and not c.startswith("Total")]
    export_cols = [c for c in hourly_df.columns
                   if c.endswith("_Export_MW") and not c.startswith("Total")]
    if not import_cols or not export_cols:
        print("[Flows] reconciliation check skipped — no per-neighbor columns found.")
        return

    computed_import = hourly_df[import_cols].sum(axis=1, skipna=True)
    computed_export = hourly_df[export_cols].sum(axis=1, skipna=True)
    # Only compare rows where at least one neighbor column is non-null,
    # so fully-missing rows (sum()==0 by construction) don't fake a match.
    has_any_neighbor_import = hourly_df[import_cols].notna().any(axis=1)
    has_any_neighbor_export = hourly_df[export_cols].notna().any(axis=1)

    diff_import = (computed_import - hourly_df["TotalImport_MW"]).abs()
    diff_export = (computed_export - hourly_df["TotalExport_MW"]).abs()
    tol = 1.0  # MW

    comparable_import = diff_import[has_any_neighbor_import & hourly_df["TotalImport_MW"].notna()]
    comparable_export = diff_export[has_any_neighbor_export & hourly_df["TotalExport_MW"].notna()]

    print(f"[Flows] Total vs sum-of-present-neighbors reconciliation (tolerance {tol} MW, "
          f"only rows where both sides have data):")
    if len(comparable_import):
        n_mismatch = (comparable_import > tol).sum()
        print(f"  Import: {n_mismatch}/{len(comparable_import)} comparable rows disagree by >{tol} MW "
              f"(mean abs diff: {comparable_import.mean():.2f} MW)")
    else:
        print("  Import: no comparable rows (no overlap between Total and per-neighbor data).")
    if len(comparable_export):
        n_mismatch = (comparable_export > tol).sum()
        print(f"  Export: {n_mismatch}/{len(comparable_export)} comparable rows disagree by >{tol} MW "
              f"(mean abs diff: {comparable_export.mean():.2f} MW)")
    else:
        print("  Export: no comparable rows (no overlap between Total and per-neighbor data).")


# ============================================================
# DOWNLOAD DRIVERS
# ============================================================

def _get_token_holder() -> dict:
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
    return {"token": token}


def _print_failed(label: str, failed: list, unit: str):
    if not failed:
        return
    print(f"\n{label} {len(failed)} {unit} failed to download after retries:")
    for f in failed[:20]:
        print(f"  - {f}")
    if len(failed) > 20:
        print(f"  ... and {len(failed) - 20} more")
    print(f"{label} Re-run the script — cached (successful) {unit} are skipped, only these will retry.")


def download_prices():
    session = requests.Session()
    token_holder = _get_token_holder()
    days = list(daterange(START_DATE, END_DATE))
    print(f"[Prices] Fetching {len(days)} days...")
    all_rows = []
    failed_days = []
    n_cached = 0
    for i, day in enumerate(days, 1):
        # Check cache BEFORE fetching, so the throttling sleep below only
        # fires for a real network request — it used to fire unconditionally
        # after every day, including cache hits, which meant a mostly-cached
        # rerun (like this one, adding 2 padding days to ~1826 already
        # cached) spent ~30 minutes just sleeping before doing anything.
        was_cached = (PRICES_RAW_DIR / f"{day.isoformat()}.json").exists()
        data = fetch_prices_day(day, session, token_holder)
        if data is None:
            failed_days.append(day)
        else:
            all_rows.extend(flatten_prices_day(data))
        if was_cached:
            n_cached += 1
        else:
            time.sleep(REQUEST_DELAY_SECONDS)
        if i % 200 == 0 or i == len(days):
            print(f"  [Prices] {i}/{len(days)} days processed "
                  f"({n_cached} from cache, {len(failed_days)} failed so far)")
    _print_failed("[Prices]", failed_days, "day(s)")
    _save_raw_hourly(all_rows, "DeliveryStartUTC", "DeliveryEndUTC", ["Price_EUR"], PRICES_OUTPUT_CSV, "[Prices]")


def download_volumes():
    session = requests.Session()
    token_holder = _get_token_holder()
    days = list(daterange(START_DATE, END_DATE))
    print(f"[Volumes] Fetching {len(days)} days...")
    all_rows = []
    failed_days = []
    n_cached = 0
    for i, day in enumerate(days, 1):
        was_cached = (VOLUMES_RAW_DIR / f"{day.isoformat()}.json").exists()
        data = fetch_volumes_day(day, session, token_holder)
        if data is None:
            failed_days.append(day)
        else:
            all_rows.extend(flatten_volumes_day(data))
        if was_cached:
            n_cached += 1
        else:
            time.sleep(REQUEST_DELAY_SECONDS)
        if i % 200 == 0 or i == len(days):
            print(f"  [Volumes] {i}/{len(days)} days processed "
                  f"({n_cached} from cache, {len(failed_days)} failed so far)")
    _print_failed("[Volumes]", failed_days, "day(s)")
    _save_raw_hourly(all_rows, "DeliveryStartUTC", "DeliveryEndUTC", ["BuyVolume_MW", "SellVolume_MW"], VOLUMES_OUTPUT_CSV, "[Volumes]")


def download_flows():
    session = requests.Session()
    token_holder = _get_token_holder()
    days = list(daterange(START_DATE, END_DATE))
    print(f"[Flows] Fetching {len(days)} days x {len(AREAS)} areas...")
    all_rows = []
    failed = []
    n_cached = 0
    total_pairs = len(days) * len(AREAS)
    i = 0
    for day in days:
        for area in AREAS:
            i += 1
            was_cached = (FLOWS_RAW_DIR / f"{day.isoformat()}_{area}.json").exists()
            data = fetch_flows_day_area(day, area, session, token_holder)
            if data is None:
                failed.append((day, area))
            else:
                all_rows.extend(flatten_flows_day_area(data, area))
            if was_cached:
                n_cached += 1
            else:
                time.sleep(REQUEST_DELAY_SECONDS)
            if i % 200 == 0 or i == total_pairs:
                print(f"  [Flows] {i}/{total_pairs} (day, area) pairs processed "
                      f"({n_cached} from cache, {len(failed)} failed so far)")
    _print_failed("[Flows]", failed, "(day, area) pair(s)")

    if not all_rows:
        print("[Flows] No data retrieved.")
        return
    df = pd.DataFrame(all_rows)
    df["DeliveryStartUTC"] = pd.to_datetime(df["DeliveryStartUTC"], utc=True)
    df["DeliveryEndUTC"] = pd.to_datetime(df["DeliveryEndUTC"], utc=True)
    value_cols = [c for c in df.columns if c not in ("DeliveryStartUTC", "DeliveryEndUTC", "Area")]

    _check_daily_completeness(df, "DeliveryStartUTC", "Area", "[Flows]")
    _check_raw_duplicates(df, "DeliveryStartUTC", "Area", "[Flows]")

    rows = []
    for area in AREAS:
        sub = df[df["Area"] == area].set_index("DeliveryStartUTC")
        rows_before = len(sub)
        hourly = sub[value_cols].resample("1h").mean()
        rows_after = len(hourly)
        if rows_after < rows_before:
            print(f"[Flows] {area}: resampled {rows_before} raw rows -> {rows_after} hourly rows "
                  f"({rows_before - rows_after} sub-hourly rows collapsed).")
        else:
            print(f"[Flows] {area}: all {rows_before} rows were already hourly.")
        hourly["Area"] = area
        rows.append(hourly.reset_index())
    hourly_df = pd.concat(rows, ignore_index=True)
    hourly_df = hourly_df.sort_values(["DeliveryStartUTC", "Area"]).reset_index(drop=True)

    hourly_df = _fix_structural_flow_zeros(hourly_df)
    _check_flow_total_reconciliation(hourly_df)

    FLOWS_OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    hourly_df.to_csv(FLOWS_OUTPUT_CSV, index=False)
    print(f"[Flows] Wrote {len(hourly_df)} hourly rows to {FLOWS_OUTPUT_CSV}")


def _save_raw_hourly(all_rows: list[dict], start_col: str, end_col: str, value_cols: list[str], out_path: Path,
                     label: str, areas: list[str] | None = None):
    """Shared helper for prices/volumes: build DataFrame, run the
    completeness/duplicate diagnostics, resample 15-min (where present) to
    hourly via mean per area, save. areas defaults to AREAS (DK1, DK2)."""
    areas = areas if areas is not None else AREAS
    if not all_rows:
        print(f"{label} No data retrieved.")
        return
    df = pd.DataFrame(all_rows)
    df[start_col] = pd.to_datetime(df[start_col], utc=True)
    df[end_col] = pd.to_datetime(df[end_col], utc=True)

    _check_daily_completeness(df, start_col, "Area", label)
    _check_raw_duplicates(df, start_col, "Area", label)

    rows = []
    for area in areas:
        sub = df[df["Area"] == area].set_index(start_col)
        rows_before = len(sub)
        hourly = sub[value_cols].resample("1h").mean()
        rows_after = len(hourly)
        if rows_after < rows_before:
            print(f"{label} {area}: resampled {rows_before} raw rows -> {rows_after} hourly rows "
                  f"({rows_before - rows_after} sub-hourly rows collapsed).")
        else:
            print(f"{label} {area}: all {rows_before} rows were already hourly.")
        hourly["Area"] = area
        rows.append(hourly.reset_index())
    hourly_df = pd.concat(rows, ignore_index=True)
    hourly_df = hourly_df.rename(columns={start_col: "HourUTC"})
    hourly_df = hourly_df.sort_values(["HourUTC", "Area"]).reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    hourly_df.to_csv(out_path, index=False)
    print(f"{label} Wrote {len(hourly_df)} hourly rows to {out_path}")


# ============================================================
# FEATURE OVERVIEW (terminal only)
# ============================================================

def feature_overview():
    """Per-file, per-column coverage report (pct missing, first/last
    non-null), mirroring dataframe/building.py's own coverage_report() —
    so the neighbor-missingness pattern (and everything else) is visible
    right from this pipeline's own output, before the full merge."""
    print(f"\n{'=' * 70}")
    print("DAY-AHEAD (Nord Pool): FEATURE INVENTORY")
    print("=" * 70)
    for name, path, time_col in [
        ("Prices", PRICES_OUTPUT_CSV, "HourUTC"),
        ("Volumes", VOLUMES_OUTPUT_CSV, "HourUTC"),
        ("Flows", FLOWS_OUTPUT_CSV, "DeliveryStartUTC"),
    ]:
        if not Path(path).exists():
            print(f"\n{name}: NOT YET BUILT ({path})")
            continue
        df = pd.read_csv(path)
        df[time_col] = pd.to_datetime(df[time_col], utc=True)
        print(f"\n{name}")
        print(f"  file: {path}")
        print(f"  range: {df[time_col].min()} to {df[time_col].max()}")
        print(f"  rows: {len(df)}")
        for area in AREAS:
            print(f"    {area}: {(df['Area'] == area).sum()} rows")

        feature_cols = [c for c in df.columns if c not in (time_col, "Area", "DeliveryEndUTC")]
        cov_rows = []
        for col in feature_cols:
            non_null = df[col].notna()
            cov_rows.append({
                "feature": col,
                "pct_missing": round(100 * (1 - non_null.mean()), 2) if len(df) else 100.0,
                "first_non_null": df.loc[non_null, time_col].min() if non_null.any() else None,
                "last_non_null": df.loc[non_null, time_col].max() if non_null.any() else None,
            })
        cov = pd.DataFrame(cov_rows).sort_values("feature").reset_index(drop=True)
        print(f"\n  Coverage:")
        print(cov.to_string(index=False))

        if name == "Flows":
            _print_flow_missingness_by_year(df, time_col, feature_cols)
            _print_flow_missingness_by_area(df, feature_cols)


def _print_flow_missingness_by_area(df: pd.DataFrame, feature_cols: list):
    """Breaks the ~50% missingness in the per-neighbor flow columns down by
    Area (DK1 vs DK2) instead of by year. The per-year breakdown came back
    flat at 50.0% for every year 2020-2026 with zero variation, which rules
    out a coverage-over-time story. If instead the missingness is really an
    Area split -- one area's rows carry the full byConnectionArea neighbor
    breakdown and the other area's rows only ever report GER -- that would
    also produce exactly 50% missing for every non-GER neighbor column
    regardless of year, matching what was actually observed. This checks
    that directly: 0% missing for one area and 100% for the other (per
    column) confirms it; anything else (e.g. both areas partially missing)
    means the real explanation is still something different."""
    neighbor_cols = [c for c in feature_cols if not c.startswith("Total")]
    if not neighbor_cols:
        return
    rows = []
    for area, g in df.groupby("Area"):
        row = {"Area": area}
        for col in neighbor_cols:
            row[col] = round(100 * g[col].isna().mean(), 1)
        rows.append(row)
    by_area = pd.DataFrame(rows).sort_values("Area").reset_index(drop=True)
    print(f"\n  Per-neighbor % MISSING by Area (0 = fully present for that area, 100 = fully absent):")
    print(by_area.to_string(index=False))


def _print_flow_missingness_by_year(df: pd.DataFrame, time_col: str, feature_cols: list):
    """Breaks the ~50% missingness in the per-neighbor flow columns down by
    calendar year, so the actual PATTERN is visible (a neighbor that's
    missing throughout vs. one that switches on/off at some date needs a
    different fix — a full-year gap says 'restrict the analysis window for
    that feature or use Total* instead'; a clean before/after switch says
    'this column is usable from date X onward'; something scattered/
    inconsistent within a year would be worth a closer look, not just
    accepted as a reporting-coverage story)."""
    d = df.copy()
    d["_year"] = d[time_col].dt.year
    neighbor_cols = [c for c in feature_cols if not c.startswith("Total")]
    if not neighbor_cols:
        return
    rows = []
    for year, g in d.groupby("_year"):
        row = {"year": year}
        for col in neighbor_cols:
            row[col] = round(100 * g[col].isna().mean(), 1)
        rows.append(row)
    by_year = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    print(f"\n  Per-neighbor % MISSING by year (0 = fully present that year, 100 = fully absent):")
    print(by_year.to_string(index=False))


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    RUN_PRICES = True
    RUN_VOLUMES = True
    RUN_FLOWS = True
    RUN_FEATURE_OVERVIEW = True

    if RUN_PRICES:
        download_prices()
    if RUN_VOLUMES:
        download_volumes()
    if RUN_FLOWS:
        download_flows()
    if RUN_FEATURE_OVERVIEW:
        feature_overview()


if __name__ == "__main__":
    main()