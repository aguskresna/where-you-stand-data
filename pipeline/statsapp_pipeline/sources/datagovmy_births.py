"""Daily live births in Malaysia (National Registration Department via data.gov.my, CC BY 4.0).

Uses 2000-2022 by default: earlier years show registration artefacts, such as unknown birthdays recorded
as January 1. Save a CSV as pipeline/manual/datagovmy_births/births.csv if the download fails.
"""

from __future__ import annotations

import pandas as pd

from ..common import PipelineError, pick_column

SOURCE = "datagovmy_births"
URLS = ["https://storage.data.gov.my/demography/births.parquet"]
PAGE = "https://data.gov.my/data-catalogue/births"
FIRST, LAST = 2000, 2022
WATCH = URLS
MANUAL = ["births.csv"]


def frame(ctx) -> pd.DataFrame:
    for folder in (ctx.manual_dir, ctx.raw):
        if (folder / "births.csv").exists():
            return pd.read_csv(folder / "births.csv")
        if (folder / "births.parquet").exists():
            return pd.read_parquet(folder / "births.parquet")
    errors = []
    for url in URLS:
        try:
            return pd.read_parquet(ctx.download(url, "births.parquet"))
        except Exception as e:
            errors.append(str(e))
    raise PipelineError(f"Couldn't get the births table ({'; '.join(errors)}). Download the CSV from {PAGE} and save it as {ctx.manual_dir / 'births.csv'}")


def build(ctx) -> None:
    build_from(ctx, frame(ctx))


def build_from(ctx, df: pd.DataFrame) -> None:
    date = pick_column(df, ["date"], "date")
    births = pick_column(df, ["births", "abs", "value"], "births")
    state = next((c for c in df.columns if c.lower() == "state"), None)
    if state:
        df = df[df[state] == "Malaysia"] if (df[state] == "Malaysia").any() else df.groupby(date, as_index=False)[births].sum()
    d = pd.to_datetime(df[date])
    first = int(ctx.options.get("first", FIRST))
    last = int(ctx.options.get("last", LAST))
    keep = d.dt.year.between(first, last)
    df, d = df[keep], d[keep]
    if df.empty:
        raise PipelineError(f"No births between {first} and {last}")
    key = d.dt.strftime("%m-%d")
    by_date = df.groupby(key)[births].mean().round().astype(int)
    ctx.write("my.births.daily", {"years": [first, last], "byDate": by_date.to_dict()}, year=f"{first}-{last}",
              note="Average registered births on each calendar date.")
