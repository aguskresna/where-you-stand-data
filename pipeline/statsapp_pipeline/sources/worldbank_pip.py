"""World Bank Poverty and Inequality Platform percentiles (CC0): 100 income or consumption percentiles per country.

Download the "Percentiles" dataset from the World Bank data catalog (search "PIP percentiles") as CSV and
save it as pipeline/manual/worldbank_pip/pip_percentiles.csv. Values are 2021 PPP dollars per person per day.
Population weights come from the UN WPP indicators, so build un_wpp first.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..common import PipelineError, pick_column

SOURCE = "worldbank_pip"
FILE = "pip_percentiles.csv"
MANUAL = [FILE]
DEPENDS = ["un_wpp"]
HOW = "Download the PIP percentiles CSV from https://datacatalog.worldbank.org (search 'Poverty and Inequality Platform percentiles') and save it there."


def thresholds(rows: pd.DataFrame, pct_col: str, avg_col: str, q_col: str | None) -> list[float]:
    """101 thresholds from 100 percentile groups.

    With a threshold column, q[p] is the top of percentile p; the bottom (q[0]) and a missing top (q[100])
    are extrapolated from the group means. Without one, thresholds sit between neighbouring group means.
    """
    rows = rows.sort_values(pct_col)
    avg = rows[avg_col].to_numpy(dtype=float)
    if len(avg) != 100:
        raise PipelineError(f"Expected 100 percentiles, found {len(avg)}")
    if q_col and rows[q_col].notna().sum() >= 99:
        top = rows[q_col].to_numpy(dtype=float)
        q = np.empty(101)
        q[1:] = top
        q[0] = max(0.0, avg[0] - (top[0] - avg[0]))
        if not np.isfinite(q[100]):
            q[100] = avg[99] + (avg[99] - top[98])
    else:
        mids = (avg[:-1] + avg[1:]) / 2
        q = np.concatenate([[max(0.0, avg[0] - (mids[0] - avg[0]))], mids, [avg[99] + (avg[99] - mids[-1])]])
    q = np.maximum.accumulate(np.nan_to_num(q, nan=0.0))
    return [round(float(x), 3) for x in q]


def build(ctx) -> None:
    df = pd.read_csv(ctx.manual(FILE, HOW))
    wpp_path = ctx.data_dir / ctx.contract["datasets"]["world.wpp.indicators"]["file"]
    if not wpp_path.exists():
        raise PipelineError("Build un_wpp first: PIP needs its population figures")
    with open(wpp_path, encoding="utf-8") as f:
        wpp = json.load(f)["data"]
    build_from(ctx, df, wpp)


def build_from(ctx, df: pd.DataFrame, wpp: dict) -> None:
    code = pick_column(df, ["country_code", "code"], "country code")
    year = pick_column(df, ["year", "reporting_year"], "year")
    pct = pick_column(df, ["percentile"], "percentile")
    avg = pick_column(df, ["avg_welfare", "welfare", "mean"], "average welfare")
    qcol = next((c for c in df.columns if c.lower() in ("quantile", "threshold")), None)
    level = next((c for c in df.columns if c.lower() == "reporting_level"), None)
    welfare = next((c for c in df.columns if c.lower() == "welfare_type"), None)
    if level:
        df = df[df[level].str.lower() == "national"]
    countries = {}
    for iso, rows in df.groupby(code):
        latest_year = rows[year].max()
        rows = rows[rows[year] == latest_year]
        if welfare and rows[welfare].nunique() > 1:
            rows = rows[rows[welfare] == "income"] if (rows[welfare] == "income").any() else rows
        series = wpp["series"].get(iso)
        if not series:
            continue
        i = int(latest_year) - wpp["first"]
        pop = series["pop"][min(max(i, 0), len(series["pop"]) - 1)]
        if not pop:
            continue
        try:
            q = thresholds(rows, pct, avg, qcol)
        except PipelineError as e:
            ctx.log(f"  skipped {iso}: {e}")
            continue
        countries[iso] = {"year": int(latest_year), "welfare": str(rows[welfare].iloc[0]) if welfare else "income", "pop": round(pop * 1000), "q": q}
    if not countries:
        raise PipelineError("No countries matched between PIP and the UN population data")
    ctx.write("world.pip.percentiles", {"unit": "2021 PPP $ per person per day", "countries": countries},
              year=max(c["year"] for c in countries.values()), note="Each country's latest survey year.")
