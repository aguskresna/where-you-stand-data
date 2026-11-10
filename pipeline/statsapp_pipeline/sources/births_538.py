"""US births by calendar date, from FiveThirtyEight's data repository (CC BY 4.0).

2000-2014 comes from Social Security Administration counts; 1994-1999 from the CDC/NCHS file, whose
NCHS data-use rules apply. The app shows the average number of births on each calendar date.
"""

from __future__ import annotations

import pandas as pd

SOURCE = "births_538"
REPO = "https://raw.githubusercontent.com/fivethirtyeight/data/master/births/"
PAGE = "https://github.com/fivethirtyeight/data/tree/master/births"
SSA = "US_births_2000-2014_SSA.csv"
CDC = "US_births_1994-2003_CDC_NCHS.csv"
WATCH = [REPO + SSA, REPO + CDC]


def build(ctx) -> None:
    ssa = pd.read_csv(ctx.download_or_manual(REPO + SSA, SSA, PAGE))
    cdc = pd.read_csv(ctx.download_or_manual(REPO + CDC, CDC, PAGE))
    build_from(ctx, ssa, cdc)


def build_from(ctx, ssa: pd.DataFrame, cdc: pd.DataFrame) -> None:
    df = pd.concat([cdc[cdc["year"] < ssa["year"].min()], ssa], ignore_index=True)
    df["key"] = df["month"].astype(int).map("{:02d}".format) + "-" + df["date_of_month"].astype(int).map("{:02d}".format)
    by_date = df.groupby("key")["births"].mean().round().astype(int)
    first, last = int(df["year"].min()), int(df["year"].max())
    ctx.write("us.births.daily", {"years": [first, last], "byDate": by_date.to_dict()}, year=f"{first}-{last}",
              note="Average births on each calendar date; February 29 averages leap years only.")
