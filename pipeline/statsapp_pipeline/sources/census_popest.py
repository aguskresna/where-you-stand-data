"""Census Bureau Population Estimates: US resident population by single year of age and sex (public domain).

The national characteristics file for vintage V is
  https://www2.census.gov/programs-surveys/popest/datasets/<decade start>-<V>/national/asrh/nc-est<V>-agesex-res.csv
with columns SEX (0 both, 1 male, 2 female), AGE (0..99, 100 = 100 and over, 999 = all ages) and
POPESTIMATE<year> for each July 1 from the decade's base to V. We keep the newest year of the newest
vintage. A new vintage comes out each June (sometimes later); the job watches for next year's file.
"""

from __future__ import annotations

import pandas as pd

from ..common import PipelineError

SOURCE = "census_popest"
BASE = "https://www2.census.gov/programs-surveys/popest/datasets"
SEXES = {"total": 0, "M": 1, "F": 2}


def url_for(vintage: int) -> str:
    start = (vintage - 1) // 10 * 10  # vintage 2030 still sits in 2020-2030, as 2020 sat in 2010-2020
    return f"{BASE}/{start}-{vintage}/national/asrh/nc-est{vintage}-agesex-res.csv"


def latest_vintage(ctx) -> int:
    for v in range(ctx.today.year, ctx.today.year - 4, -1):
        if ctx.exists(url_for(v)):
            return v
    raise PipelineError(f"No national age-sex file found for vintages {ctx.today.year - 3}-{ctx.today.year} under {BASE}")


def watch(ctx) -> list[str]:
    v = latest_vintage(ctx)
    return [url_for(v), url_for(v + 1)]  # the second answers 404 until the next vintage appears


def build(ctx) -> None:
    v = latest_vintage(ctx)
    path = ctx.download(url_for(v))
    build_from(ctx, pd.read_csv(path), vintage=v)


def build_from(ctx, df: pd.DataFrame, vintage: int) -> None:
    cols = [c for c in df.columns if str(c).upper().startswith("POPESTIMATE") and str(c)[11:].isdigit()]
    if not cols or not {"SEX", "AGE"} <= set(df.columns):
        raise PipelineError(f"Expected SEX, AGE and POPESTIMATE<year> columns; found {list(df.columns)}")
    col = max(cols, key=lambda c: int(str(c)[11:]))
    year = int(str(col)[11:])
    out = {}
    for key, code in SEXES.items():
        rows = df[df["SEX"] == code].set_index("AGE")[col]
        missing = [a for a in range(101) if a not in rows.index]
        if missing:
            raise PipelineError(f"SEX={code}: ages {missing[:5]} missing")
        values = [int(rows[a]) for a in range(101)]
        if 999 in rows.index and sum(values) != int(rows[999]):
            raise PipelineError(f"SEX={code}: ages 0-100 add up to {sum(values)}, not the all-ages total {int(rows[999])}")
        out[key] = values
    if [m + f for m, f in zip(out["M"], out["F"])] != out["total"]:
        raise PipelineError("Male and female counts don't add up to the total")
    ctx.write("us.census.pop_age", out, year=year,
              note=f"Resident population on July 1, {year} (Vintage {vintage} estimates). The last age is 100 and over.")
