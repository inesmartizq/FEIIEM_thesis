"""
import_extras.py

Additional Nord Pool Data Portal imports, one section per dataset. Each
section downloads (with local caching, so a re-run only fetches what is
missing), cleans and saves one processed CSV. Run:

    python src/imports/import_extras.py

You'll be asked for a Nord Pool bearer token (DevTools -> Network -> any
dataportal-api request -> Request Headers -> authorization); paste it with
or without the leading "Bearer ".

DATASETS
--------
Hydro reservoir filling (Nord Pool "Reservoir" report)
    GET /api/Reservoir/Get?deliveryArea=<area>&year=<ISO year>
    One response per (area, ISO year), one entry per ISO week:
        weekStartDate / weekEndDate (Monday-Sunday), currentCapacityInGigawattHours,
        maxCapacityInGigawattHours, utilizationPercentage.
    Areas: FI, NO, NO1-NO5, SE, SE1-SE4 (NO / SE are the country totals).

    Weekly -> hourly: STEP within the week. Every hour gets the value of
    the Monday-Sunday week it falls in, judged in Nordic local time
    (Europe/Oslo = CET/CEST, same as Copenhagen), on a UTC hourly grid.
    NOTE: the weekly reading is only published after the week, so hours
    early in a week see a value that wasn't known yet (up to ~7 days of
    look-ahead). Chosen deliberately; the documentation of any dataframe
    using it should say so.

    ISO years != calendar years: 1-2 Jan 2022 belong to ISO week 52 of 2021
    and 29-31 Dec 2025 to ISO week 1 of 2026, so ISO years 2021-2026 are
    requested. Each (area, week) is kept ONCE; a week returned in two
    responses with different values is reported, never silently picked.

Day-ahead system price + turnover (whole Nordic system, area 'SYS')
    GET /api/DayAheadSystem?date=<CET delivery day>&currency=EUR
    One response per CET delivery day; entries are hourly until 2025-09-30
    and 15-min from 2025-10-01 (SDAC 15-min MTU). 'turnover' per entry is
    MW (average power): checked against each response's block aggregates,
    where block turnover = sum(entry x duration in h) in MWh.
    Hourly = duration-weighted mean of the entries in the hour (price: the
    same averaging as the DK zone prices; turnover: MW mean = MWh traded in
    that hour). Days 2022-01-01 .. 2026-01-01 are requested: the last UTC
    hour of 2025 (23:00) is 00:00 CET on 2026-01-01.

OUTPUT
    data/raw/reservoir/<area>/<ISO year>.json        raw cache
    data/processed/reservoir/reservoir_weekly.csv    one row per (area, week), deduplicated
    data/processed/reservoir/reservoir_2022_2025_hourly.csv
        HourUTC, Area, WeekStartDate, ReservoirCurrent_GWh, ReservoirMax_GWh,
        ReservoirUtilization_pct
    data/raw/day_ahead/system/<CET day>.json         raw cache
    data/processed/day_ahead/system_price_turnover_2022_2025_hourly.csv
        HourUTC, Area (= 'SYS'), Price_EUR, Turnover_MW
"""

import base64
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# ----------------------- CONFIG -----------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/imports/<this file> -> project root
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

BASE_URL = "https://dataportal-api.nordpoolgroup.com/api"

# Analysis window (inclusive dates, UTC hours) of the hourly outputs.
START_DATE = date(2022, 1, 1)
END_DATE = date(2025, 12, 31)

# Paste a token here (with or without "Bearer "), or leave as-is to be asked.
NORDPOOL_BEARER_TOKEN = "PASTE_YOUR_TOKEN_HERE"

REQUEST_DELAY_SECONDS = 1.0   # between real (non-cached) requests
MAX_RETRIES = 6

RUN_RESERVOIR = True
RUN_SYSTEM_PRICE = True
# --------------------------------------------------------


# ============================================================
# SHARED: token + HTTP
# ============================================================

