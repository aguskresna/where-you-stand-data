"""American Time Use Survey (Bureau of Labor Statistics): sleep percentiles and average hours a day.

bls.gov refuses scripted downloads (HTTP 403), so this reads the ATUS Activity summary file saved by
hand: from https://www.bls.gov/tus/data.htm save the latest single-year "ATUS Activity summary file"
zip (atussum-<year>.zip) as pipeline/manual/bls_atus/atussum.zip. A multi-year file works too; only
its latest year (TUYEAR) is used.

One diary day per respondent (4 a.m. to 4 a.m.), weighted with the final weight TUFNWGTP so that
weekdays and weekend days count in their true proportions. Activity codes as BLS defines them in the
ATUS lexicon (columns tXXYYZZ are minutes on the diary day):
  sleep    0101xx  sleeping (including naps and sleeplessness)
  work     0501xx  working at a main or other job (no travel)
  screens  120303, 120304 watching TV; 120307 playing games; 120308 computer use for leisure
  travel   18xxxx  all travel, whatever the purpose
Averages are over everyone 15 and over, as in BLS's news release table 1 (where travel is folded
into each activity instead). Sleep percentiles are for adults by age band; a single diary day
varies more than a person's usual sleep.
"""

from __future__ import annotations

import zipfile

import pandas as pd

from ..common import AGE_BANDS, PipelineError, band_of, by_groups, round_to, weighted_quantiles

SOURCE = "bls_atus"
PAGE = "https://www.bls.gov/tus/data.htm"
MANUAL = ["atussum.zip"]
HOW = (f"bls.gov refuses scripted downloads. Open {PAGE}, download the latest single-year ATUS Activity summary file "
       "(atussum-<year>.zip) and save it as pipeline/manual/bls_atus/atussum.zip.")

SCREEN_CODES = ["t120303", "t120304", "t120307", "t120308"]


def build(ctx) -> None:
    path = ctx.manual("atussum.zip", HOW)
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist() if n.lower().endswith((".dat", ".csv")) and "atussum" in n.lower()), None)
        if not name:
            raise PipelineError(f"No atussum .dat/.csv inside {path.name}")
        with z.open(name) as f:
            df = pd.read_csv(f)
    build_from(ctx, df)


def build_from(ctx, df: pd.DataFrame) -> None:
    df = df.rename(columns={c: c.lower() if c.lower().startswith("t") and c[1:].isdigit() else c.upper() for c in df.columns})
    weight = "TUFNWGTP"
    for c in (weight, "TEAGE"):
        if c not in df.columns:
            raise PipelineError(f"The ATUS activity summary file has no {c} column")
    if "TUYEAR" in df.columns:
        year = int(df["TUYEAR"].max())
        df = df[df["TUYEAR"] == year]
    else:
        raise PipelineError("The ATUS activity summary file has no TUYEAR column")
    codes = [c for c in df.columns if c.startswith("t") and c[1:].isdigit() and len(c) == 7]
    if not codes:
        raise PipelineError("No activity columns (tXXYYZZ) in the ATUS activity summary file")

    def minutes(prefixes):
        cols = [c for c in codes if c[1:].startswith(prefixes)]
        return df[cols].sum(axis=1) if cols else pd.Series(0.0, index=df.index)

    d = pd.DataFrame({
        "age": df["TEAGE"],
        "w": df[weight],
        "sleep": minutes(("0101",)) / 60,
        "work": minutes(("0501",)) / 60,
        "screens": df[[c for c in SCREEN_CODES if c in df.columns]].sum(axis=1) / 60,
        "travel": minutes(("18",)) / 60,
    })
    d = d[d["w"] > 0]
    if len(d) < ctx.min_records:
        raise PipelineError("Too few ATUS respondents")

    def avg(col):
        return round_to((d[col] * d["w"]).sum() / d["w"].sum(), 2)

    adults = d[d["age"] >= 18].copy()
    adults["band"] = band_of(adults["age"], AGE_BANDS)
    sleep = by_groups(adults, {"band": AGE_BANDS}, lambda r: weighted_quantiles(r["sleep"], r["w"], digits=2), ctx.min_records)
    data = {"sleep": {"groups": sleep}, "averages": {k: avg(k) for k in ("sleep", "work", "screens", "travel")}}
    ctx.write("us.bls.atus", data, year=year,
              note="Hours on one diary day. Averages are for everyone 15 and over (work counts paid work only; screens are TV, "
                   "games and leisure computer use); sleep percentiles are for adults by age band.")
