"""Each builder against small made-up files in the publisher's layout. Real files are much larger,
and the layouts of OpenDOSM, data.gov.my and BPS tables should be checked on the first real run."""

import io
import json
import shutil
import zipfile

import numpy as np
import pandas as pd
import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import acs_pums, births_538, bps, datagovmy_births, nhanes, opendosm, ssa_names, un_wpp, worldbank_pip, worldbank_wdi
from statsapp_pipeline.__main__ import gate
from statsapp_pipeline.common import load_sources
from conftest import ROOT

ascending = lambda v: all(b >= a for a, b in zip(v, v[1:]))


# ---------------------------------------------------------------- ACS PUMS


def fake_pums(n_households=400, seed=1):
    rng = np.random.default_rng(seed)
    people, homes = [], []
    for i in range(n_households):
        serial = f"2024HU{i:07d}"
        st = int(rng.choice([6, 48, 36, 12]))
        size = int(rng.integers(1, 5))
        homes.append({"SERIALNO": serial, "ST": st, "WGTP": float(rng.integers(50, 150)), "NP": size, "HINCP": float(rng.integers(10, 300) * 1000),
                      "ADJINC": 1010000, "TEN": int(rng.choice([1, 2, 3])), "VALP": float(rng.integers(100, 900) * 1000), "GRPIP": float(rng.integers(10, 80)),
                      "NOC": int(rng.integers(0, 3)), "TYPEHUGQ": 1})
        for j in range(size):
            rel = 20 if j == 0 else 21 if j == 1 else 25
            sex = (1 if j == 0 else 2) if j < 2 else int(rng.choice([1, 2]))
            age = int(rng.integers(25, 80)) if j < 2 else int(rng.integers(2, 35))
            people.append({"SERIALNO": serial, "ST": st, "AGEP": age, "SEX": sex, "RAC1P": int(rng.choice([1, 2, 6, 8])), "HISP": int(rng.choice([1, 1, 2])),
                           "MAR": int(rng.choice([1, 3, 5])), "SCHL": int(rng.integers(10, 25)), "PINCP": float(rng.integers(0, 200) * 1000),
                           "PERNP": float(rng.integers(0, 150) * 1000), "ADJINC": 1010000, "PWGTP": float(rng.integers(50, 150)),
                           "JWMNP": float(rng.integers(0, 60)), "WKHP": float(rng.integers(0, 60)), "WKWN": float(rng.integers(0, 53)),
                           "RELSHIPP": rel, "LANX": int(rng.choice([1, 2])), "LANP": float(rng.choice([1200, 1970])), "POBP": float(rng.choice([6, 303, 210])),
                           "FOD1P": float(rng.choice([2102, 6203])) if rng.random() < 0.5 else np.nan, "OCCP": float(rng.choice([10, 1021])), "PAOC": float(rng.choice([1, 4]))})
    return pd.DataFrame(people), pd.DataFrame(homes)


