"""BLS Occupational Employment and Wage Statistics: annual wage percentiles by detailed occupation.

Kept: the 10th, 25th, 50th, 75th and 90th percentile annual wages of every detailed occupation, for
the US, each state, DC and the territories (cross-industry, all ownerships). Wages BLS doesn't
publish ('*') or only gives as a top code ('#', at or above the highest wage it reports) leave that
occupation-area pair out: no number is published for it, so none is stored.

www.bls.gov refuses the pipeline's requests (HTTP 403, "Access Denied"), so the all-data file is
saved by hand (see HOW). The file name changes with every May release: update FILE (and MANUAL).
"""

from __future__ import annotations

import re
import zipfile

import pandas as pd

from ..common import PipelineError

SOURCE = "bls_oews"
YEAR = 2025  # May 2025 estimates, released spring 2026
FILE = f"oesm{YEAR % 100:02d}all.zip"
MANUAL = [FILE]
PAGE = "https://www.bls.gov/oes/tables.htm"
HOW = (f"Open {PAGE} in a browser, download 'All data' for May {YEAR} (XLSX in a zip, {FILE}) "
       f"and save it unchanged as pipeline/manual/bls_oews/{FILE}.")
P = [10, 25, 50, 75, 90]
WAGES = ["A_PCT10", "A_PCT25", "A_MEDIAN", "A_PCT75", "A_PCT90"]
COLUMNS = ["AREA_TYPE", "PRIM_STATE", "AREA_TITLE", "I_GROUP", "OWN_CODE", "OCC_CODE", "OCC_TITLE", "O_GROUP", *WAGES]
AREA_TYPES = {"1", "2", "3"}  # the US, states (and DC), territories


def read_zip(path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if re.search(r"all_data.*\.xlsx$", n, re.I)]
        if not names:
            raise PipelineError(f"No all_data_*.xlsx in {path}: {z.namelist()}")
        with z.open(names[0]) as f:
            return pd.read_excel(f, dtype=str, usecols=lambda c: str(c).strip().upper() in COLUMNS)


def build_from(ctx, df: pd.DataFrame, year: int) -> dict:
    """Writes the dataset; returns counts of what was kept and left out (for the log and the tests)."""
    df = df.rename(columns=lambda c: str(c).strip().upper())
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise PipelineError(f"The OEWS file has no {missing} column(s)")
    df = df.apply(lambda s: s.str.strip())
    keep = (df["AREA_TYPE"].isin(AREA_TYPES) & (df["I_GROUP"].str.lower() == "cross-industry")
            & (df["OWN_CODE"] == "1235") & (df["O_GROUP"].str.lower() == "detailed"))
    df = df[keep]
    if df.empty:
        raise PipelineError("No cross-industry detailed-occupation rows for the US or states in the OEWS file")
    wages = df[WAGES].apply(pd.to_numeric, errors="coerce")  # '*' and '#' become NaN
    complete = wages.notna().all(axis=1)
    occupations, areas, groups = {}, {}, {}
    for (_, row), ok, values in zip(df.iterrows(), complete, wages.itertuples(index=False)):
        area = "US" if row["AREA_TYPE"] == "1" else row["PRIM_STATE"]
        if not re.fullmatch(r"[A-Z]{2}", area or ""):
            continue
        areas[area] = "United States" if area == "US" else row["AREA_TITLE"]
        if not ok:
            continue
        occupations[row["OCC_CODE"]] = row["OCC_TITLE"]
        groups[f"{row['OCC_CODE']}|{area}"] = [int(round(v)) for v in values]
    if "US" not in areas:
        raise PipelineError("The OEWS file has no national (AREA_TYPE 1) rows")
    ctx.write("us.bls.oews", {"p": P, "occupations": dict(sorted(occupations.items())), "areas": dict(sorted(areas.items())),
                              "groups": dict(sorted(groups.items()))}, year=year,
              note=f"OEWS May {year}, cross-industry. Occupations whose wages BLS doesn't publish or top-codes are left out for that area.")
    return {"kept": len(groups), "left_out": int((~complete).sum())}


def build(ctx) -> None:
    counts = build_from(ctx, read_zip(ctx.manual(FILE, HOW)), YEAR)
    ctx.log(f"  {counts['kept']} occupation-area wage sets kept, {counts['left_out']} left out (unpublished or top-coded wages)")
