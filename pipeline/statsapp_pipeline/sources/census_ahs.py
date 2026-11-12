"""American Housing Survey (Census Bureau and HUD), national public use file: home floor area.

The public use file gives floor area only in nine size classes (UNITSIZE 1-9); the exact square
footage is on the internal file alone. So this publishes the weighted share of occupied homes in each
class, not 101 percentiles: thresholds inside a class would have to be invented. The class shares
match the PUF estimates Census lists in its 'Table Specifications and PUF Estimates for User
Verification' workbook.

Occupied homes (INTSTATUS 1), weighted with WEIGHT. Owners are TENURE 1; renters TENURE 2 (rented)
and 3 (occupied without paying rent), as in Census's renter-occupied tables. Homes whose size wasn't
reported (UNITSIZE -9) are left out of the shares.
"""

from __future__ import annotations

import re
import zipfile

import pandas as pd

from ..common import PipelineError, round_to

SOURCE = "census_ahs"
BASE = "https://www2.census.gov/programs-surveys/ahs/"
PAGE = "https://www.census.gov/programs-surveys/ahs/data.html"
FIRST_YEAR = 2023  # the newest national file when this was written; the survey runs in odd years
EDGES = [500, 750, 1000, 1500, 2000, 2500, 3000, 4000]  # UNITSIZE 1 is under 500, 9 is 4,000 or more
COLUMNS = ["UNITSIZE", "TENURE", "WEIGHT", "INTSTATUS"]


def folder(year: int) -> str:
    return f"{BASE}{year}/"


def latest_year(ctx) -> int:
    year = FIRST_YEAR
    while ctx.head(folder(year + 2)).startswith("200"):
        year += 2
    return year


def watch(ctx) -> list[str]:
    year = latest_year(ctx)
    return [folder(year), folder(year + 2)]  # the folder listing grows when a new file version lands


def puf_name(listing: str, year: int) -> str:
    """The newest 'AHS <year> National PUF v<x.y> CSV.zip' in a folder listing (not the flat or SAS files)."""
    found = re.findall(rf"AHS(?:%20| ){year}(?:%20| )National(?:%20| )PUF(?:%20| )v(\d+)\.(\d+)(?:%20| )CSV\.zip", listing)
    if not found:
        raise PipelineError(f"No national PUF CSV for {year} in {folder(year)}")
    major, minor = max((int(a), int(b)) for a, b in found)
    return f"AHS%20{year}%20National%20PUF%20v{major}.{minor}%20CSV.zip"


def build(ctx) -> None:
    year = latest_year(ctx)
    listing = ctx.download(folder(year), f"ahs{year}_folder.html", refresh=not ctx.offline).read_text(encoding="utf-8", errors="replace")
    name = puf_name(listing, year)
    path = ctx.download_or_manual(folder(year) + name, name.replace("%20", " "), PAGE)
    with zipfile.ZipFile(path) as z:
        inner = next((n for n in z.namelist() if n.lower().endswith("household.csv")), None)
        if not inner:
            raise PipelineError(f"No household.csv inside {path.name}")
        with z.open(inner) as f:
            df = pd.read_csv(f, usecols=COLUMNS, dtype=str)
    build_from(ctx, df, year)


def build_from(ctx, df: pd.DataFrame, year: int) -> None:
    d = df[COLUMNS].copy()
    for c in ("UNITSIZE", "TENURE", "INTSTATUS"):
        d[c] = d[c].astype(str).str.strip().str.strip("'")
    d["w"] = pd.to_numeric(df["WEIGHT"], errors="coerce")
    d = d[(d["INTSTATUS"] == "1") & (d["w"] > 0)]
    d = d[d["UNITSIZE"].isin([str(i) for i in range(1, 10)])]
    d["cls"] = d["UNITSIZE"].astype(int)
    groups = {}
    for key, rows in (("all", d), ("owner", d[d["TENURE"] == "1"]), ("renter", d[d["TENURE"].isin(["2", "3"])])):
        if len(rows) < ctx.min_records:
            continue
        by_cls = rows.groupby("cls")["w"].sum().reindex(range(1, 10), fill_value=0.0)
        shares = (by_cls / by_cls.sum()).tolist()
        lows = [0, *EDGES]
        highs = [*EDGES, None]
        groups[key] = [[lo, hi, round_to(v, 4)] for lo, hi, v in zip(lows, highs, shares)]
    if "all" not in groups:
        raise PipelineError("Too few AHS records with a reported unit size")
    ctx.write("us.ahs.size", {"unit": "sq ft", "groups": groups}, year=year,
              note="Occupied homes. The public file gives size classes only, so this is the share of homes in each class; "
                   "homes whose size wasn't reported are left out.")
