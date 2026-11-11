"""FHFA House Price Index (all-transactions, quarterly, not seasonally adjusted): average yearly growth.

For each state, and for the US ('*'), the compound yearly growth between the latest quarter and the
same quarter ten years earlier: (index now / index ten years ago) ** (1/10) - 1.
"""

from __future__ import annotations

import io

import pandas as pd

from ..common import PipelineError

SOURCE = "fhfa_hpi"
BASE = "https://www.fhfa.gov/hpi/download/quarterly_datasets/"
STATE_FILE = "hpi_at_state.csv"
US_FILE = "hpi_at_us_and_census.csv"
PAGE = "https://www.fhfa.gov/data/hpi/datasets?tab=quarterly-data"
WATCH = [BASE + STATE_FILE, BASE + US_FILE]
YEARS = 10
STATES = {"AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD",
          "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
          "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY"}


def read(path) -> pd.DataFrame:
    """The files have no header: place, year, quarter, index."""
    df = pd.read_csv(path, header=None, names=["place", "year", "quarter", "index"], dtype={"place": str})
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["quarter"] = pd.to_numeric(df["quarter"], errors="coerce")
    df["index"] = pd.to_numeric(df["index"], errors="coerce")  # '-' where FHFA publishes no value
    return df.dropna(subset=["year", "quarter"])


def growth(df: pd.DataFrame) -> tuple[tuple[int, int], dict[str, float]]:
    # The latest quarter in the file (year first, then quarter).
    last = df.dropna(subset=["index"]).sort_values(["year", "quarter"]).iloc[-1]
    year, quarter = int(last["year"]), int(last["quarter"])
    now = df[(df["year"] == year) & (df["quarter"] == quarter)].set_index("place")["index"]
    then = df[(df["year"] == year - YEARS) & (df["quarter"] == quarter)].set_index("place")["index"]
    out = {}
    for place, v in now.items():
        v0 = then.get(place)
        if pd.notna(v) and v0 is not None and pd.notna(v0) and v0 > 0:
            out[place] = round((float(v) / float(v0)) ** (1 / YEARS) - 1, 4)
    return (year, quarter), out


def build_from(ctx, states: pd.DataFrame, us: pd.DataFrame) -> None:
    (year, quarter), by_state = growth(states)
    (uy, uq), by_us = growth(us)
    if (uy, uq) != (year, quarter):
        raise PipelineError(f"The state file ends in {year} Q{quarter} but the US file in {uy} Q{uq}")
    out = {st: g for st, g in by_state.items() if st in STATES}
    if len(out) != len(STATES) or "USA" not in by_us:
        raise PipelineError(f"Expected growth for 50 states, DC and the USA; got {len(out)} states and {'the' if 'USA' in by_us else 'no'} USA")
    out["*"] = by_us["USA"]
    ctx.write("us.fhfa.hpi", {"states": dict(sorted(out.items()))}, year=year,
              note=f"Average yearly change of the all-transactions index, {year - YEARS} Q{quarter} to {year} Q{quarter}.")


def fetch(ctx, name: str):
    path = ctx.manual_dir / name
    if path.exists():
        return path
    try:
        return ctx.download(BASE + name, name, refresh=not ctx.offline)
    except PipelineError as e:
        raise PipelineError(f"{e}. Download {name} from {PAGE} and save it as {path.as_posix()}") from e


def build(ctx) -> None:
    build_from(ctx, read(fetch(ctx, STATE_FILE)), read(fetch(ctx, US_FILE)))
