"""
analysis_utils.py

Small shared helpers for the downstream analysis scripts
(visualize_dataframe.py, correlation_analysis.py). Kept separate so both
scripts stay flexible about WHICH dataframe they're pointed at, without
duplicating the same "find the file / find the key columns" logic twice.

Nothing here is specific to one dataframe's column names -- it works the
same way dataframe_building.py's own _resolve_column() does: try a short
list of common candidate names, fall back to an explicit CLI override,
and fail loudly (never silently guess wrong) if neither works.
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATAFRAMES_DIR = PROJECT_ROOT / "data" / "dataframes"
PLOTS_DIR = PROJECT_ROOT / "plots"

# Candidate column names tried, in order, when --time-col / --group-col
# isn't passed explicitly. Covers every dataframe this project currently
# produces (dataframe_building.py's own "datetime_utc"/"bidding_zone",
# plus the raw pipeline outputs' own column names, in case someone points
# these scripts at a pre-merge file instead of a built dataframe).
TIME_COL_CANDIDATES = ["datetime_utc", "datetime", "time_utc", "DeliveryStartUTC", "HourUTC", "timestamp"]
GROUP_COL_CANDIDATES = ["bidding_zone", "Area", "area"]

# Columns that are category identifiers, not measurements (e.g. fe_hour,
# fe_week_of_sample — fixed-effect ids expanded to dummies in the model).
# Kept in the data, but never plotted or correlated as if they were numbers.
IDENTIFIER_PREFIXES = ("fe_",)


def resolve_input_path(arg: str) -> Path:
    """Accept a bare ANALYSES name ("df_2025"), a bare filename, or a
    full path. A bare name/filename is resolved against
    data/dataframes/ -- the folder dataframe_building.py always saves
    into -- so "df_2025" and "full_2022_2025" both just work without
    typing the full path."""
    p = Path(arg)
    if p.exists():
        return p
    candidate = DATAFRAMES_DIR / (arg if arg.endswith(".csv") else f"{arg}.csv")
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        f"Could not find '{arg}' as a path, nor as {candidate}. "
        f"Pass a full path, or an ANALYSES name that's already been built."
    )


def detect_column(df: pd.DataFrame, override: str | None, candidates: list, role: str) -> str:
    """Resolve the {role} column: use `override` if given (erroring
    loudly if it doesn't exist), else the first candidate name found in
    df.columns, else raise -- never silently guesses."""
    if override:
        if override not in df.columns:
            raise KeyError(f"--{role}-col '{override}' not found. Columns: {list(df.columns)}")
        return override
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(
        f"Could not auto-detect a {role} column. Tried {candidates}. "
        f"Pass --{role}-col explicitly. Columns: {list(df.columns)}"
    )


def load_dataframe(input_arg: str, time_col_override: str | None = None,
                    group_col_override: str | None = None):
    """Shared entry point for both analysis scripts: resolve the input
    file, load it, detect/parse the time and group columns, and return
    (df, time_col, group_col, feature_cols) where feature_cols is every
    remaining NUMERIC column -- i.e. everything the script should
    actually plot/correlate. Non-numeric leftover columns are reported,
    not silently dropped without explanation."""
    in_path = resolve_input_path(input_arg)
    print(f"Loading {in_path} ...")
    df = pd.read_csv(in_path)

    time_col = detect_column(df, time_col_override, TIME_COL_CANDIDATES, "time")
    group_col = detect_column(df, group_col_override, GROUP_COL_CANDIDATES, "group")
    df[time_col] = pd.to_datetime(df[time_col], utc=True)

    identifiers = [c for c in df.columns if c.startswith(IDENTIFIER_PREFIXES)]
    feature_cols = [c for c in df.columns if c not in (time_col, group_col) and c not in identifiers
                     and pd.api.types.is_numeric_dtype(df[c])]
    skipped = [c for c in df.columns
               if c not in (time_col, group_col) and c not in feature_cols and c not in identifiers]
    if skipped:
        print(f"Not numeric -- skipped: {skipped}")
    if identifiers:
        print(f"Category identifiers (fixed-effect ids, not measurements) -- not plotted/correlated: "
              f"{identifiers}")

    print(f"{in_path.name}: {len(df)} rows, {len(feature_cols)} numeric feature(s), "
          f"groups: {sorted(df[group_col].astype(str).unique())}, "
          f"range: {df[time_col].min()} to {df[time_col].max()}")

    return df, time_col, group_col, feature_cols, in_path.stem


def drop_constant_columns(df: pd.DataFrame, cols: list, label: str = "") -> list:
    """Return `cols` minus any column that's constant (or entirely NaN)
    within this dataframe -- e.g. the structural-zero da_flow_* columns
    for one bidding zone (see dataframe_building.py's
    report_zero_variance_by_area()). A constant column has an undefined
    correlation (division by zero std) and can't be plotted as a
    distribution either, so both downstream scripts drop these the same
    way and say what they dropped."""
    kept, dropped = [], []
    for c in cols:
        vals = df[c].dropna()
        if len(vals) == 0 or vals.nunique() <= 1:
            dropped.append(c)
        else:
            kept.append(c)
    if dropped:
        tag = f" ({label})" if label else ""
        print(f"  dropping {len(dropped)} constant/all-NaN column(s){tag}: {dropped}")
    return kept