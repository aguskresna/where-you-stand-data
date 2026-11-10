"""American Community Survey 1-year PUMS (US Census Bureau, public domain): 17 datasets.

Downloads the person and housing CSV zips plus the data dictionary (for occupation, field-of-degree,
language and birthplace labels). Dollar amounts are adjusted with ADJINC. Groups with fewer than
MIN_RECORDS person records are left out so the app falls back to broader groups.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from ..common import AGE_BANDS, EDU_BANDS, HOUSEHOLDER_BANDS, PipelineError, band_of, by_groups, round_to, weighted_median, weighted_quantiles, weighted_share
from ..regions import FIPS_TO_USPS, USPS

SOURCE = "census_acs_pums"
DEFAULT_YEAR = 2024
PAGE = "https://www.census.gov/programs-surveys/acs/microdata/access.html"

PERSON_COLS = ["SERIALNO", "ST", "AGEP", "SEX", "RAC1P", "HISP", "MAR", "SCHL", "PINCP", "PERNP", "ADJINC", "PWGTP",
               "JWMNP", "WKHP", "WKWN", "RELSHIPP", "LANX", "LANP", "POBP", "FOD1P", "OCCP", "PAOC"]
HOUSING_COLS = ["SERIALNO", "ST", "WGTP", "NP", "HINCP", "ADJINC", "TEN", "VALP", "GRPIP", "NOC", "TYPEHUGQ"]

RACES = ["white", "black", "asian", "hispanic", "other"]
MARITAL = ["never", "married", "previously"]
EDU_LEVELS = ["Less than high school", "High school or GED", "Some college or associate degree", "Bachelor's degree", "Graduate or professional degree"]

# RELSHIPP (2019 onward): 20 reference person, 21 opposite-sex spouse, 22 opposite-sex unmarried partner,
# 23 same-sex spouse, 24 same-sex unmarried partner, 25 biological child, 26 adopted child, 27 stepchild.
HOUSEHOLDER, PARTNERS, CHILDREN = 20, (21, 22, 23, 24), (25, 26, 27)


def read_zip_csvs(path: Path, prefix: str, columns: list[str]) -> pd.DataFrame:
    """Reads every CSV in the zip whose name starts with prefix (psam_pusa.csv, psam_pusb.csv, ...)."""
    frames = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = Path(info.filename).name
            if not (name.lower().startswith(prefix) and name.lower().endswith(".csv")):
                continue
            with zf.open(info) as f:
                header = pd.read_csv(f, nrows=0).columns
            missing = [c for c in columns if c not in header]
            if missing:
                raise PipelineError(f"{name} has no column(s) {missing}")
            with zf.open(info) as f:
                frames.append(pd.read_csv(f, usecols=columns, dtype={"SERIALNO": str}, low_memory=False))
    if not frames:
        raise PipelineError(f"No {prefix}*.csv files in {path}")
    return pd.concat(frames, ignore_index=True)


def read_dictionary(path: Path) -> dict[str, dict[str, str]]:
    """Value labels from the PUMS data dictionary CSV: {variable: {code: label}} for VAL rows."""
    labels: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for row in csv.reader(f):
            if len(row) >= 7 and row[0] == "VAL" and row[4] == row[5]:
                labels.setdefault(row[1], {})[code_key(row[4])] = row[6].strip()
    return labels


def code_key(code) -> str:
    """Codes compare as integers without leading zeros: '0010' and 10 both become '10'."""
    s = str(code).strip()
    try:
        return str(int(float(s)))
    except ValueError:
        return s


def tidy_label(label: str, sentence: bool = False) -> str:
    """'MGR-Chief Executives And Legislators' -> 'Chief executives and legislators' (sentence=True).

    Place and language names keep their capitals.
    """
    label = re.sub(r"^[A-Z]{3}-", "", str(label)).strip()
    label = re.sub(r"\s+", " ", label)
    return label[:1].upper() + label[1:].lower() if sentence else label


def recode_people(p: pd.DataFrame, h: pd.DataFrame) -> pd.DataFrame:
    p = p.copy()
    p["state"] = p["ST"].map(FIPS_TO_USPS)
    p = p[p["state"].notna()]
    adj = p["ADJINC"] / 1e6
    p["age"] = p["AGEP"].astype(int)
    p["sex"] = np.where(p["SEX"] == 1, "M", "F")
    p["band"] = band_of(p["age"], AGE_BANDS)
    p["eband"] = band_of(p["age"], EDU_BANDS)
    hisp = p["HISP"].fillna(1) > 1
    p["race"] = np.select(
        [hisp, p["RAC1P"] == 1, p["RAC1P"] == 2, p["RAC1P"] == 6],
        ["hispanic", "white", "black", "asian"],
        default="other",
    )
    p["marital"] = np.select([p["MAR"] == 5, p["MAR"] == 1], ["never", "married"], default="previously")
    schl = p["SCHL"].fillna(0)
    p["edu"] = np.select([schl < 16, schl <= 17, schl <= 20, schl == 21], [0, 1, 2, 3], default=4)
    p["income"] = p["PINCP"] * adj
    p["earn"] = p["PERNP"] * adj
    p["w"] = p["PWGTP"].astype(float)
    noc = h.set_index("SERIALNO")["NOC"]
    p["noc"] = p["SERIALNO"].map(noc).fillna(0)
    in_couple = p["RELSHIPP"].isin([HOUSEHOLDER, *PARTNERS])
    p["kids"] = ((in_couple & (p["noc"] > 0)) | p["PAOC"].isin([1, 2, 3])).astype(int)
    p["bilingual"] = (p["LANX"] == 1).astype(int)
    p["fulltime"] = (p["WKHP"].fillna(0) >= 35) & (p["WKWN"].fillna(0) >= 50)
    return p


def recode_households(h: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    h = h[(h["TYPEHUGQ"] == 1) & h["NP"].fillna(0).gt(0)].copy()
    h["state"] = h["ST"].map(FIPS_TO_USPS)
    h = h[h["state"].notna()]
    ages = p.loc[p["RELSHIPP"] == HOUSEHOLDER].set_index("SERIALNO")["age"]
    h["hage"] = h["SERIALNO"].map(ages)
    h["hband"] = band_of(h["hage"].fillna(-1), HOUSEHOLDER_BANDS)
    h["income"] = h["HINCP"] * h["ADJINC"] / 1e6
    h["adj3"] = h["income"] * np.sqrt(3 / h["NP"])
    h["owner"] = h["TEN"].isin([1, 2])
    h["renter"] = h["TEN"] == 3
    h["w"] = h["WGTP"].astype(float)
    return h


def q(col: str, digits: int = 0):
    return lambda rows: weighted_quantiles(rows[col], rows["w"], digits=digits)


def share(test):
    return lambda rows: round(weighted_share(test(rows), rows["w"]), 4)


def files_for(year: int) -> str:
    return f"https://www2.census.gov/programs-surveys/acs/data/pums/{year}/1-Year/"


def latest_year(ctx) -> int:
    """The newest ACS 1-year PUMS release on the Census site (each one comes out in the autumn)."""
    if ctx.options.get("year"):
        return int(ctx.options["year"])
    for year in range(ctx.today.year - 1, DEFAULT_YEAR - 1, -1):
        try:
            if ctx.exists(files_for(year) + "csv_pus.zip"):
                return year
        except Exception:
            break
    return DEFAULT_YEAR


def watch(ctx) -> list[str]:
    base = files_for(latest_year(ctx))
    return [base + "csv_pus.zip", base + "csv_hus.zip"]


def build(ctx) -> None:
    year = latest_year(ctx)
    base = files_for(year)
    pz = ctx.download_or_manual(base + "csv_pus.zip", f"{year}_csv_pus.zip", PAGE)
    hz = ctx.download_or_manual(base + "csv_hus.zip", f"{year}_csv_hus.zip", PAGE)
    dd = ctx.download_or_manual(
        f"https://www2.census.gov/programs-surveys/acs/tech_docs/pums/data_dict/PUMS_Data_Dictionary_{year}.csv",
        f"{year}_dictionary.csv",
        "https://www.census.gov/programs-surveys/acs/microdata/documentation.html",
    )
    ctx.log("  reading PUMS files (this takes a few minutes)")
    labels = read_dictionary(dd)
    raw_h = read_zip_csvs(hz, "psam_h", HOUSING_COLS)
    p = recode_people(read_zip_csvs(pz, "psam_p", PERSON_COLS), raw_h)
    h = recode_households(raw_h, p)
    build_all(ctx, p, h, labels, year)


def build_all(ctx, p: pd.DataFrame, h: pd.DataFrame, labels: dict, year: int) -> None:
    n = ctx.min_records
    adults = p[p["age"] >= 18]
    states = USPS

    # Weighted random sample of adults for the stacked-filter questions.
    size = min(int(ctx.options.get("sample_size", 80000)), len(adults))
    rng = np.random.default_rng(int(ctx.options.get("seed", year)))
    s = adults.iloc[np.sort(rng.choice(len(adults), size, replace=False))]
    w = s["w"] * (adults["w"].sum() / s["w"].sum())
    ctx.write("us.acs.sample", {
        "columns": ["sex", "age", "race", "marital", "edu", "income", "kids", "bilingual", "state", "w"],
        "weight": "w",
        "population": round(float(adults["w"].sum())),
        "codes": {"sex": ["M", "F"], "race": RACES, "marital": MARITAL, "state": states},
        "rows": {
            "sex": (s["sex"] == "F").astype(int).tolist(),
            "age": s["age"].tolist(),
            "race": s["race"].map(RACES.index).tolist(),
            "marital": s["marital"].map(MARITAL.index).tolist(),
            "edu": s["edu"].astype(int).tolist(),
            "income": (np.round(s["income"].fillna(0).clip(lower=0) / 100) * 100).astype(int).tolist(),
            "kids": s["kids"].tolist(),
            "bilingual": s["bilingual"].tolist(),
            "state": s["state"].map(states.index).tolist(),
            "w": np.round(w, 1).tolist(),
        },
    }, year=year, note=f"Simple random sample of {size:,} adults, reweighted to the adult population.")

    earners = adults[adults["income"] > 0]
    ctx.write("us.acs.income_q", {
        "unit": "USD/year",
        "groups": by_groups(earners, {"sex": ["M", "F"], "band": AGE_BANDS, "state": states}, q("income", -2), n),
    }, year=year)

    hh = h[h["income"].notna()]
    ctx.write("us.acs.hh_income", {
        "unit": "USD/year",
        "median_adj3": round_to(weighted_median(hh["adj3"], hh["w"]), -2),
        "groups": by_groups(hh, {"state": states}, q("adj3", -2), n),
    }, year=year, note="Household income adjusted to a three-person household (income × √(3 / size)).")

    married = share(lambda r: r["marital"] != "never")
    by_age = {}
    for (sex, age), rows in adults[adults["age"] <= 80].groupby(["sex", "age"]):
        if len(rows) >= n:
            by_age[f"{sex}|{age}"] = married(rows)
    ctx.write("us.acs.ever_married", {
        "byAge": by_age,
        "byBandState": by_groups(adults, {"sex": ["M", "F"], "band": AGE_BANDS, "state": states}, married, n),
    }, year=year)

    young = adults[adults["age"] <= 40]
    ctx.write("us.acs.with_parents", {
        "groups": by_groups(young, {"sex": ["M", "F"], "age": list(range(18, 41))}, share(lambda r: r["RELSHIPP"].isin(CHILDREN)), n),
    }, year=year)

    owned = h[h["hband"] != ""]
    ctx.write("us.acs.ownership", {
        "groups": by_groups(owned, {"hband": HOUSEHOLDER_BANDS, "state": states}, share(lambda r: r["owner"]), n),
    }, year=year)

    renters = h[h["renter"] & h["GRPIP"].fillna(0).gt(0)]
    ctx.write("us.acs.rent_burden", {"unit": "% of income", "groups": by_groups(renters, {"state": states}, q("GRPIP"), n)}, year=year)

    owners = h[h["owner"] & h["VALP"].fillna(0).gt(0)]
    values = by_groups(owners, {"state": states}, lambda r: weighted_median(r["VALP"], r["w"]), n)
    incomes = by_groups(hh, {"state": states}, lambda r: weighted_median(r["income"], r["w"]), n)
    ctx.write("us.acs.housing", {
        "groups": {k: {"value": round_to(v, -3), "income": round_to(incomes[k], -2)} for k, v in values.items() if k in incomes},
    }, year=year)

    commuters = p[p["JWMNP"].fillna(0).gt(0)]
    ctx.write("us.acs.commute_q", {"unit": "minutes", "groups": by_groups(commuters, {"state": states}, q("JWMNP"), n)}, year=year)

    workers = adults[adults["WKHP"].fillna(0).gt(0)]
    ctx.write("us.acs.work_hours_q", {"unit": "hours/week", "groups": by_groups(workers, {"sex": ["M", "F"], "band": AGE_BANDS}, q("WKHP"), n)}, year=year)

    parents = adults[adults["RELSHIPP"].isin([HOUSEHOLDER, *PARTNERS])].copy()
    parents["kidcat"] = parents["noc"].clip(upper=4).astype(int)
    ctx.write("us.acs.children", {
        "categories": ["0", "1", "2", "3", "4+"],
        "groups": by_groups(parents, {"band": AGE_BANDS}, lambda r: [round(weighted_share(r["kidcat"] == k, r["w"]), 4) for k in range(5)], n),
    }, year=year)

    grown = p[p["age"] >= 25]
    ctx.write("us.acs.education", {
        "levels": EDU_LEVELS,
        "groups": by_groups(grown, {"eband": EDU_BANDS}, lambda r: [round(weighted_share(r["edu"] == k, r["w"]), 4) for k in range(5)], n),
    }, year=year)

    graduates = p[(p["age"].between(25, 64)) & p["fulltime"] & p["FOD1P"].notna() & (p["earn"] > 0)]
    fields = {}
    fod = labels.get("FOD1P", {})
    for code, rows in graduates.groupby(graduates["FOD1P"].map(code_key)):
        if len(rows) < max(n, 100):
            continue
        qs = weighted_quantiles(rows["earn"], rows["w"], n=5, digits=-2)
        fields[code] = {"label": tidy_label(fod.get(code, code), sentence=True), "median": qs[2], "p25": qs[1], "p75": qs[3], "n": len(rows)}
    ctx.write("us.acs.degree_earnings", {
        "overall": {"median": round_to(weighted_median(graduates["earn"], graduates["w"]), -2)},
        "fields": fields,
    }, year=year, note="Full-time, year-round workers aged 25 to 64; first field of degree listed.")

    ctx.write("us.acs.couples", couples(p, h), year=year, note="Opposite-sex married and unmarried couples living together.")

    full = adults[adults["fulltime"] & (adults["earn"] > 0) & adults["OCCP"].notna()]
    occ = labels.get("OCCP", {})
    occupations = {}
    for code, rows in full.groupby(full["OCCP"].map(code_key)):
        f, m = rows[rows["sex"] == "F"], rows[rows["sex"] == "M"]
        if len(f) >= n and len(m) >= n:
            occupations[code] = {
                "label": tidy_label(occ.get(code, code), sentence=True),
                "F": round_to(weighted_median(f["earn"], f["w"]), -2), "M": round_to(weighted_median(m["earn"], m["w"]), -2),
                "nF": len(f), "nM": len(m),
            }
    ctx.write("us.acs.occ_pay_gap", {
        "all": {s: round_to(weighted_median(full.loc[full["sex"] == s, "earn"], full.loc[full["sex"] == s, "w"]), -2) for s in ("F", "M")},
        "occupations": occupations,
    }, year=year, note="Median earnings of full-time, year-round workers.")

    speakers = p[(p["age"] >= 5) & (p["LANX"] == 1) & p["LANP"].notna()]
    ctx.write("us.acs.languages", {"languages": counts_with_states(speakers, "LANP", labels.get("LANP", {}), n)}, year=year)

    born_abroad = p[p["POBP"].fillna(0) >= 100]
    countries = counts_with_states(born_abroad, "POBP", labels.get("POBP", {}), n, key="people")
    for code, rows in born_abroad[(born_abroad["age"] >= 18) & (born_abroad["income"] > 0)].groupby(born_abroad["POBP"].map(code_key)):
        if code in countries:
            countries[code]["medianIncome"] = round_to(weighted_median(rows["income"], rows["w"]), -2)
    ctx.write("us.acs.diaspora", {"countries": {k: v for k, v in countries.items() if "medianIncome" in v}}, year=year)


def counts_with_states(rows: pd.DataFrame, column: str, labels: dict, n: int, key: str = "speakers") -> dict:
    out = {}
    codes = rows[column].map(code_key)
    for code, g in rows.groupby(codes):
        if len(g) < n:
            continue
        by_state = g.groupby("state")["w"].sum().sort_values(ascending=False).head(5)
        out[code] = {"label": tidy_label(labels.get(code, code)), key: round(float(g["w"].sum())), "states": [[s, round(float(v))] for s, v in by_state.items()]}
    return out


def couples(p: pd.DataFrame, h: pd.DataFrame) -> dict:
    cols = ["SERIALNO", "sex", "age", "edu", "race", "earn"]
    ref = p.loc[p["RELSHIPP"] == HOUSEHOLDER, cols]
    partner = p.loc[p["RELSHIPP"].isin([21, 22]), cols]
    c = ref.merge(partner, on="SERIALNO", suffixes=("_a", "_b"))
    c = c[c["sex_a"] != c["sex_b"]]
    a_is_man = c["sex_a"] == "M"
    pick = lambda col: (np.where(a_is_man, c[f"{col}_a"], c[f"{col}_b"]), np.where(a_is_man, c[f"{col}_b"], c[f"{col}_a"]))
    age_m, age_w = pick("age")
    edu_m, edu_w = pick("edu")
    race_m, race_w = pick("race")
    earn_m, earn_w = pick("earn")
    w = c["SERIALNO"].map(h.set_index("SERIALNO")["w"]).fillna(0).to_numpy()
    if not (w > 0).any():
        raise PipelineError("No couples with household weights")
    edu_m, edu_w = edu_m.astype(int), edu_w.astype(int)
    pairs = lambda a, b, keys: {f"{x}|{y}": round(weighted_share((a == x) & (b == y), w), 4) for x in keys for y in keys}
    earns = {}
    for x in range(5):
        for y in range(5):
            m = (edu_m == x) & (edu_w == y)
            if w[m].sum() > 0:
                earns[f"{x}|{y}"] = round(weighted_share(np.nan_to_num(earn_m[m].astype(float)) > np.nan_to_num(earn_w[m].astype(float)), w[m]), 3)
    return {
        "gap": weighted_quantiles(np.abs(age_m - age_w), w),
        "manOlder": round(weighted_share(age_m > age_w, w), 4),
        "womanOlder": round(weighted_share(age_w > age_m, w), 4),
        "sameAge": round(weighted_share(age_m == age_w, w), 4),
        "eduPairs": pairs(edu_m, edu_w, range(5)),
        "racePairs": pairs(race_m, race_w, RACES),
        "manEarnsMore": earns,
    }