def _clean_token(raw: str) -> str:
    """Strip an optional leading 'Bearer ' (any case) and surrounding
    whitespace, so pasting the token straight out of DevTools works either
    way."""
    raw = raw.strip()
    if raw[:7].lower() == "bearer ":
        raw = raw[7:].strip()
    return raw


def _decode_jwt_exp(token: str) -> datetime | None:
    """Best-effort read of a JWT's expiry, without a jwt library."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    except Exception:  # noqa: BLE001 — not a JWT / no exp: just skip the expiry info
        return None


def _prompt_for_token(reason: str) -> str:
    print("\n" + "=" * 60)
    print(reason)
    print("Grab a token from DevTools (Network tab -> any dataportal-api request")
    print("-> Headers -> Request Headers -> authorization) and paste it below")
    print("(with or without 'Bearer ').")
    print("=" * 60)
    return _clean_token(input("Token: "))


def _get_token_holder() -> dict:
    token = _clean_token(NORDPOOL_BEARER_TOKEN)
    if token == "PASTE_YOUR_TOKEN_HERE" or not token:
        token = _prompt_for_token("A Nord Pool bearer token is needed.")
    exp = _decode_jwt_exp(token)
    if exp:
        minutes = (exp - datetime.now(timezone.utc)).total_seconds() / 60
        print(f"Token expires at {exp.isoformat()} (~{minutes:.0f} min from now).")
        if minutes < 0:
            token = _prompt_for_token("That token is already expired.")
    return {"token": token}


def _headers(token: str) -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://data.nordpoolgroup.com",
        "Referer": "https://data.nordpoolgroup.com/",
        "Authorization": f"Bearer {token}",
    }


def fetch_json(url: str, params: dict, cache_file: Path, session: requests.Session,
               token_holder: dict, label: str) -> dict | None:
    """GET a JSON response, using / filling a local cache file. Handles an
    expired token (401 -> asks for a new one), rate limiting (429 -> waits)
    and transient errors (retries). Returns None if it finally fails; empty
    responses (204) are NOT cached, so they are retried on the next run."""
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, headers=_headers(token_holder["token"]), timeout=30)
        except requests.exceptions.RequestException as e:
            print(f"  {label}: connection error ({e!r}), retry {attempt}/{MAX_RETRIES} in 5 s")
            time.sleep(5)
            continue
        if resp.status_code == 200:
            data = resp.json()
            cache_file.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(REQUEST_DELAY_SECONDS)
            return data
        if resp.status_code == 204:
            print(f"  {label}: no data (204)")
            time.sleep(REQUEST_DELAY_SECONDS)
            return None
        if resp.status_code == 401:
            token_holder["token"] = _prompt_for_token("Token expired or rejected (401).")
            continue
        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After") or min(60, 5 * 2 ** attempt))
            print(f"  {label}: 429, waiting {wait:.0f} s")
            time.sleep(wait)
            continue
        print(f"  {label}: HTTP {resp.status_code} — {resp.text[:200]!r}")
        time.sleep(REQUEST_DELAY_SECONDS)
        return None
    print(f"  {label}: gave up after {MAX_RETRIES} attempts")
    return None


def hourly_utc_index(start: date, end: date) -> pd.DatetimeIndex:
    """Hourly UTC grid, both dates inclusive (end's 24 hours included)."""
    return pd.date_range(pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1),
                         freq="h", tz="UTC", inclusive="left")


# ============================================================
# HYDRO RESERVOIR FILLING (weekly -> hourly)
# ============================================================

RESERVOIR_AREAS = ["FI", "NO", "NO1", "NO2", "NO3", "NO4", "NO5", "SE", "SE1", "SE2", "SE3", "SE4"]
RESERVOIR_TOTALS = {"NO": ["NO1", "NO2", "NO3", "NO4", "NO5"], "SE": ["SE1", "SE2", "SE3", "SE4"]}
RESERVOIR_LOCAL_TZ = "Europe/Oslo"  # Nordic market time (CET/CEST); weeks run Monday-Sunday in it
RESERVOIR_URL = f"{BASE_URL}/Reservoir/Get"
RESERVOIR_RAW_DIR = RAW_DIR / "reservoir"
RESERVOIR_OUT_DIR = PROCESSED_DIR / "reservoir"
RESERVOIR_VALUES = {
    "currentCapacityInGigawattHours": "ReservoirCurrent_GWh",
    "maxCapacityInGigawattHours": "ReservoirMax_GWh",
    "utilizationPercentage": "ReservoirUtilization_pct",
}


