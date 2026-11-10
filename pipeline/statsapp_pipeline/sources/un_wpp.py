"""UN World Population Prospects 2024 (CC BY 3.0 IGO): indicators, population by age, and life tables.

The CSV files are large, so they are downloaded by hand from https://population.un.org/wpp/downloads
(CSV format, "Medium" variant) and saved in pipeline/manual/un_wpp/. Aggregates other than the World
are skipped; the World (LocID 900) is stored under the code WLD.
"""

from __future__ import annotations

import pandas as pd

from ..common import PipelineError

SOURCE = "un_wpp"
FIRST, LAST = 1950, 2030
WORLD_LOCID = 900
HOW = "Download it from https://population.un.org/wpp/downloads (CSV format) and save it there unchanged."

INDICATORS = "WPP2024_Demographic_Indicators_Medium.csv.gz"
POP_AGE = "WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz"
LIFE = {"B": "WPP2024_Life_Table_Complete_Medium_Both_2024-2100.csv.gz",
        "F": "WPP2024_Life_Table_Complete_Medium_Female_2024-2100.csv.gz",
        "M": "WPP2024_Life_Table_Complete_Medium_Male_2024-2100.csv.gz"}
MANUAL = [INDICATORS, POP_AGE, *LIFE.values()]  # the next revision (WPP 2026) has new file names: update these


def read(path, columns, keep) -> pd.DataFrame:
    """Reads the needed columns in chunks, keeping rows where keep(chunk) is true."""
    parts = []
    for chunk in pd.read_csv(path, usecols=columns, chunksize=400_000, low_memory=False):
        parts.append(chunk[keep(chunk)])
    df = pd.concat(parts, ignore_index=True)
    return code_locations(df)


def code_locations(df: pd.DataFrame) -> pd.DataFrame:
    """Countries keep their ISO3 code, the World becomes WLD, other aggregates are dropped."""
    world = df["LocID"] == WORLD_LOCID
    country = (df["LocTypeName"] == "Country/Area") & df["ISO3_code"].notna()
    df = df[world | country].copy()
    df["code"] = df["ISO3_code"].where(~(df["LocID"] == WORLD_LOCID), "WLD")
    return df


def build(ctx) -> None:
    year = min(max(ctx.today.year, 2024), 2100)
    loc = ["LocID", "ISO3_code", "LocTypeName", "Location", "Time"]
    ind = read(ctx.manual(INDICATORS, HOW), loc + ["TPopulation1July", "Births", "TFR", "MAC", "LEx"], lambda c: c["Time"].between(FIRST, LAST))
    ages = read(ctx.manual(POP_AGE, HOW), loc + ["AgeGrpStart", "PopMale", "PopFemale"], lambda c: c["Time"] == year)
    tables = {s: read(ctx.manual(name, HOW), loc + ["AgeGrpStart", "lx", "ex"], lambda c: c["Time"] == year) for s, name in LIFE.items()}
    build_from(ctx, ind, ages, tables, year)


def build_from(ctx, ind: pd.DataFrame, ages: pd.DataFrame, tables: dict[str, pd.DataFrame], year: int) -> None:
    names = ind.drop_duplicates("code").set_index("code")["Location"].to_dict()
    names["WLD"] = "World"
    series = {}
    n = LAST - FIRST + 1
    fields = {"pop": ("TPopulation1July", 3), "births": ("Births", 3), "tfr": ("TFR", 3), "mac": ("MAC", 2), "e0": ("LEx", 2)}
    for code, rows in ind.groupby("code"):
        rows = rows.set_index("Time").reindex(range(FIRST, LAST + 1))
        series[code] = {k: [None if pd.isna(v) else round(float(v), d) for v in rows[col]] for k, (col, d) in fields.items()}
        if len(series[code]["pop"]) != n:
            raise PipelineError(f"Unexpected years for {code}")
    ctx.write("world.wpp.indicators", {"first": FIRST, "last": LAST, "countries": dict(sorted(names.items())), "series": series},
              year=2024, note="Estimates to 2023, medium-variant projections after.")

    groups = {}
    for code, rows in ages.groupby("code"):
        rows = rows.set_index("AgeGrpStart").reindex(range(101)).fillna(0)
        groups[code] = {"m": [round(float(v), 3) for v in rows["PopMale"]], "f": [round(float(v), 3) for v in rows["PopFemale"]]}
    if "WLD" not in groups:
        raise PipelineError("The population-by-age file has no World rows")
    ctx.write("world.wpp.pop_age", {"year": year, "groups": groups}, year=year, note="Thousands of people at 1 July, by single year of age (100 = 100+).")

    by_code: dict[str, dict] = {}
    for sex, df in tables.items():
        for code, rows in df.groupby("code"):
            rows = rows.sort_values("AgeGrpStart")
            by_code.setdefault(code, {})[sex] = {
                "ages": [int(a) for a in rows["AgeGrpStart"]],
                "lx": [round(float(v)) for v in rows["lx"]],
                "ex": [round(float(v), 2) for v in rows["ex"]],
            }
    for code, t in by_code.items():
        if len(t) == 3:
            ctx.write("world.wpp.lifetable", {"tables": t}, year=year, shard=code)
    ctx.finish_shards("world.wpp.lifetable", year=year)
