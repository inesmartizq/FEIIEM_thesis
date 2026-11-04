"""
Downloads Nord Pool "Power System" day-ahead production/consumption
forecasts and actuals for DK1/DK2, and combines them into ONE processed,
analysis-ready CSV of forecast + actual renewable generation and load.

Endpoints (all on dataportal-api.nordpoolgroup.com, bearer token auth,
same auth family as the market-data endpoints used in the other import_*
pipelines):

    Production forecast (per-area call, 15-min resolution):
        GET /api/ProductionDataPrognoses?date=YYYY-MM-DD&deliveryArea=DK1&location=
        content[].forecastByType.{Solar,WindOffshore,WindOnshore}.dayAheadPrognosis
        content[].totalDayAheadPrognosis   <- sum of the 3 renewable types ONLY

    Production actual (per-area call, 15-min resolution):
        GET /api/ProductionData?date=YYYY-MM-DD&deliveryArea=DK1&location=
        content[].byType.{Biomass,FossilGas,FossilHardCoal,FossilOil,
                           Solar,Waste,WindOffshore,WindOnshore}
        content[].total   <- sum of ALL 8 types, NOT comparable to the
                             forecast total above. We do NOT use this field;
                             instead we compute our own Solar+WindOffshore+
                             WindOnshore total so it's actually comparable
                             to totalDayAheadPrognosis.

    Consumption forecast (single call, both areas, hourly resolution):
        GET /api/ConsumptionPrognoses?date=YYYY-MM-DD&deliveryAreas=DK1,DK2&locations=
        multiAreaEntries[].entryPerArea.{DK1,DK2}.volume

    Consumption actual (single call, both areas, hourly resolution):
        GET /api/Consumption?date=YYYY-MM-DD&deliveryAreas=DK1,DK2&locations=
        multiAreaEntries[].entryPerArea.{DK1,DK2}.volume

Process:
    1. DOWNLOAD (parallel): every (dataset, day, area) combination is one
       request, cached to data/raw/da_forecasts/<dataset>/[<area>/]<date>.json.
       Requests run concurrently through a bounded thread pool with a shared
       rate limiter and thread-safe token refresh, so a run can use several
       workers without tripping rate limits or double-prompting for a token.
    2. PROCESS: read every cached file back off disk, resample the two
       15-min production series to hourly (mean, since these are MW power
       values), leave the two already-hourly consumption series as-is, and
       left-join everything onto one (time_utc, area) grid.
    3. SAVE: one CSV, data/processed/da_forecasts/da_forecasts_and_actual.csv.

Usage:
    pip install requests pandas
    python import_da_forecasts_pipeline.py
    (you'll be prompted to paste a bearer token from DevTools; pasting it
    with or without the "Bearer " prefix both work)
"""

import json
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

# ----------------------- CONFIG -----------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/imports/<this file> -> project root
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "da_forecasts"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "da_forecasts"
OUTPUT_CSV = PROCESSED_DIR / "da_forecasts_and_actual.csv"

AREAS = ["DK1", "DK2"]
# Padded one calendar day on each side of the analysis window (2022-01-01 to
# 2025-12-31). Nord Pool requests are by CET delivery day while timestamps are
# UTC (genuine UTC — see dataframe/building.py's TIMEZONE NOTE), so the first
# UTC hour of 2022-01-01 belongs to CET day 2022-01-01 but the last UTC hours of
# 2025-12-31 run into CET day 2026-01-01. The surplus days are dropped when the
# dataframe is built.
START_DATE = date(2021, 12, 31)
END_DATE = date(2026, 1, 1)

BASE_URL = "https://dataportal-api.nordpoolgroup.com/api"

MAX_WORKERS = 3             # concurrent requests
STARTING_REQUESTS_PER_SEC = 2.0   # shared rate limit across all workers, adapts down on 429s
MIN_REQUESTS_PER_SEC = 0.3
MAX_REQUESTS_PER_SEC = 5.0
MAX_RETRIES = 8

RUN_DOWNLOAD = True
RUN_PROCESS = True
# --------------------------------------------------------


# ---------------------------------------------------------------------------
# Thread-safe token handling
# ---------------------------------------------------------------------------
_token_lock = threading.Lock()
TOKEN_HOLDER = {"token": None}


