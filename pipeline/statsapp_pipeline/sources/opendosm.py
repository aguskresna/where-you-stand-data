"""OpenDOSM (Department of Statistics Malaysia, CC BY 4.0): household income percentiles, wages,
population, life tables and consumer prices.

Each table is fetched from the OpenDOSM file store as parquet (needs pyarrow). If a download fails,
open the catalogue page printed in the error, download the CSV and save it as
pipeline/manual/opendosm/<catalogue id>.csv; the builder prefers a saved file when one exists.

The readers look for columns by name and say what they found when a layout differs, because the
catalogue occasionally renames columns between releases.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..common import PipelineError, latest, pick_column

SOURCE = "opendosm"
STORE = "https://storage.dosm.gov.my"
CATALOGUE = "https://open.dosm.gov.my/data-catalogue/{id}"

# Catalogue ids and the file-store paths to try for each.
FILES = {
    "hies_malaysia_percentile": ["hies/hies_malaysia_percentile.parquet"],
    "hies_state_percentile": ["hies/hies_state_percentile.parquet"],
    "wages_state": ["labour/wages_state.parquet", "labour/salaries_state.parquet"],
    "wages_age": ["labour/wages_age.parquet", "labour/salaries_age.parquet"],
    "wages_education": ["labour/wages_education.parquet", "labour/salaries_education.parquet"],
    "population_state": ["population/population_state.parquet"],
    "lifetables": ["demography/lifetables.parquet", "population/lifetables.parquet"],
    "lifetables_state": ["demography/lifetables_state.parquet", "population/lifetables_state.parquet"],
    "cpi_headline": ["cpi/cpi_2d.parquet", "cpi/cpi_headline.parquet"],
}

ETHNICITY = {
    "overall": "Everyone", "bumi": "Bumiputera", "bumi_malay": "Malay", "bumi_other": "Other Bumiputera",
    "chinese": "Chinese", "indian": "Indian", "other_citizen": "Other citizens", "other_noncitizen": "Non-citizens",
}
SEX = {"both": "both", "overall": "both", "all": "both", "total": "both", "male": "male", "female": "female", "lelaki": "male", "perempuan": "female"}
CPI_DIVISIONS = {
    "01": "Food and drinks", "02": "Alcohol and tobacco", "03": "Clothing and footwear", "04": "Housing and utilities",
    "05": "Furnishings and household upkeep", "06": "Health", "07": "Transport", "08": "Information and communication",
    "09": "Recreation, sport and culture", "10": "Education", "11": "Restaurants and accommodation",
    "12": "Insurance and financial services", "13": "Personal care and other",
}


MANUAL = [f"{cid}.csv" for cid in FILES]


def watch(ctx) -> list[str]:
    return [f"{STORE}/{paths[0]}" for paths in FILES.values()]


def frame(ctx, catalogue_id: str) -> pd.DataFrame:
    """A catalogue table from a saved file, or downloaded from the file store."""
    for folder in (ctx.manual_dir, ctx.raw):
        for ext in ("csv", "parquet"):
            path = folder / f"{catalogue_id}.{ext}"
            if path.exists():
                return pd.read_csv(path) if ext == "csv" else pd.read_parquet(path)
    errors = []
    for rel in FILES[catalogue_id]:
        try:
            path = ctx.download(f"{STORE}/{rel}", f"{catalogue_id}.parquet")
            return pd.read_parquet(path)
        except Exception as e:  # moved file, no pyarrow, network refused
            errors.append(str(e))
    raise PipelineError(
        f"Couldn't get {catalogue_id} ({'; '.join(errors)}). Download the CSV from {CATALOGUE.format(id=catalogue_id)} "
        f"and save it as {ctx.manual_dir / (catalogue_id + '.csv')}"
    )


def norm_sex(v) -> str:
    return SEX.get(str(v).strip().lower(), str(v).strip().lower())


def norm_age(v) -> str:
    """'15 - 19', '15–19', '15_19' -> '15-19'; '60 & above', '60 and over' -> '60+'."""
    s = str(v).strip().lower()
    if s in ("overall", "all", "total"):
        return "overall"
    m = re.match(r"^(\d+)\s*(?:\+|&\s*above|and\s*(?:above|over)|plus)$", s)
    if m:
        return f"{m.group(1)}+"
    m = re.match(r"^(\d+)\s*[-–_ ]+\s*(\d+)$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return s


def age_start(label: str) -> int:
    m = re.match(r"^(\d+)", label)
    return int(m.group(1)) if m else -1


def thresholds(rows: pd.DataFrame) -> list[float]:
    """101 thresholds from a percentile table (1..100), using maxima when present, else means."""
    pct = pick_column(rows, ["percentile"], "percentile")
    value = pick_column(rows, ["income", "value", "amount"], "income")
    var = next((c for c in rows.columns if c.lower() == "variable"), None)
    if var:
        piv = rows.pivot_table(index=pct, columns=var, values=value, aggfunc="first")
        cols = {str(c).lower(): c for c in piv.columns}
        piv = piv.reindex(range(1, 101))
        if "maximum" in cols:
            top = piv[cols["maximum"]].to_numpy(dtype=float)
            bottom = float(piv[cols["minimum"]].iloc[0]) if "minimum" in cols else top[0] / 2
            q = np.concatenate([[bottom], top])
        else:
            mean = piv[cols.get("mean", cols.get("median", next(iter(cols.values()))))].to_numpy(dtype=float)
            mids = (mean[:-1] + mean[1:]) / 2
            q = np.concatenate([[mean[0] - (mids[0] - mean[0])], mids, [mean[-1] + (mean[-1] - mids[-1])]])
    else:
        vals = rows.sort_values(pct)[value].to_numpy(dtype=float)
        if len(vals) == 101:
            q = vals
        elif len(vals) == 100:
            q = np.concatenate([[vals[0] / 2], vals])
        else:
            raise PipelineError(f"Expected 100 percentiles, found {len(vals)}")
    if np.isnan(q).any():
        raise PipelineError("Percentile table has gaps")
    q = np.maximum.accumulate(np.clip(q, 0, None))
    return [round(float(x)) for x in q]


def year_of(rows: pd.DataFrame):
    if "date" in rows.columns:
        return int(str(rows["date"].max())[:4])
    return None


def hies(ctx) -> None:
    groups, years = {}, {}
    nat = latest(frame(ctx, "hies_malaysia_percentile"))
    groups["Malaysia"], years["Malaysia"] = thresholds(nat), year_of(nat)
    states = latest(frame(ctx, "hies_state_percentile"))
    state_col = pick_column(states, ["state"], "state")
    for state, rows in states.groupby(state_col):
        groups[str(state)], years[str(state)] = thresholds(rows), year_of(rows)
    ctx.write("my.hies.percentile", {"unit": "RM/month", "groups": groups, "years": years}, year=years["Malaysia"])


def wage_table(df: pd.DataFrame, dim_candidates: list[str], what: str, norm=str) -> tuple[dict, list[str]]:
    df = latest(df)
    dim = pick_column(df, dim_candidates, what)
    sex = pick_column(df, ["sex"], "sex")
    var = next((c for c in df.columns if c.lower() == "variable"), None)
    out = {}
    order = list(dict.fromkeys(norm(v) for v in df[dim]))  # the publisher's order, before any pivot sorts it
    if var:
        value = pick_column(df, ["salary", "wages", "value", "income"], "value")
        df = df.pivot_table(index=[dim, sex], columns=var, values=value, aggfunc="first").reset_index()
    cols = {str(c).lower(): c for c in df.columns}
    median = next((cols[c] for c in cols if "median" in c), None)
    mean = next((cols[c] for c in cols if "mean" in c), None)
    if median is None:
        raise PipelineError(f"No median column for {what}; found {list(df.columns)}")
    for _, row in df.iterrows():
        key = norm(row[dim])
        out[f"{key}|{norm_sex(row[sex])}"] = {"median": round(float(row[median])), "mean": round(float(row[mean])) if mean else None}
    return out, order


def wages(ctx) -> None:
    by_state, _ = wage_table(frame(ctx, "wages_state"), ["state"], "state")
    by_age, _ = wage_table(frame(ctx, "wages_age"), ["age", "age_group"], "age group", norm_age)
    by_edu, levels = wage_table(frame(ctx, "wages_education"), ["education", "edu", "qualification"], "education")
    ctx.write("my.wages", {"byState": by_state, "byAge": by_age, "byEducation": by_edu, "educationLevels": [l for l in levels if l.lower() not in ("overall", "all")]},
              year=ctx.today.year, note="Monthly salaries and wages of Malaysian citizen employees.")


def population(ctx) -> None:
    df = latest(frame(ctx, "population_state"))
    state = pick_column(df, ["state"], "state")
    sex = pick_column(df, ["sex"], "sex")
    age = pick_column(df, ["age"], "age")
    eth = pick_column(df, ["ethnicity"], "ethnicity")
    value = pick_column(df, ["population", "value"], "population")
    df = df.assign(_age=df[age].map(norm_age), _sex=df[sex].map(norm_sex))
    df = df[df["_age"] != "overall"]
    labels = sorted(df["_age"].unique(), key=age_start)
    groups = {}
    for (st, sx, et), rows in df.groupby([state, "_sex", eth]):
        s = rows.groupby("_age")[value].sum().reindex(labels).fillna(0)
        groups[f"{st}|{sx}|{et}"] = [round(float(v), 2) for v in s]
    codes = sorted(df[eth].unique(), key=lambda c: (c != "overall", list(ETHNICITY).index(c) if c in ETHNICITY else 99, c))
    ctx.write("my.population", {"ageGroups": labels, "ethnicities": [[c, ETHNICITY.get(c, str(c).replace("_", " ").capitalize())] for c in codes], "groups": groups},
              year=year_of(df), note="Thousands of people.")


def lifetables(ctx) -> None:
    tables = {}
    for cid in ("lifetables", "lifetables_state"):
        try:
            df = latest(frame(ctx, cid))
        except PipelineError as e:
            if cid == "lifetables":
                ctx.log(f"  {e}")
                continue
            raise
        sex = pick_column(df, ["sex"], "sex")
        age = pick_column(df, ["age"], "age")
        state = next((c for c in df.columns if c.lower() == "state"), None)
        var = next((c for c in df.columns if c.lower() == "variable"), None)
        if var:
            value = pick_column(df, ["value"], "value")
            df = df.pivot_table(index=[c for c in (state, sex, age) if c], columns=var, values=value, aggfunc="first").reset_index()
        lx = pick_column(df, ["lx"], "lx")
        ex = pick_column(df, ["ex"], "ex")
        df = df.assign(_age=df[age].map(lambda v: age_start(norm_age(v))))
        for keys, rows in df.groupby([c for c in (state, sex) if c]):
            keys = keys if isinstance(keys, tuple) else (keys,)
            st, sx = (keys if state else ("Malaysia", keys[0]))
            rows = rows.sort_values("_age")
            tables[f"{st}|{norm_sex(sx)}"] = {"ages": rows["_age"].astype(int).tolist(), "lx": [round(float(v)) for v in rows[lx]], "ex": [round(float(v), 2) for v in rows[ex]]}
    if not tables:
        raise PipelineError("No life tables found")
    ctx.write("my.lifetables", {"tables": tables}, year=ctx.today.year, note="Abridged life tables; the oldest group is open-ended.")


def cpi(ctx) -> None:
    df = frame(ctx, "cpi_headline")
    date = pick_column(df, ["date"], "date")
    div = pick_column(df, ["division"], "division")
    index = pick_column(df, ["index", "value"], "index")
    df = df.assign(_d=pd.to_datetime(df[date]))
    last = df["_d"].max()
    prior = last - pd.DateOffset(years=1)
    now = df[df["_d"] == last].set_index(div)[index]
    then = df[df["_d"] == prior].set_index(div)[index]
    change = (now / then - 1).dropna()
    if "overall" not in change.index:
        raise PipelineError("The CPI table has no 'overall' division")
    groups = {str(k): {"label": CPI_DIVISIONS.get(str(k), str(k)), "change": round(float(v), 4)} for k, v in change.items() if str(k) != "overall"}
    ctx.write("my.cpi", {"asOf": last.strftime("%Y-%m"), "overall": round(float(change["overall"]), 4), "groups": groups}, year=last.year)


def build(ctx) -> None:
    problems = []
    for step in (hies, wages, population, lifetables, cpi):
        try:
            step(ctx)
        except PipelineError as e:
            problems.append(f"{step.__name__}: {e}")
            ctx.log(f"  {step.__name__} not built: {e}")
    if problems and not ctx.written:
        raise PipelineError("Nothing from OpenDOSM was built:\n  " + "\n  ".join(problems))