def test_acs_builds_every_dataset_in_the_shapes_the_app_reads(make_ctx, read):
    p_raw, h_raw = fake_pums()
    p = acs_pums.recode_people(p_raw, h_raw)
    h = acs_pums.recode_households(h_raw, p)
    ctx = make_ctx("census_acs_pums")
    labels = {"FOD1P": {"2102": "Computer Science"}, "OCCP": {"10": "MGR-Chief Executives And Legislators"}, "LANP": {"1200": "Spanish"}, "POBP": {"303": "Mexico"}}
    acs_pums.build_all(ctx, p, h, labels, 2024)
    built = json.loads((make_ctx.data / "manifest.json").read_text())["datasets"]
    expected = [d for d, s in json.loads((ROOT / "data/contract.json").read_text())["datasets"].items() if "census_acs_pums" in s["sources"]]
    assert sorted(built) == sorted(expected)

    # Only group figures are published, never individual survey rows.
    assert not any("sample" in d for d in built)

    singles = read(make_ctx.data, "us.acs.singles")["data"]
    lo, hi = singles["ages"]
    us_women = singles["groups"]["F|*"]
    assert len(us_women["all"]) == hi - lo + 1
    assert all(s is None or s <= a for s, a in zip(us_women["single"], us_women["all"]))

    inc = read(make_ctx.data, "us.acs.income_q")["data"]["groups"]
    assert "*|*|*" in inc and len(inc["*|*|*"]) == 101 and ascending(inc["*|*|*"])
    assert any(k.endswith("|CA") for k in inc)

    couples = read(make_ctx.data, "us.acs.couples")["data"]
    assert couples["manOlder"] + couples["womanOlder"] + couples["sameAge"] == pytest.approx(1, abs=1e-3)
    assert sum(couples["eduPairs"].values()) == pytest.approx(1, abs=1e-2)

    occ = read(make_ctx.data, "us.acs.occ_pay_gap")["data"]["occupations"]
    assert occ["10"]["label"] == "Chief executives and legislators"
    langs = read(make_ctx.data, "us.acs.languages")["data"]["languages"]
    assert langs["1200"]["label"] == "Spanish" and langs["1200"]["states"][0][0] in {"CA", "TX", "NY", "FL"}
    kids = read(make_ctx.data, "us.acs.children")["data"]["groups"]
    assert sum(kids["*"]) == pytest.approx(1, abs=1e-3)


def test_acs_reads_split_csvs_from_the_zip_and_the_dictionary(tmp_path):
    p, _ = fake_pums(5)
    z = tmp_path / "p.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("psam_pusa.csv", p.iloc[:3].to_csv(index=False))
        zf.writestr("psam_pusb.csv", p.iloc[3:].to_csv(index=False))
        zf.writestr("ACS2024_PUMS_README.pdf", "x")
    df = acs_pums.read_zip_csvs(z, "psam_p", ["SERIALNO", "AGEP"])
    assert len(df) == len(p)
    with pytest.raises(PipelineError, match="no column"):
        acs_pums.read_zip_csvs(z, "psam_p", ["NOPE"])
    d = tmp_path / "dict.csv"
    d.write_text('NAME,OCCP,C,4,"Occupation"\nVAL,OCCP,C,4,0010,0010,"MGR-Chief Executives And Legislators"\nVAL,AGEP,N,2,0,99,"Age"\n')
    assert acs_pums.read_dictionary(d) == {"OCCP": {"10": "MGR-Chief Executives And Legislators"}}


# ---------------------------------------------------------------- NHANES, SSA, births


def test_nhanes(make_ctx, read):
    rng = np.random.default_rng(2)
    n = 600
    demo = pd.DataFrame({"SEQN": range(n), "RIAGENDR": rng.choice([1, 2], n), "RIDAGEYR": rng.integers(10, 81, n), "WTMEC2YR": rng.uniform(1000, 9000, n)})
    exam = pd.DataFrame({"SEQN": range(n), "BMXHT": rng.normal(170, 9, n), "BMXWT": rng.normal(80, 15, n), "BMXWAIST": rng.normal(98, 14, n), "BMXBMI": rng.normal(28, 6, n)})
    nhanes.build_from(make_ctx("nchs_nhanes"), demo, exam)
    d = read(make_ctx.data, "us.nhanes.body")["data"]
    assert set(d["measures"]) == {"height_cm", "weight_kg", "waist_cm", "bmi"}
    assert ascending(d["measures"]["height_cm"]["groups"]["F|25-34"])
    assert 0 < d["shares"]["obese"]["groups"]["*|*"] < 1


def test_ssa_names_shards_ranks_and_totals(make_ctx, read):
    df = pd.DataFrame([("Olivia", "F", 100, 2020), ("Emma", "F", 120, 2020), ("Olivia", "F", 90, 2021), ("Oliver", "M", 80, 2021), ("Emma", "F", 50, 2021), ("X", "F", 9, 2021)],
                      columns=["name", "sex", "count", "year"])
    ssa_names.build_from(make_ctx("ssa_names"), df)
    ol = read(make_ctx.data, "us.ssa.names", "ol")["data"]["names"]
    assert ol["Olivia|F"] == {"y": [2020, 2021], "c": [100, 90], "r": [2, 1]}
    assert "Oliver|M" in ol
    totals = read(make_ctx.data, "us.ssa.totals")["data"]
    assert totals["F"]["2021"] == 140