def _reservoir_iso_years() -> list[int]:
    """ISO years whose weeks cover every hour of [START_DATE, END_DATE] in
    Nordic local time (the first UTC hour is 01:00 local on START_DATE, the
    last ends 01:00 local the day after END_DATE)."""
    first = START_DATE.isocalendar().year
    last = (pd.Timestamp(END_DATE) + pd.Timedelta(days=1)).isocalendar().year
    return list(range(first, last + 1))


def _flatten_reservoir(data: dict, area: str, requested_year: int) -> list[dict]:
    if data.get("deliveryArea") != area or data.get("isoYear") != requested_year:
        print(f"  WARNING — response for {area} {requested_year} says area "
              f"{data.get('deliveryArea')!r}, isoYear {data.get('isoYear')!r}")
    rows = []
    for e in data.get("content", []):
        rows.append({
            "Area": area,
            "IsoYear": requested_year,
            "IsoWeek": e.get("isoWeek"),
            "WeekStartDate": e.get("weekStartDate"),
            "WeekEndDate": e.get("weekEndDate"),
            "UpdatedAt": data.get("updatedAt"),
            **{new: e.get(old) for old, new in RESERVOIR_VALUES.items()},
        })
    return rows


def _deduplicate_weeks(weekly: pd.DataFrame) -> pd.DataFrame:
    """One row per (Area, WeekStartDate). Identical repeats are dropped
    quietly; repeats with DIFFERENT values are reported and the most
    recently updated one is kept."""
    value_cols = list(RESERVOIR_VALUES.values())
    dup = weekly.duplicated(["Area", "WeekStartDate"], keep=False)
    if dup.any():
        groups = weekly[dup].groupby(["Area", "WeekStartDate"])
        conflicts = [k for k, g in groups if len(g[value_cols].drop_duplicates()) > 1]
        print(f"  {int(dup.sum())} rows share an (area, week) with another response; "
              f"{len(conflicts)} of those weeks have DIFFERENT values")
        for k in conflicts[:20]:
            print(f"    conflict {k}: keeping the most recently updated value")
    weekly = weekly.sort_values(["Area", "WeekStartDate", "UpdatedAt"])
    return weekly.drop_duplicates(["Area", "WeekStartDate"], keep="last").reset_index(drop=True)


