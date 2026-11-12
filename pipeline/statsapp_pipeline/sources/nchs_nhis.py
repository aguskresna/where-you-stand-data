"""National Health Interview Survey (CDC/NCHS), Sample Adult file: sexual orientation and smoking.

NCHS data-use rules apply: statistical reporting and analysis only, and no attempt to identify anyone.
Weighted with the final annual adult weight WTFA_A; groups are sex by age band, published only when
both denominators have at least MIN_RECORDS adults.

  straight, gay, bisexual   ORIENT_A 2, 1, 3 among adults who answered 1-5 (gay/lesbian, straight,
                            bisexual, something else, don't know). Refused and not ascertained are
                            left out, so the three shares plus 'something else' and 'don't know' make 1.
  nonsmoker                 SMKCIGST_A 3 (former) or 4 (never) among adults with a known status (1-4):
                            not currently smoking cigarettes. E-cigarettes aren't counted.
"""

from __future__ import annotations

import zipfile

import pandas as pd

from ..common import AGE_BANDS, PipelineError, band_of, by_groups, round_to, weighted_share

SOURCE = "nchs_nhis"
BASE = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/NHIS/"
PAGE = "https://www.cdc.gov/nchs/nhis/documentation/index.html"
FIRST_YEAR = 2025  # the newest file when this was written; later years are found by checking BASE
COLUMNS = ["SEX_A", "AGEP_A", "ORIENT_A", "SMKCIGST_A", "WTFA_A"]


def url(year: int) -> str:
    return f"{BASE}{year}/adult{year % 100:02d}csv.zip"


def latest_year(ctx) -> int:
    year = FIRST_YEAR
    while ctx.exists(url(year + 1)):
        year += 1
    return year


def watch(ctx) -> list[str]:
    year = latest_year(ctx)
    return [url(year), url(year + 1)]  # next year's file appearing changes the fingerprint


def build(ctx) -> None:
    year = latest_year(ctx)
    path = ctx.download_or_manual(url(year), f"adult{year % 100:02d}csv.zip", PAGE)
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
        if not name:
            raise PipelineError(f"No CSV inside {path.name}")
        with z.open(name) as f:
            df = pd.read_csv(f, usecols=lambda c: c.upper() in COLUMNS)
    df.columns = [c.upper() for c in df.columns]
    build_from(ctx, df, year)


def build_from(ctx, df: pd.DataFrame, year: int) -> None:
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise PipelineError(f"The NHIS adult file has no {missing}")
    d = df[(df["WTFA_A"] > 0) & df["SEX_A"].isin([1, 2]) & (df["AGEP_A"] >= 18) & (df["AGEP_A"] <= 85)].copy()
    d["sex"] = d["SEX_A"].map({1: "M", 2: "F"})
    d["band"] = band_of(d["AGEP_A"], AGE_BANDS)  # 85 is '85 and over', inside 65+
    d["w"] = d["WTFA_A"]
    d["orient_ok"] = d["ORIENT_A"].isin([1, 2, 3, 4, 5])
    d["smoke_ok"] = d["SMKCIGST_A"].isin([1, 2, 3, 4])

    def shares(rows):
        o = rows[rows["orient_ok"]]
        s = rows[rows["smoke_ok"]]
        if len(o) < ctx.min_records or len(s) < ctx.min_records:
            return None
        share = lambda frame, mask: round_to(weighted_share(mask, frame["w"]), 4)
        return {
            "straight": share(o, o["ORIENT_A"] == 2),
            "gay": share(o, o["ORIENT_A"] == 1),
            "bisexual": share(o, o["ORIENT_A"] == 3),
            "nonsmoker": share(s, s["SMKCIGST_A"].isin([3, 4])),
        }

    groups = by_groups(d, {"sex": ["M", "F"], "band": AGE_BANDS}, shares, ctx.min_records)
    groups = {k: v for k, v in groups.items() if v is not None}
    ctx.write("us.nhis.traits", {"groups": groups}, year=year,
              note="Adults 18 and over. Orientation shares leave out refused and not-ascertained answers; "
                   "'something else' and 'don't know' make up the rest. Non-smokers don't currently smoke cigarettes.")