def test_births_538_averages_by_calendar_date(make_ctx, read):
    ssa = pd.DataFrame({"year": [2000, 2001, 2000], "month": [1, 1, 2], "date_of_month": [1, 1, 29], "births": [100, 200, 50]})
    cdc = pd.DataFrame({"year": [1999, 2000], "month": [1, 1], "date_of_month": [1, 1], "births": [300, 999]})
    births_538.build_from(make_ctx("births_538"), ssa, cdc)
    d = read(make_ctx.data, "us.births.daily")["data"]
    assert d["years"] == [1999, 2001]
    assert d["byDate"]["01-01"] == 200 and d["byDate"]["02-29"] == 50


# ---------------------------------------------------------------- UN, World Bank


def wpp_frames(year=2026):
    rows = []
    for loc, iso, typ, name, scale in [(900, None, "World", "World", 100), (360, "IDN", "Country/Area", "Indonesia", 3), (458, "MYS", "Country/Area", "Malaysia", 0.4), (5500, None, "Region", "Asia", 50)]:
        for t in range(1950, 2031):
            rows.append({"LocID": loc, "ISO3_code": iso, "LocTypeName": typ, "Location": name, "Time": t, "TPopulation1July": scale * 1000 + t,
                         "Births": scale * 20, "TFR": 2.5, "MAC": 29.1, "LEx": 70 + (t - 1950) / 10})
    ind = un_wpp.code_locations(pd.DataFrame(rows))
    ages = un_wpp.code_locations(pd.DataFrame([{"LocID": loc, "ISO3_code": iso, "LocTypeName": typ, "Location": "", "Time": year, "AgeGrpStart": a, "PopMale": 10.0, "PopFemale": 11.0}
                                               for loc, iso, typ in [(900, None, "World"), (360, "IDN", "Country/Area")] for a in range(101)]))
    life = {s: un_wpp.code_locations(pd.DataFrame([{"LocID": 360, "ISO3_code": "IDN", "LocTypeName": "Country/Area", "Location": "", "Time": year, "AgeGrpStart": a,
                                                     "lx": 100000 * (1 - a / 101), "ex": 75 - a * 0.7} for a in range(101)])) for s in ("B", "F", "M")}
    return ind, ages, life


def test_un_wpp(make_ctx, read):
    ind, ages, life = wpp_frames()
    un_wpp.build_from(make_ctx("un_wpp"), ind, ages, life, 2026)
    w = read(make_ctx.data, "world.wpp.indicators")["data"]
    assert set(w["countries"]) == {"WLD", "IDN", "MYS"}
    assert len(w["series"]["IDN"]["pop"]) == 81 and w["series"]["WLD"]["e0"][0] == 70
    pa = read(make_ctx.data, "world.wpp.pop_age")["data"]
    assert pa["year"] == 2026 and len(pa["groups"]["WLD"]["m"]) == 101
    lt = read(make_ctx.data, "world.wpp.lifetable", "IDN")["data"]["tables"]
    assert set(lt) == {"B", "F", "M"} and lt["B"]["ages"][-1] == 100


def test_pip_thresholds_and_population(make_ctx, read):
    rows = []
    for iso in ("IDN", "MYS"):
        for p in range(1, 101):
            rows.append({"country_code": iso, "year": 2023, "reporting_level": "national", "welfare_type": "consumption" if iso == "IDN" else "income",
                         "percentile": p, "avg_welfare": p * 0.1 + 0.05, "quantile": p * 0.1})
    ind, _, _ = wpp_frames()
    ctx = make_ctx("un_wpp")
    un_wpp.build_from(ctx, ind, *wpp_frames()[1:], 2026)
    wpp = read(make_ctx.data, "world.wpp.indicators")["data"]
    worldbank_pip.build_from(make_ctx("worldbank_pip"), pd.DataFrame(rows), wpp)
    c = read(make_ctx.data, "world.pip.percentiles")["data"]["countries"]
    assert c["IDN"]["welfare"] == "consumption" and len(c["IDN"]["q"]) == 99 and ascending(c["IDN"]["q"])
    assert c["IDN"]["q"][49] == pytest.approx(5.0) and len(c["IDN"]["m"]) == 100 and c["IDN"]["pop"] == (3 * 1000 + 2023) * 1000


