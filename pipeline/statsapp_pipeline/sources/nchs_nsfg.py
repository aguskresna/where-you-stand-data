"""National Survey of Family Growth (CDC/NCHS): how many first marriages are still intact after 10 and 20 years.

NCHS data-use rules apply: statistical reporting and analysis only, and no attempt to identify anyone.

Method, as in NCHS's National Health Statistics Report No. 49 ("First Marriages in the United States",
2012, tables 5-6): a weighted Kaplan-Meier estimate of the time from first marriage to its disruption by
separation or divorce. MARDIS01 is the date the couple stopped living together when that came before
the divorce. A first marriage that ended in widowhood is censored at the death; an intact one at the
interview. Women's and men's respondent files are pooled, each with its own final weight.

The public files since 2017 give the years of marriage and dissolution, not the months, so durations
are year differences: a marriage counts as disrupted within k years when its dissolution year is at
most k years after its wedding year; censored marriages are at risk through their year difference
(disruptions first on ties). On the 2006-2010 files, which still had months, this year-level estimate
stays within 1.7 percentage points of the month-level one, which reproduces NHSR 49 exactly.

Respondents are 15-49, so a 20-year figure needs people who married young enough: a figure is published
only when at least MIN_RECORDS first marriages were still under observation at that duration, otherwise
it is null (for those who married at 30 or later, y20 is always null). Education is the respondent's at
interview, used only for respondents aged 22 and over, as in NHSR 49.
"""

from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd

from ..common import PipelineError, by_groups, round_to

SOURCE = "nchs_nsfg"
FILES = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/NSFG/"
PAGE = "https://www.cdc.gov/nchs/nsfg/nsfg-2022-2023-puf.htm"
CYCLE = "2022-2023"  # a new cycle has new file names and weight: update CYCLE and WEIGHT
WEIGHT = "WGT2022_2023"
RESP_FILES = {"F": f"NSFG-{CYCLE}-FemRespPUFData.zip", "M": f"NSFG-{CYCLE}-MaleRespPUFData.zip"}
WATCH = [FILES + n for n in RESP_FILES.values()]
COLUMNS = ["AGE_R", "FMARNO", "MARDAT01", "MARDIS01", "MAREND01", "FMAR1AGE", "HIEDUC", "CMINTVW", WEIGHT]

AGE_GROUPS = ["<20", "20-24", "25-29", "30+"]
EDU_GROUPS = ["0", "1", "2", "3", "4"]  # the app's EDU list: less than high school .. graduate degree
# HIEDUC (public-use codes): 1-2 no diploma, 3 GED, 4 high school graduate, 5 some college, 6-7 associate,
# 8 bachelor's, 9-11 master's, professional, doctorate.
EDU_OF_HIEDUC = {1: "0", 2: "0", 3: "1", 4: "1", 5: "2", 6: "2", 7: "2", 8: "3", 9: "4", 10: "4", 11: "4"}


def build(ctx) -> None:
    frames = []
    for sex, name in RESP_FILES.items():
        path = ctx.download_or_manual(FILES + name, name, PAGE)
        with zipfile.ZipFile(path) as z:
            inner = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
            if not inner:
                raise PipelineError(f"No CSV inside {path.name}")
            with z.open(inner) as f:
                frames.append(pd.read_csv(f, usecols=lambda c: c in COLUMNS, low_memory=False).assign(sex=sex))
    build_from(ctx, pd.concat(frames, ignore_index=True), CYCLE)


def first_marriages(df: pd.DataFrame) -> pd.DataFrame:
    """One row per ever-married respondent: duration in years (t), disrupted (e), weight, groups."""
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise PipelineError(f"The NSFG respondent files have no {missing}")
    d = df[(df["FMARNO"] >= 1) & (df[WEIGHT] > 0)].copy()
    ended = d["MAREND01"].isin([1, 2, 3])
    # 9997 and similar codes mean the year isn't known; those few marriages are left out.
    ok = d["MARDAT01"].between(1900, 2100) & (~ended | d["MARDIS01"].between(1900, 2100)) & d["FMAR1AGE"].between(10, 49)
    d = d[ok]
    ended = d["MAREND01"].isin([1, 2, 3])
    interview_year = 1900 + (d["CMINTVW"] - 1) // 12
    end_year = np.where(ended, d["MARDIS01"], interview_year)
    out = pd.DataFrame({
        "t": (end_year - d["MARDAT01"]).astype(float),
        "e": d["MAREND01"].isin([1, 2]).astype(int),  # separation or divorce; widowhood is censored
        "w": d[WEIGHT].astype(float),
    }, index=d.index)
    if (out["t"] < 0).any():
        raise PipelineError("An NSFG first marriage ends before it starts; check the year variables")
    age = d["FMAR1AGE"]
    out["age"] = np.select([age < 20, age < 25, age < 30], ["<20", "20-24", "25-29"], "30+")
    out["edu"] = np.where(d["AGE_R"] >= 22, d["HIEDUC"].map(EDU_OF_HIEDUC).fillna(""), "")
    return out


def survival(t, e, w, years: list[int]) -> dict[int, tuple[float, int]]:
    """Weighted Kaplan-Meier: share still intact after k years, and how many were still observed at k."""
    t, e, w = np.asarray(t, float), np.asarray(e, int), np.asarray(w, float)
    out = {}
    for k in years:
        s = 1.0
        for u in np.unique(t[(e == 1) & (t <= k)]):
            at_risk = w[t >= u].sum()
            events = w[(t == u) & (e == 1)].sum()
            if at_risk > 0:
                s *= 1 - events / at_risk
        out[k] = (s, int((t >= k).sum()))
    return out


def build_from(ctx, df: pd.DataFrame, cycle: str) -> None:
    d = first_marriages(df)

    def figures(rows):
        s = survival(rows["t"], rows["e"], rows["w"], [10, 20])
        return {f"y{k}": round_to(v, 3) if n >= ctx.min_records else None for k, (v, n) in s.items()}

    groups = by_groups(d, {"age": AGE_GROUPS, "edu": EDU_GROUPS}, figures, ctx.min_records)
    groups = {k: v for k, v in groups.items() if v["y10"] is not None}
    if "*|*" not in groups:
        raise PipelineError("Too few NSFG first marriages")
    ctx.write("us.nsfg.marriage", {"groups": groups}, year=cycle,
              note="First marriages of women and men aged 15-49 at interview, still intact (no separation or divorce). "
                   "y20 is null where too few marriages could be followed for 20 years.")