def _clean_token(raw: str) -> str:
    """Strip an optional leading 'Bearer ' (any case) and surrounding
    whitespace, so pasting the token straight out of DevTools works either
    way."""
    raw = raw.strip()
    if raw[:7].lower() == "bearer ":
        raw = raw[7:].strip()
    return raw


def _prompt_for_new_token(reason: str):
    """Prompt for a fresh token. Called under _token_lock, so only one
    thread ever prompts at a time; others just pick up the refreshed token
    once this returns."""
    print(f"\n[token] {reason}")
    raw = input("Paste a fresh bearer token (with or without 'Bearer '): ")
    TOKEN_HOLDER["token"] = _clean_token(raw)
    print("[token] updated.\n")


def get_token() -> str:
    with _token_lock:
        if not TOKEN_HOLDER["token"]:
            _prompt_for_new_token("No token set yet.")
        return TOKEN_HOLDER["token"]


def refresh_token_if_still_stale(stale_token: str):
    """Called after a 401. Only actually prompts if no other thread already
    refreshed past the token that just failed."""
    with _token_lock:
        if TOKEN_HOLDER["token"] == stale_token:
            _prompt_for_new_token("Token expired (401) — need a new one.")


# ---------------------------------------------------------------------------
# Shared, ADAPTIVE rate limiter (thread-safe), using a minimum-interval
# approach rather than a per-second window — correct at any rate, including
# well under 1 request/sec (a window-based bucket can't actually enforce
# "1 request every 3 seconds" using a 1-second window; a min-interval check
# can).
#
# Behaves like TCP congestion control: every 429 halves the current rate
# (down to a floor), and the rate only creeps back up gradually after a run
# of consecutive successes. A CIRCUIT BREAKER on top: if 429s keep arriving
# in a short window even after backing off, that usually means we tripped a
# server-side time-window quota (Cloudflare-style), not that our per-request
# pace is slightly too fast — the fix is a real pause (tens of seconds),
# not a smaller number. All threads block on the same cooldown when it's
# active, rather than continuing to hammer the server while "backed off."
# ---------------------------------------------------------------------------
class AdaptiveRateLimiter:
    def __init__(self, starting_rate: float, min_rate: float, max_rate: float):
        self.rate = starting_rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.lock = threading.Lock()
        self._last_request_at = 0.0
        self._consecutive_successes = 0
        self._recent_throttles = deque()   # timestamps of recent 429s
        self._cooldown_until = 0.0

    def wait(self):
        while True:
            with self.lock:
                now = time.monotonic()
                if now < self._cooldown_until:
                    sleep_for = self._cooldown_until - now
                else:
                    min_interval = 1.0 / self.rate
                    sleep_for = (self._last_request_at + min_interval) - now
                    if sleep_for <= 0:
                        self._last_request_at = now
                        return
            time.sleep(max(sleep_for, 0.01))

    def on_throttled(self):
        with self.lock:
            old = self.rate
            self.rate = max(self.rate * 0.5, self.min_rate)
            self._consecutive_successes = 0
            if old != self.rate:
                print(f"[rate limiter] backing off: {old:.2f} -> {self.rate:.2f} req/s")

            now = time.monotonic()
            self._recent_throttles.append(now)
            while self._recent_throttles and now - self._recent_throttles[0] > 20.0:
                self._recent_throttles.popleft()
            if len(self._recent_throttles) >= 8 and now >= self._cooldown_until:
                cooldown_s = 60.0
                self._cooldown_until = now + cooldown_s
                self._recent_throttles.clear()
                print(f"[rate limiter] CIRCUIT BREAKER: {8}+ 429s in 20s even while backing off — "
                      f"this looks like a server-side time-window quota, not a pace problem. "
                      f"Pausing ALL requests for {cooldown_s:.0f}s.")

    def on_success(self):
        with self.lock:
            self._consecutive_successes += 1
            # Additive increase: only after a solid run of successes, and
            # slowly, so we don't immediately re-trigger the wall we just
            # backed off from.
            if self._consecutive_successes >= 100 and self.rate < self.max_rate:
                self._consecutive_successes = 0
                old = self.rate
                self.rate = min(self.rate + 0.25, self.max_rate)
                print(f"[rate limiter] easing up: {old:.2f} -> {self.rate:.2f} req/s")


