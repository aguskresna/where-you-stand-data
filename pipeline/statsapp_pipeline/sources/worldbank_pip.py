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


P = list(range(1, 100))  # positions of the published cut points: the tops of percentiles 1..99


def thresholds(rows: pd.DataFrame, pct_col: str, avg_col: str, q_col: str | None) -> tuple[list[float], list[float]]:
    """The 99 cut points between percentiles (the 'quantile' column: top of percentiles 1..99) and the
    100 percentile means.

    PIP leaves the top of the 100th percentile blank and has no bottom for the 1st, so those ends are
    not published; nothing is extrapolated.
    """
    rows = rows.sort_values(pct_col)
    avg = rows[avg_col].to_numpy(dtype=float)
    if len(avg) != 100 or not np.isfinite(avg).all():
        raise PipelineError(f"Expected 100 percentile means, found {np.isfinite(avg).sum()}")
    if not q_col:
        raise PipelineError("The PIP file has no 'quantile' (threshold) column")
    top = rows[q_col].to_numpy(dtype=float)[:99]
    if not np.isfinite(top).all():
        raise PipelineError("Missing cut points for percentiles 1..99")
    q = np.maximum.accumulate(top)
    return [round(float(x), 3) for x in q], [round(float(x), 3) for x in avg]


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
            q, means = thresholds(rows, pct, avg, qcol)
        except PipelineError as e:
            ctx.log(f"  skipped {iso}: {e}")
            continue
        countries[iso] = {"year": int(latest_year), "welfare": str(rows[welfare].iloc[0]) if welfare else "income", "pop": round(pop * 1000), "q": q, "m": means}
    if not countries:
        raise PipelineError("No countries matched between PIP and the UN population data")
    ctx.write("world.pip.percentiles", {"unit": "2021 PPP $ per person per day", "p": P, "countries": countries},
              year=max(c["year"] for c in countries.values()), note="Each country's latest survey year. q: cut points at percentiles 1..99; m: the mean of each of the 100 percentiles.")