def _check_weekly(weekly: pd.DataFrame):
    """Structural checks: Monday starts, 7-day weeks, no missing weeks,
    utilization consistent with current/max, country totals = sum of
    sub-areas."""
    start = pd.to_datetime(weekly["WeekStartDate"])
    end = pd.to_datetime(weekly["WeekEndDate"])
    bad = weekly[(start.dt.dayofweek != 0) | ((end - start).dt.days != 6)]
    print(f"  weeks not Monday-Sunday: {len(bad)}")

    for area, g in weekly.groupby("Area"):
        s = pd.to_datetime(g["WeekStartDate"]).sort_values()
        gaps = s.diff().dt.days.dropna()
        missing = int((gaps // 7 - 1).clip(lower=0).sum())
        if missing:
            print(f"  WARNING — {area}: {missing} missing week(s) between {s.min().date()} and {s.max().date()}")

    implied = 100 * weekly["ReservoirCurrent_GWh"] / weekly["ReservoirMax_GWh"]
    off = (implied - weekly["ReservoirUtilization_pct"]).abs()
    print(f"  utilization vs current/max: max abs difference {off.max():.2f} percentage points "
          f"(rounding to 0.1 expected)")

    wide = weekly.pivot(index="WeekStartDate", columns="Area", values="ReservoirCurrent_GWh")
    for total, parts in RESERVOIR_TOTALS.items():
        cols = [total, *parts]
        if not set(cols) <= set(wide.columns):
            continue
        both = wide[cols].dropna()
        diff = (both[total] - both[parts].sum(axis=1)).abs()
        rel = diff / both[total].abs()
        print(f"  {total} vs sum of {'+'.join(parts)}: {len(both)} common weeks, max abs diff "
              f"{diff.max():.1f} GWh ({100 * rel.max():.2f} %), weeks off by > 0.5 %: {int((rel > 0.005).sum())}")


def _weekly_to_hourly(weekly: pd.DataFrame) -> pd.DataFrame:
    """STEP within the week: each UTC hour takes the value of the
    Monday-Sunday week its Nordic LOCAL time falls in."""
    hours = hourly_utc_index(START_DATE, END_DATE)
    local_day = hours.tz_convert(RESERVOIR_LOCAL_TZ).tz_localize(None).normalize()
    week_start = (local_day - pd.to_timedelta(local_day.dayofweek, unit="D")).strftime("%Y-%m-%d")
    grid = pd.DataFrame({"HourUTC": hours, "WeekStartDate": week_start})
    out = []
    for area in RESERVOIR_AREAS:
        g = weekly[weekly["Area"] == area][["WeekStartDate", *RESERVOIR_VALUES.values()]]
        merged = grid.merge(g, on="WeekStartDate", how="left")
        merged.insert(1, "Area", area)
        missing = merged["ReservoirCurrent_GWh"].isna()
        if missing.any():
            weeks = sorted(merged.loc[missing, "WeekStartDate"].unique())
            print(f"  WARNING — {area}: {int(missing.sum())} hour(s) without a weekly value "
                  f"(weeks starting {weeks[:5]}{' ...' if len(weeks) > 5 else ''})")
        out.append(merged)
    return pd.concat(out, ignore_index=True)


def download_reservoir():
    print(f"[Reservoir] areas {RESERVOIR_AREAS}, ISO years {_reservoir_iso_years()}")
    session = requests.Session()
    token_holder = _get_token_holder()
    rows, failed = [], []
    for area in RESERVOIR_AREAS:
        for year in _reservoir_iso_years():
            data = fetch_json(RESERVOIR_URL, {"deliveryArea": area, "year": year},
                              RESERVOIR_RAW_DIR / area / f"{year}.json", session, token_holder,
                              f"reservoir {area} {year}")
            if data is None:
                failed.append((area, year))
                continue
            rows.extend(_flatten_reservoir(data, area, year))
    if failed:
        print(f"[Reservoir] {len(failed)} request(s) failed (re-run to retry): {failed}")
    if not rows:
        print("[Reservoir] no data — nothing written.")
        return

    weekly = _deduplicate_weeks(pd.DataFrame(rows))
    print("[Reservoir] checks:")
    _check_weekly(weekly)
    RESERVOIR_OUT_DIR.mkdir(parents=True, exist_ok=True)
    weekly.sort_values(["Area", "WeekStartDate"]).to_csv(RESERVOIR_OUT_DIR / "reservoir_weekly.csv", index=False)

    hourly = _weekly_to_hourly(weekly)
    out = RESERVOIR_OUT_DIR / f"reservoir_{START_DATE.year}_{END_DATE.year}_hourly.csv"
    hourly.to_csv(out, index=False)
    print(f"[Reservoir] wrote {len(weekly)} weekly rows and {len(hourly)} hourly rows "
          f"({len(RESERVOIR_AREAS)} areas x {len(hourly) // len(RESERVOIR_AREAS)} hours) -> {out}")


# ============================================================
# DAY-AHEAD SYSTEM PRICE + TURNOVER (whole Nordic system, no zone)
# ============================================================

SYSTEM_URL = f"{BASE_URL}/DayAheadSystem"
SYSTEM_RAW_DIR = RAW_DIR / "day_ahead" / "system"
SYSTEM_OUT_DIR = PROCESSED_DIR / "day_ahead"
SYSTEM_AREA = "SYS"
SYSTEM_TOLERANCE = 0.02  # block checks: allowed relative deviation (Nord Pool rounds)


def _system_days() -> list[date]:
    """CET delivery days covering every UTC hour of [START_DATE, END_DATE]:
    the last UTC hour (23:00 on END_DATE) is 00:00 CET of the NEXT day."""
    return list(pd.date_range(START_DATE, pd.Timestamp(END_DATE) + pd.Timedelta(days=1), freq="D").date)


def _flatten_system(data: dict, day: date) -> list[dict]:
    if data.get("deliveryDateCET") != day.isoformat() or data.get("currency") != "EUR":
        print(f"  WARNING — system {day}: response says day {data.get('deliveryDateCET')!r}, "
              f"currency {data.get('currency')!r}")
    state = (data.get("areaState") or {}).get("state")
    if state != "Final":
        print(f"  WARNING — system {day}: state {state!r} (not 'Final')")
    return [{"DeliveryDateCET": data.get("deliveryDateCET"),
             "DeliveryStartUTC": e.get("deliveryStart"), "DeliveryEndUTC": e.get("deliveryEnd"),
             "Price_EUR": e.get("price"), "Turnover_MW": e.get("turnover")}
            for e in data.get("multiDataEntries", [])]


def _check_system_blocks(responses: dict, raw: pd.DataFrame):
    """Each response's block aggregates (Peak / Off-peak 1 / Off-peak 2) vs
    the entries inside the block: averagePrice should equal the mean price
    and turnover the sum of entry_value x duration_in_hours. That second
    check is what confirms 'turnover' per entry is MW (average power) and
    the block turnover MWh."""
    worst_price, worst_turn, n_bad, n_blocks = 0.0, 0.0, 0, 0
    for day, data in responses.items():
        day_rows = raw[raw["DeliveryDateCET"] == day.isoformat()]
        for b in data.get("blockDataAggregates", []):
            start, end = pd.Timestamp(b["blockStart"]), pd.Timestamp(b["blockEnd"])
            inside = day_rows[(day_rows["DeliveryStartUTC"] >= start) & (day_rows["DeliveryEndUTC"] <= end)]
            if inside.empty:
                continue
            hours = (inside["DeliveryEndUTC"] - inside["DeliveryStartUTC"]).dt.total_seconds() / 3600
            price_dev = abs(inside["Price_EUR"].mean() - b["averagePrice"])
            turn_rel = abs((inside["Turnover_MW"] * hours).sum() - b["turnover"]) / max(abs(b["turnover"]), 1)
            worst_price, worst_turn = max(worst_price, price_dev), max(worst_turn, turn_rel)
            n_blocks += 1
            n_bad += turn_rel > SYSTEM_TOLERANCE or price_dev > 0.05
    print(f"  block check on {n_blocks} blocks: max |mean price - block average| = {worst_price:.3f} EUR/MWh; "
          f"max relative turnover deviation = {100 * worst_turn:.3f} % "
          f"({n_bad} block(s) beyond tolerance)")
    if n_bad == 0:
        print("  -> confirmed: turnover per entry is MW (average power), block turnover MWh")
    else:
        print("  WARNING — blocks don't match: check the units / averaging before using these values")


def _system_to_hourly(raw: pd.DataFrame) -> pd.DataFrame:
    """Hourly UTC values: duration-weighted mean of the entries in each hour
    (hourly entries -> unchanged; four 15-min entries -> their mean). For a
    MW quantity that mean equals the MWh traded in the hour. An hour is kept
    only if its entries cover the full 60 minutes; otherwise NaN + warning."""
    r = raw.copy()
    r["minutes"] = (r["DeliveryEndUTC"] - r["DeliveryStartUTC"]).dt.total_seconds() / 60
    r["HourUTC"] = r["DeliveryStartUTC"].dt.floor("h")
    for col in ("Price_EUR", "Turnover_MW"):
        r[f"{col}_w"] = r[col] * r["minutes"]
    g = r.groupby("HourUTC")
    hourly = pd.DataFrame({
        "covered_min": g["minutes"].sum(),
        "Price_EUR": g["Price_EUR_w"].sum(min_count=1) / g["minutes"].sum(),
        "Turnover_MW": g["Turnover_MW_w"].sum(min_count=1) / g["minutes"].sum(),
    })
    incomplete = hourly["covered_min"] != 60
    if incomplete.any():
        print(f"  WARNING — {int(incomplete.sum())} hour(s) not fully covered by entries -> NaN: "
              f"{[str(t) for t in hourly.index[incomplete][:5]]}")
        hourly.loc[incomplete, ["Price_EUR", "Turnover_MW"]] = float("nan")
    grid = hourly_utc_index(START_DATE, END_DATE)
    out = hourly.reindex(grid)[["Price_EUR", "Turnover_MW"]]
    missing = out["Price_EUR"].isna()
    if missing.any():
        print(f"  WARNING — {int(missing.sum())} hour(s) of the 2022-2025 grid without a system price: "
              f"{[str(t) for t in out.index[missing][:5]]}")
    out = out.rename_axis("HourUTC").reset_index()
    out.insert(1, "Area", SYSTEM_AREA)
    return out


def download_system_price():
    days = _system_days()
    print(f"[System price] {len(days)} CET delivery days {days[0]} .. {days[-1]} "
          f"(first run ~{len(days) * REQUEST_DELAY_SECONDS / 60:.0f} min; cached afterwards)")
    session = requests.Session()
    token_holder = _get_token_holder()
    responses, rows, failed = {}, [], []
    for i, day in enumerate(days, 1):
        data = fetch_json(SYSTEM_URL, {"date": day.isoformat(), "currency": "EUR"},
                          SYSTEM_RAW_DIR / f"{day.isoformat()}.json", session, token_holder,
                          f"system {day}")
        if data is None:
            failed.append(day)
        else:
            responses[day] = data
            rows.extend(_flatten_system(data, day))
        if i % 200 == 0 or i == len(days):
            print(f"  [System price] {i}/{len(days)} days ({len(failed)} failed)")
    if failed:
        print(f"[System price] {len(failed)} day(s) failed (re-run to retry): {failed[:10]}")
    if not rows:
        print("[System price] no data — nothing written.")
        return

    raw = pd.DataFrame(rows)
    raw["DeliveryStartUTC"] = pd.to_datetime(raw["DeliveryStartUTC"], utc=True)
    raw["DeliveryEndUTC"] = pd.to_datetime(raw["DeliveryEndUTC"], utc=True)
    dup = raw.duplicated("DeliveryStartUTC", keep=False)
    if dup.any():
        conflicting = raw[dup].groupby("DeliveryStartUTC")[["Price_EUR", "Turnover_MW"]].nunique().gt(1).any(axis=1)
        print(f"  {int(dup.sum())} entries appear in two responses; {int(conflicting.sum())} with different "
              f"values (kept the later delivery day's response)")
        raw = raw.sort_values(["DeliveryStartUTC", "DeliveryDateCET"]).drop_duplicates("DeliveryStartUTC", keep="last")
    per_day = raw.groupby("DeliveryDateCET").size()
    print(f"  entries per CET day: {per_day.value_counts().sort_index().to_dict()} "
          f"(24 hourly / 96 quarter-hourly; 23/25 and 92/100 on DST days)")
    print("[System price] checks:")
    _check_system_blocks(responses, raw)

    hourly = _system_to_hourly(raw)
    SYSTEM_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = SYSTEM_OUT_DIR / f"system_price_turnover_{START_DATE.year}_{END_DATE.year}_hourly.csv"
    hourly.to_csv(out, index=False)
    print(f"[System price] wrote {len(hourly)} hourly rows -> {out}")


# ============================================================
# MAIN
# ============================================================

def main():
    if RUN_RESERVOIR:
        download_reservoir()
    if RUN_SYSTEM_PRICE:
        download_system_price()


if __name__ == "__main__":
    main()