_rate_limiter = AdaptiveRateLimiter(STARTING_REQUESTS_PER_SEC, MIN_REQUESTS_PER_SEC, MAX_REQUESTS_PER_SEC)
_session = requests.Session()


def api_get(path: str, params: dict) -> dict | None:
    """GET one endpoint with shared adaptive rate limiting, thread-safe
    token refresh on 401, and jittered retry with backoff on 429/5xx.
    Returns the parsed JSON body, or None if it never succeeded after
    MAX_RETRIES."""
    for attempt in range(1, MAX_RETRIES + 1):
        token = get_token()
        _rate_limiter.wait()
        try:
            resp = _session.get(
                f"{BASE_URL}/{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=30,
            )
        except requests.RequestException as e:
            wait_s = min(2 ** attempt, 60) + random.uniform(0, 1)
            print(f"[retry {attempt}/{MAX_RETRIES}] {path} {params}: network error {e}, waiting {wait_s:.1f}s")
            time.sleep(wait_s)
            continue

        if resp.status_code == 200:
            _rate_limiter.on_success()
            return resp.json()
        if resp.status_code == 401:
            refresh_token_if_still_stale(token)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            _rate_limiter.on_throttled()
            our_backoff = min(3 ** attempt, 90)
            retry_after = resp.headers.get("Retry-After")
            server_wait = None
            if retry_after is not None:
                try:
                    server_wait = float(retry_after)
                except ValueError:
                    server_wait = None
            # A server-given wait under 1s (e.g. "Retry-After: 0") is not
            # useful guidance — trust it only when it's at least as long as
            # our own backoff would be; otherwise use our own schedule.
            wait_s = server_wait if (server_wait is not None and server_wait >= our_backoff) else our_backoff
            wait_s += random.uniform(0, wait_s * 0.3)  # jitter: desyncs concurrent retries
            print(f"[retry {attempt}/{MAX_RETRIES}] {path} {params}: HTTP {resp.status_code}, waiting {wait_s:.1f}s")
            time.sleep(wait_s)
            continue
        # Any other error (400, 404, ...) — not retryable, log and give up.
        print(f"[error] {path} {params}: HTTP {resp.status_code} — {resp.text[:200]}")
        return None

    print(f"[FAILED] {path} {params}: gave up after {MAX_RETRIES} attempts")
    return None


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ---------------------------------------------------------------------------
# Per-dataset fetch + cache. Each returns True if the cache file exists (or
# was just written) with valid content, False if the fetch failed.
# ---------------------------------------------------------------------------
def _cache_path_area(dataset: str, area: str, day: date) -> Path:
    return RAW_DIR / dataset / area / f"{day.isoformat()}.json"


def _cache_path_multi(dataset: str, day: date) -> Path:
    return RAW_DIR / dataset / f"{day.isoformat()}.json"


def fetch_production_forecast(day: date, area: str) -> bool:
    path = _cache_path_area("production_forecast", area, day)
    if path.exists():
        return True
    data = api_get("ProductionDataPrognoses", {"date": day.isoformat(), "deliveryArea": area, "location": ""})
    if data is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return True


def fetch_production_actual(day: date, area: str) -> bool:
    path = _cache_path_area("production_actual", area, day)
    if path.exists():
        return True
    data = api_get("ProductionData", {"date": day.isoformat(), "deliveryArea": area, "location": ""})
    if data is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return True


def fetch_consumption_forecast(day: date) -> bool:
    path = _cache_path_multi("consumption_forecast", day)
    if path.exists():
        return True
    data = api_get("ConsumptionPrognoses", {"date": day.isoformat(), "deliveryAreas": "DK1,DK2", "locations": ""})
    if data is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return True


def fetch_consumption_actual(day: date) -> bool:
    path = _cache_path_multi("consumption_actual", day)
    if path.exists():
        return True
    data = api_get("Consumption", {"date": day.isoformat(), "deliveryAreas": "DK1,DK2", "locations": ""})
    if data is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return True