def test_wdi_keeps_only_cc_by_indicators(make_ctx, read, monkeypatch):
    ctx = make_ctx("worldbank_wdi")

    def fake(url, params=None):
        if "metadata" in url:
            code = url.split("/series/")[1].split("/")[0]
            lic = "CC BY-4.0" if code != "IT.NET.USER.ZS" else "Custom (see terms)"
            return {"source": [{"concept": [{"variable": [{"concept": [{"id": "License_Type", "value": lic}]}]}]}]}
        return [{"page": 1, "pages": 1}, [{"countryiso3code": "IDN", "date": "2021", "value": 4800.5}, {"countryiso3code": "", "date": "2021", "value": 1}]]

    monkeypatch.setattr(ctx, "fetch_json", fake)
    worldbank_wdi.build(ctx)
    ind = read(make_ctx.data, "world.wdi")["data"]["indicators"]
    assert "IT.NET.USER.ZS" not in ind and ind["PA.NUS.PRVT.PP"]["series"]["IDN"]["2021"] == 4800.5


# ---------------------------------------------------------------- Malaysia


def write_csv(folder, name, df):
    folder.mkdir(parents=True, exist_ok=True)
    df.to_csv(folder / name, index=False)


def test_opendosm_tables(make_ctx, read):
    ctx = make_ctx("opendosm")
    m = ctx.manual_dir
    pct = lambda extra: pd.DataFrame([{**extra, "date": "2024-01-01", "percentile": p, "variable": v, "income": p * 100 + (0 if v == "minimum" else 99)}
                                      for p in range(1, 101) for v in ("minimum", "maximum", "mean")])
    write_csv(m, "hies_malaysia_percentile.csv", pct({}))
    write_csv(m, "hies_state_percentile.csv", pd.concat([pct({"state": "Selangor"}), pct({"state": "Johor"})]))
    wages = lambda dim, vals: pd.DataFrame([{"date": "2024-01-01", dim: v, "sex": s, "variable": var, "salary": 3000 + i * 100}
                                            for i, v in enumerate(vals) for s in ("both", "male", "female") for var in ("median", "mean")])
    write_csv(m, "wages_state.csv", wages("state", ["Malaysia", "Selangor"]))
    write_csv(m, "wages_age.csv", wages("age", ["overall", "15-19", "60 & above"]))
    write_csv(m, "wages_education.csv", wages("education", ["overall", "SPM", "Degree"]))
    write_csv(m, "population_state.csv", pd.DataFrame([{"date": "2023-01-01", "state": st, "sex": "both", "age": a, "ethnicity": e, "population": 10.0}
                                                       for st in ("Malaysia", "Johor") for a in ("overall", "0-4", "5-9", "85+") for e in ("overall", "chinese")]))
    write_csv(m, "lifetables_state.csv", pd.DataFrame([{"date": "2023-01-01", "state": "Johor", "sex": s, "age": a, "lx": 100000 - i * 1000, "ex": 75 - i}
                                                       for s in ("both", "male", "female") for i, a in enumerate(["0", "1", "5", "80+"])]))
    write_csv(m, "cpi_headline.csv", pd.DataFrame([{"date": d, "division": k, "index": v} for d, f in (("2025-09-01", 1.0), ("2026-09-01", 1.02))
                                                   for k, v in (("overall", 100 * f), ("01", 110 * f * 1.01))]))
    opendosm.build(ctx)
    h = read(make_ctx.data, "my.hies.percentile")["data"]
    assert h["groups"]["Malaysia"][0] == 100 and h["groups"]["Malaysia"][100] == 10099 and h["years"]["Selangor"] == 2024
    assert h["p"] == list(range(101))
    w = read(make_ctx.data, "my.wages")["data"]
    assert w["byAge"]["60+|both"]["median"] == 3200 and w["educationLevels"] == ["SPM", "Degree"]
    pop = read(make_ctx.data, "my.population")["data"]
    assert pop["ageGroups"] == ["0-4", "5-9", "85+"] and pop["ethnicities"][0] == ["overall", "Everyone"]
    lt = read(make_ctx.data, "my.lifetables")["data"]["tables"]
    assert lt["Johor|male"]["ages"] == [0, 1, 5, 80]
    cpi = read(make_ctx.data, "my.cpi")["data"]
    assert cpi["asOf"] == "2026-09" and cpi["overall"] == pytest.approx(0.02) and cpi["groups"]["01"]["label"] == "Food and drinks"


