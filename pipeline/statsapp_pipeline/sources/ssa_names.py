"""Social Security Administration baby names, 1880 onward (CC0): name counts, ranks and yearly totals.

The national file lists every name given to at least five babies of one sex in a year. Names are split
into shards by their first two letters so the app downloads only the file it needs.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

from ..common import PipelineError

SOURCE = "ssa_names"
URL = "https://www.ssa.gov/oact/babynames/names.zip"
PAGE = "https://www.ssa.gov/oact/babynames/limits.html"
WATCH = [URL]


def read_names(path: Path) -> pd.DataFrame:
    frames = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            m = re.fullmatch(r"yob(\d{4})\.txt", Path(info.filename).name)
            if not m:
                continue
            with zf.open(info) as f:
                df = pd.read_csv(f, names=["name", "sex", "count"], dtype={"name": str, "sex": str, "count": "int64"})
            df["year"] = int(m.group(1))
            frames.append(df)
    if not frames:
        raise PipelineError(f"No yobYYYY.txt files in {path}")
    return pd.concat(frames, ignore_index=True)


def build(ctx) -> None:
    build_from(ctx, read_names(ctx.download_or_manual(URL, "names.zip", PAGE)))


def build_from(ctx, df: pd.DataFrame) -> None:
    df = df[df["name"].str.fullmatch(r"[A-Za-z]{2,}") & df["sex"].isin(["F", "M"])].copy()
    last = int(df["year"].max())
    df["rank"] = df.groupby(["year", "sex"])["count"].rank(method="min", ascending=False).astype(int)
    totals = df.groupby(["sex", "year"])["count"].sum()
    ctx.write("us.ssa.totals", {s: {str(y): int(n) for y, n in totals[s].items()} for s in ("F", "M")}, year=last,
              note="Sum of babies in the names file (names given to at least five babies), not all births.")
    df["shard"] = df["name"].str[:2].str.lower()
    df = df.sort_values(["shard", "name", "sex", "year"])
    for shard, rows in df.groupby("shard", sort=False):
        names = {}
        for (name, sex), g in rows.groupby(["name", "sex"], sort=False):
            names[f"{name}|{sex}"] = {"y": g["year"].tolist(), "c": g["count"].tolist(), "r": g["rank"].tolist()}
        ctx.write("us.ssa.names", {"names": names}, year=last, shard=shard)
    ctx.finish_shards("us.ssa.names", year=last)