def download_all():
    """Build the full (dataset, day, area) task list and drain it through a
    bounded thread pool. Tasks whose cache file already exists return
    immediately, so a rerun after an interruption only fetches what's
    missing."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tasks = []
    for day in daterange(START_DATE, END_DATE):
        for area in AREAS:
            tasks.append(("production_forecast", fetch_production_forecast, (day, area)))
            tasks.append(("production_actual", fetch_production_actual, (day, area)))
        tasks.append(("consumption_forecast", fetch_consumption_forecast, (day,)))
        tasks.append(("consumption_actual", fetch_consumption_actual, (day,)))

    print(f"Total requests to process (cached ones will be skipped instantly): {len(tasks)}")

    completed = 0
    failed = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fn, *args): (name, args) for name, fn, args in tasks}
        for fut in as_completed(futures):
            name, args = futures[fut]
            ok = fut.result()
            completed += 1
            if not ok:
                failed.append((name, args))
            if completed % 200 == 0 or completed == len(tasks):
                print(f"  {completed}/{len(tasks)} done ({len(failed)} failed so far)")

    if failed:
        print(f"\n{len(failed)} request(s) failed after retries:")
        for name, args in failed[:20]:
            print(f"  - {name} {args}")
        if len(failed) > 20:
            print(f"  ... and {len(failed) - 20} more")
        print("Rerun the script — cached (successful) requests are skipped, only these will retry.")
    else:
        print("\nAll requests succeeded.")


# ---------------------------------------------------------------------------
# PROCESS: read cache back off disk, resample, combine into one CSV
# ---------------------------------------------------------------------------
def _resample_15min_to_hourly_mean(df: pd.DataFrame, time_col: str, area_col: str, value_cols: list) -> pd.DataFrame:
    """MW power values: hourly mean of the four 15-min values is the
    physically-correct aggregation (mirrors resample_to_hourly() in
    import_balancing_pipeline.py)."""
    df = df.copy()
    df["_HourFloor"] = df[time_col].dt.floor("1h")
    rows_before = len(df)
    agg_map = {c: "mean" for c in value_cols}
    out = df.groupby([area_col, "_HourFloor"], sort=False).agg(agg_map).reset_index()
    out = out.rename(columns={"_HourFloor": "time_utc", area_col: "area"})
    rows_after = len(out)
    print(f"    resampled {rows_before} rows (15-min) -> {rows_after} rows (hourly)")
    return out


def load_production_forecast() -> pd.DataFrame:
    print("[production_forecast] loading cached files...")
    rows = []
    for area in AREAS:
        for day in daterange(START_DATE, END_DATE):
            path = _cache_path_area("production_forecast", area, day)
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            for entry in data.get("content", []):
                fbt = entry.get("forecastByType", {})
                rows.append({
                    "time_utc": entry["deliveryStart"],
                    "area": area,
                    "c_solar_forecast_mw": fbt.get("Solar", {}).get("dayAheadPrognosis"),
                    "c_wind_offshore_forecast_mw": fbt.get("WindOffshore", {}).get("dayAheadPrognosis"),
                    "c_wind_onshore_forecast_mw": fbt.get("WindOnshore", {}).get("dayAheadPrognosis"),
                    "c_renewables_total_forecast_mw": entry.get("totalDayAheadPrognosis"),
                })
    if not rows:
        print("  no cached files found — skipping.")
        return pd.DataFrame(columns=["time_utc", "area"])
    df = pd.DataFrame(rows)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    value_cols = ["c_solar_forecast_mw", "c_wind_offshore_forecast_mw",
                  "c_wind_onshore_forecast_mw", "c_renewables_total_forecast_mw"]
    return _resample_15min_to_hourly_mean(df, "time_utc", "area", value_cols)


def load_production_actual() -> pd.DataFrame:
    print("[production_actual] loading cached files...")
    rows = []
    for area in AREAS:
        for day in daterange(START_DATE, END_DATE):
            path = _cache_path_area("production_actual", area, day)
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            for entry in data.get("content", []):
                bt = entry.get("byType", {})
                rows.append({
                    "time_utc": entry["deliveryStart"],
                    "area": area,
                    # bt.get(...) with no default: None (JSON null) stays
                    # None here, distinct from a genuine 0.0 reading. The
                    # total below is computed from these SAME values via
                    # pandas addition (NaN-propagating), not Python's `or 0`
                    # — a missing component makes the total NaN too, rather
                    # than silently counting a missing reading as zero
                    # generation. Deliberately NOT the raw all-source
                    # 'total' field — computed to match the forecast's
                    # renewables-only definition so the two are comparable.
                    "c_solar_actual_mw": bt.get("Solar"),
                    "c_wind_offshore_actual_mw": bt.get("WindOffshore"),
                    "c_wind_onshore_actual_mw": bt.get("WindOnshore"),
                })
    if not rows:
        print("  no cached files found — skipping.")
        return pd.DataFrame(columns=["time_utc", "area"])
    df = pd.DataFrame(rows)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    n_missing = {
        "c_solar_actual_mw": df["c_solar_actual_mw"].isna().sum(),
        "c_wind_offshore_actual_mw": df["c_wind_offshore_actual_mw"].isna().sum(),
        "c_wind_onshore_actual_mw": df["c_wind_onshore_actual_mw"].isna().sum(),
    }
    print(f"  null (not just zero) 15-min readings per component: {n_missing}")
    # pandas '+' propagates NaN: any interval missing a component makes the
    # total NaN for that interval too, instead of masking it as a real 0.
    df["c_renewables_total_actual_mw"] = (
        df["c_solar_actual_mw"] + df["c_wind_offshore_actual_mw"] + df["c_wind_onshore_actual_mw"]
    )
    value_cols = ["c_solar_actual_mw", "c_wind_offshore_actual_mw",
                  "c_wind_onshore_actual_mw", "c_renewables_total_actual_mw"]
    return _resample_15min_to_hourly_mean(df, "time_utc", "area", value_cols)


def _load_multiarea_hourly(dataset: str, value_name: str) -> pd.DataFrame:
    rows = []
    for day in daterange(START_DATE, END_DATE):
        path = _cache_path_multi(dataset, day)
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for entry in data.get("multiAreaEntries", []):
            for area, vals in entry.get("entryPerArea", {}).items():
                if area not in AREAS:
                    continue
                rows.append({
                    "time_utc": entry["deliveryStart"],
                    "area": area,
                    value_name: vals.get("volume"),
                })
    if not rows:
        print(f"  [{dataset}] no cached files found — skipping.")
        return pd.DataFrame(columns=["time_utc", "area"])
    df = pd.DataFrame(rows)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    print(f"  [{dataset}] {len(df)} rows loaded (already hourly, no resampling needed)")
    return df


def load_consumption_forecast() -> pd.DataFrame:
    print("[consumption_forecast] loading cached files...")
    return _load_multiarea_hourly("consumption_forecast", "c_load_forecast_mw")


def load_consumption_actual() -> pd.DataFrame:
    print("[consumption_actual] loading cached files...")
    return _load_multiarea_hourly("consumption_actual", "c_load_actual_mw")


def process_all():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    idx = pd.MultiIndex.from_product(
        [pd.date_range(START_DATE.isoformat(), (END_DATE + timedelta(days=1)).isoformat(),
                        freq="h", tz="UTC", inclusive="left"), AREAS],
        names=["time_utc", "area"],
    )
    grid = pd.DataFrame(index=idx).reset_index()

    for loader in (load_production_forecast, load_production_actual,
                   load_consumption_forecast, load_consumption_actual):
        src = loader()
        if src.empty:
            continue
        grid = grid.merge(src, on=["time_utc", "area"], how="left")

    grid = grid.sort_values(["time_utc", "area"]).reset_index(drop=True)

    feature_cols = [c for c in grid.columns if c not in ("time_utc", "area")]
    print("\nCoverage:")
    for col in feature_cols:
        non_null = grid[col].notna()
        pct = round(100 * (1 - non_null.mean()), 2) if len(grid) else 100.0
        print(f"  {col}: {pct}% missing")

    grid.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {OUTPUT_CSV} ({len(grid)} rows, {len(grid.columns)} columns)")


def main():
    if RUN_DOWNLOAD:
        print("=== DOWNLOAD ===")
        download_all()
    if RUN_PROCESS:
        print("\n=== PROCESS ===")
        process_all()


if __name__ == "__main__":
    main()