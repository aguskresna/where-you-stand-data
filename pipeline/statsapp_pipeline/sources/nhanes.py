"""NHANES August 2021 - August 2023 (CDC/NCHS): measured height, weight, waist and BMI of adults.

NCHS data-use rules apply: statistical reporting and analysis only, and no attempt to identify anyone.
Uses the exam (MEC) weights. Ages 80 and over are top-coded at 80 in the public files.
"""

from __future__ import annotations

import pandas as pd

from ..common import AGE_BANDS, band_of, by_groups, weighted_quantiles, weighted_share

SOURCE = "nchs_nhanes"
BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/"
PAGE = "https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?Cycle=2021-2023"
WATCH = [BASE + "DEMO_L.xpt", BASE + "BMX_L.xpt"]  # a new cycle has new file names: update BASE and the suffix

MEASURES = [("BMXHT", "height_cm", "cm"), ("BMXWT", "weight_kg", "kg"), ("BMXWAIST", "waist_cm", "cm"), ("BMXBMI", "bmi", "kg/m²")]


def read_xpt(path) -> pd.DataFrame:
    return pd.read_sas(path, format="xport", encoding="latin-1")


def build(ctx) -> None:
    demo = read_xpt(ctx.download_or_manual(BASE + "DEMO_L.xpt", "DEMO_L.xpt", PAGE))
    exam = read_xpt(ctx.download_or_manual(BASE + "BMX_L.xpt", "BMX_L.xpt", PAGE))
    build_from(ctx, demo, exam)


def build_from(ctx, demo: pd.DataFrame, exam: pd.DataFrame) -> None:
    d = demo[["SEQN", "RIAGENDR", "RIDAGEYR", "WTMEC2YR"]].merge(exam, on="SEQN")
    d = d[(d["RIDAGEYR"] >= 18) & (d["WTMEC2YR"] > 0)].copy()
    d["sex"] = d["RIAGENDR"].map({1: "M", 2: "F"})
    d["band"] = band_of(d["RIDAGEYR"], AGE_BANDS)
    d["w"] = d["WTMEC2YR"]
    dims = {"sex": ["M", "F"], "band": AGE_BANDS}
    measures = {}
    for col, key, unit in MEASURES:
        rows = d[d[col].notna()]
        measures[key] = {"unit": unit, "groups": by_groups(rows, dims, lambda r, c=col: weighted_quantiles(r[c], r["w"], digits=1), ctx.min_records)}
    with_bmi = d[d["BMXBMI"].notna()]
    obese = by_groups(with_bmi, dims, lambda r: round(weighted_share(r["BMXBMI"] >= 30, r["w"]), 4), ctx.min_records)
    ctx.write("us.nhanes.body", {"measures": measures, "shares": {"obese": {"groups": obese}}}, year="2021-2023",
              note="Measured by NHANES examiners; adults 18 and over, exam weights.")
