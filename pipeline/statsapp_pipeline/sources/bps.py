"""BPS (Statistics Indonesia) tables, saved by hand in pipeline/manual/bps/.

BPS allows commercial use with a citation of each table: its title, the date you accessed it and a
direct link. poverty_line.json carries its own citation; the CSV tables take theirs from
citations.json ({"spending_brackets.csv": {"title": ..., "accessed": "YYYY-MM-DD", "url": ...}, ...}).
See pipeline/manual/bps/README.md for each file's columns.
"""

from __future__ import annotations

import json

import pandas as pd

from ..common import PipelineError

SOURCE = "bps"
MANUAL = ["poverty_line.json", "spending_brackets.csv", "wages_province_job.csv", "wages_age.csv", "cpi_groups.csv", "citations.json"]


def citation(ctx, name: str) -> dict:
    path = ctx.manual_dir / "citations.json"
    cites = json.load(open(path, encoding="utf-8")) if path.exists() else {}
    c = cites.get(name)
    if not c or not all(c.get(k) for k in ("title", "accessed", "url")):
        raise PipelineError(f"BPS requires a citation for {name}: add its title, access date and link to {path}")
    return {k: c[k] for k in ("title", "accessed", "url")}


def poverty_line(ctx) -> None:
    path = ctx.manual("poverty_line.json", "See pipeline/manual/bps/README.md.")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    for k in ("value", "period", "bands", "citation"):
        if k not in d:
            raise PipelineError(f"poverty_line.json has no '{k}'")
    bands = d["bands"]
    if bands[0][1] != 0 or bands[-1][2] is not None or any(a[2] != b[1] for a, b in zip(bands, bands[1:])):
        raise PipelineError("poverty_line.json bands must start at 0, join up, and end open (null)")
    if not d.get("checked_against_source"):
        ctx.log("  note: poverty_line.json isn't marked as checked against the BPS release; confirm the value there, then set checked_against_source to true")
    ctx.write("id.bps.poverty_line", {"value": d["value"], "period": d["period"], "bands": bands}, year=d["period"], citation=d["citation"],
              note=d.get("note"))


def spending(ctx) -> None:
    name = "spending_brackets.csv"
    df = pd.read_csv(ctx.manual(name, "See pipeline/manual/bps/README.md."))
    provinces = {}
    for prov, rows in df.groupby("province", sort=False):
        rows = rows.sort_values("from")
        provinces[str(prov)] = [[int(r["from"]), None if pd.isna(r["to"]) else int(r["to"]), round(float(r["share"]), 4)] for _, r in rows.iterrows()]
    ctx.write("id.bps.spending", {"provinces": provinces}, year=str(df["period"].iloc[0]) if "period" in df else ctx.today.year, citation=citation(ctx, name))


def wages(ctx) -> None:
    jobs_file, age_file = "wages_province_job.csv", "wages_age.csv"
    pj = pd.read_csv(ctx.manual(jobs_file, "See pipeline/manual/bps/README.md."))
    ages = pd.read_csv(ctx.manual(age_file, "See pipeline/manual/bps/README.md."))
    by = {f"{r['province']}|{r['job']}": int(r["wage"]) for _, r in pj.iterrows()}
    jobs = [j for j in dict.fromkeys(pj["job"].astype(str)) if j != "all"]
    ctx.write("id.bps.wages", {"jobs": jobs, "byProvinceJob": by, "byAge": {str(r["age_group"]): int(r["wage"]) for _, r in ages.iterrows()}},
              year=str(pj["period"].iloc[0]) if "period" in pj else ctx.today.year,
              citation={"tables": [citation(ctx, jobs_file), citation(ctx, age_file)]})


def cpi(ctx) -> None:
    name = "cpi_groups.csv"
    df = pd.read_csv(ctx.manual(name, "See pipeline/manual/bps/README.md."), dtype={"code": str})
    overall = df[df["code"] == "overall"]
    if overall.empty:
        raise PipelineError("cpi_groups.csv needs an 'overall' row")
    rest = df[df["code"] != "overall"]
    groups = {r["code"]: {"label": r["label"], "change": float(r["change"]), **({"weight": float(r["weight"])} if "weight" in df and not pd.isna(r["weight"]) else {})} for _, r in rest.iterrows()}
    ctx.write("id.bps.cpi", {"asOf": str(df["as_of"].iloc[0]), "overall": float(overall["change"].iloc[0]), "groups": groups}, year=str(df["as_of"].iloc[0])[:4], citation=citation(ctx, name))


def build(ctx) -> None:
    problems = []
    for step, needed in ((poverty_line, "poverty_line.json"), (spending, "spending_brackets.csv"), (wages, "wages_province_job.csv"), (cpi, "cpi_groups.csv")):
        if not any((folder / needed).exists() for folder in (ctx.manual_dir, ctx.raw)):
            ctx.log(f"  skipped {step.__name__}: no {needed} yet")
            continue
        try:
            step(ctx)
        except PipelineError as e:
            problems.append(str(e))
            ctx.log(f"  {step.__name__} not built: {e}")
    if not ctx.written:
        raise PipelineError("; ".join(problems) or f"No BPS files found in {ctx.manual_dir}")