def test_opendosm_percentiles_leave_the_open_ends_out():
    # The real DOSM layout: no minimum for the 1st percentile and no maximum for the 100th.
    rows = pd.DataFrame([{"percentile": p, "variable": v, "income": None if (p, v) in ((1, "minimum"), (100, "maximum")) else p * 100 + (0 if v == "minimum" else 99)}
                         for p in range(1, 101) for v in ("minimum", "maximum", "mean", "median")])
    values, positions = opendosm.thresholds(rows)
    assert positions == list(range(1, 100)) and values[0] == 199 and values[-1] == 9999


def test_opendosm_explains_missing_tables(make_ctx):
    with pytest.raises(PipelineError, match="open.dosm.gov.my/data-catalogue/population_state"):
        opendosm.frame(make_ctx("opendosm"), "population_state")


def test_datagovmy_births_window(make_ctx, read):
    df = pd.DataFrame({"date": ["1999-01-01", "2000-01-01", "2001-01-01", "2000-02-29"], "state": "Malaysia", "births": [5000, 1000, 1200, 900]})
    datagovmy_births.build_from(make_ctx("datagovmy_births"), df)
    d = read(make_ctx.data, "my.births.daily")["data"]
    assert d["byDate"]["01-01"] == 1100 and d["byDate"]["02-29"] == 900


# ---------------------------------------------------------------- Indonesia


def test_bps_ships_the_poverty_line_and_needs_citations(make_ctx, read):
    ctx = make_ctx("bps")
    m = ctx.manual_dir
    m.mkdir(parents=True)
    src = ROOT / "pipeline/manual/bps"
    shutil.copy(src / "poverty_line.json", m / "poverty_line.json")
    shutil.copy(src / "spending_brackets.example.csv", m / "spending_brackets.csv")
    bps.build(ctx)
    env = read(make_ctx.data, "id.bps.poverty_line")
    assert env["data"]["value"] == 669235 and env["data"]["bands"][-1][2] is None
    assert env["citation"]["url"].startswith("https://www.bps.go.id/")
    assert "id.bps.spending" not in ctx.written  # no citation yet

    shutil.copy(src / "citations.example.json", m / "citations.json")
    for name in ("wages_province_job", "wages_age", "cpi_groups"):
        shutil.copy(src / f"{name}.example.csv", m / f"{name}.csv")
    ctx2 = make_ctx("bps")
    bps.build(ctx2)
    assert {"id.bps.spending", "id.bps.wages", "id.bps.cpi"} <= set(ctx2.written)
    sp = read(make_ctx.data, "id.bps.spending")["data"]["provinces"]["Indonesia"]
    assert sp[-1][1] is None and sum(s for *_, s in sp) == pytest.approx(1)
    assert read(make_ctx.data, "id.bps.cpi")["data"]["overall"] == 0.027


def test_cli_gate_refuses_pending_and_unknown_sources():
    sources = {**load_sources(), "future_source": {"licenseCode": "PD", "pipeline": "pending", "todo": "x"}}
    with pytest.raises(PipelineError, match="isn't written yet"):
        gate("future_source", sources)
    with pytest.raises(PipelineError, match="Unknown source"):
        gate("nope", sources)
    gate("bps", sources)
