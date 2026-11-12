"""OECD Data Explorer (SDMX API, CSV): annual hours worked and time use.

OECD content is CC BY 4.0 from 1 July 2024 (OECD open-by-default policy); the Data Explorer serves it.

world.oecd.hours: "Average annual hours actually worked per worker" (DSD_HW@DF_AVG_ANN_HRS_WKD), all
workers (dependent and self-employed), each OECD member's newest year. OECD itself warns that the
series is meant for trends over time, and that level comparisons between countries are rough because
the national sources differ.

world.oecd.time_use: "Time use" (DSD_TIME_USE@DF_TIME_USE), minutes per day in OECD's five main
categories, both sexes. OECD publishes "Personal care" (sleep, eating, personal hygiene) as one
category, with no separate sleep figure, so personalCare is written as it is published. The table
has no survey year; each country's figure comes from its latest national time-use survey.

world.oecd.housing isn't built: OECD publishes house-price-to-income only as an index (2015 = 100)
or as a percentage of its long-term average, not as years of income, and no OECD table has absolute
typical home prices and household incomes per country to divide.
"""

from __future__ import annotations

import pandas as pd

from ..common import PipelineError

SOURCE = "oecd"
API = "https://sdmx.oecd.org/public/rest/data/"
QUERY = "/all?dimensionAtObservation=AllDimensions&format=csvfilewithlabels"
HOURS_URL = API + "OECD.ELS.SAE,DSD_HW@DF_AVG_ANN_HRS_WKD,1.0" + QUERY
TIME_USE_URL = API + "OECD.WISE.INE,DSD_TIME_USE@DF_TIME_USE,1.0" + QUERY
WATCH = [HOURS_URL, TIME_USE_URL]  # the API sends Last-Modified for each dataflow

# The 38 OECD members (November 2026). Romania's accession was close but not confirmed; add new
# members here when they join.
MEMBERS = {
    "AUS", "AUT", "BEL", "CAN", "CHL", "COL", "CRI", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL", "ISR", "ITA",
    "JPN", "KOR", "LVA", "LTU", "LUX", "MEX", "NLD", "NZL", "NOR", "POL", "PRT", "SVK", "SVN", "ESP", "SWE", "CHE", "TUR", "GBR", "USA",
}
TIME_USE = {"PCA": "personalCare", "PAW": "paidWork", "UPW": "unpaidWork", "LEI": "leisure", "OTH": "other"}


def read(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"REF_AREA": str, "MEASURE": str})


def build(ctx) -> None:
    hours = read(ctx.download(HOURS_URL, "avg_annual_hours.csv", refresh=not ctx.offline))
    time_use = read(ctx.download(TIME_USE_URL, "time_use.csv", refresh=not ctx.offline))
    build_from(ctx, hours, time_use)


def _check(df, columns, what):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise PipelineError(f"OECD {what} has a new layout: missing {missing}; found {list(df.columns)}")


def build_from(ctx, hours: pd.DataFrame, time_use: pd.DataFrame) -> None:
    # ------------------------------------------------ annual hours
    _check(hours, ["REF_AREA", "Reference area", "MEASURE", "UNIT_MEASURE", "WORKER_STATUS", "TIME_PERIOD", "OBS_VALUE"], "hours worked")
    h = hours[(hours["MEASURE"] == "HW") & (hours["UNIT_MEASURE"] == "H_Y_PS") & (hours["WORKER_STATUS"] == "_T") & hours["REF_AREA"].isin(MEMBERS)]
    if "JOB_COVERAGE" in h:
        h = h[h["JOB_COVERAGE"] == "_T"]
    h = h.dropna(subset=["OBS_VALUE"]).sort_values(["REF_AREA", "TIME_PERIOD"])
    newest = h.groupby("REF_AREA").tail(1)
    if newest.empty:
        raise PipelineError("No hours-worked figures for OECD members")
    countries = {iso: {"name": name, "hours": int(round(v)), "year": int(y)}
                 for iso, name, v, y in zip(newest["REF_AREA"], newest["Reference area"], newest["OBS_VALUE"], newest["TIME_PERIOD"])}
    years = sorted({v["year"] for v in countries.values()})
    ctx.write("world.oecd.hours", {"countries": countries}, year=years[-1] if len(years) == 1 else f"{years[0]}-{years[-1]}",
              note="Total hours actually worked in a year divided by average employment, newest year per country. OECD says the series "
                   "suits comparisons over time better than between countries, because national sources differ.")

    # ------------------------------------------------ time use
    _check(time_use, ["REF_AREA", "Reference area", "MEASURE", "SEX", "UNIT_MEASURE", "OBS_VALUE"], "time use")
    t = time_use[(time_use["SEX"] == "_T") & (time_use["UNIT_MEASURE"] == "MN_D") & time_use["MEASURE"].isin(TIME_USE)].dropna(subset=["OBS_VALUE"])
    out = {}
    for iso, g in t.groupby("REF_AREA", sort=True):
        minutes = {TIME_USE[m]: int(round(v)) for m, v in zip(g["MEASURE"], g["OBS_VALUE"])}
        if set(minutes) != set(TIME_USE.values()):
            continue  # a country without all five categories is left out rather than shown partly
        row = {"name": g["Reference area"].iloc[0], "minutes": minutes}
        if "OBS_STATUS" in g and (g["OBS_STATUS"] == "D").any():
            row["definitionDiffers"] = True
        out[iso] = row
    if not out:
        raise PipelineError("No complete time-use rows")
    ctx.write("world.oecd.time_use", {"countries": out}, year="latest survey",
              note="Minutes per day, both sexes, from each country's latest national time-use survey as compiled by the OECD (survey years "
                   "differ). Personal care includes sleep, eating and personal hygiene; OECD doesn't publish sleep on its own. "
                   "definitionDiffers marks countries OECD flags as 'definition differs'.")
