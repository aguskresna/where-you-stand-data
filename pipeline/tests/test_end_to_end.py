"""Builds every source from small fake files into one data folder, then runs the web app's own feature
code on the result (needs Node 20+). This is what proves the pipeline writes what the app reads."""

import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from statsapp_pipeline.sources import acs_pums, births_538, bps, datagovmy_births, nhanes, ssa_names, un_wpp, worldbank_pip, worldbank_wdi
from conftest import ROOT
from test_sources import fake_pums, wpp_frames


# The reference web prototype holds the original feature code; skip if it isn't next to the backend.
CHECKER = ROOT.parent / "reference" / "web-prototype" / "scripts" / "check-data.mjs"


@pytest.mark.skipif(shutil.which("node") is None or not CHECKER.exists(), reason="needs Node and reference/web-prototype")
def test_the_app_runs_on_pipeline_output(make_ctx, read, monkeypatch):
    p_raw, h_raw = fake_pums(1500)
    p = acs_pums.recode_people(p_raw, h_raw)
    acs_pums.build_all(make_ctx("census_acs_pums"), p, acs_pums.recode_households(h_raw, p), {}, 2024)

    rng = np.random.default_rng(3)
    n = 900
    demo = pd.DataFrame({"SEQN": range(n), "RIAGENDR": rng.choice([1, 2], n), "RIDAGEYR": rng.integers(18, 81, n), "WTMEC2YR": rng.uniform(1000, 9000, n)})
    exam = pd.DataFrame({"SEQN": range(n), "BMXHT": rng.normal(170, 9, n), "BMXWT": rng.normal(80, 15, n), "BMXWAIST": rng.normal(98, 14, n), "BMXBMI": rng.normal(28, 6, n)})
    nhanes.build_from(make_ctx("nchs_nhanes"), demo, exam)

    names = pd.DataFrame([(nm, s, c, y) for y in range(1990, 2025) for nm, s, c in (("Olivia", "F", 500 + y), ("Liam", "M", 400 + y))], columns=["name", "sex", "count", "year"])
    ssa_names.build_from(make_ctx("ssa_names"), names)

    days = pd.date_range("2000-01-01", "2014-12-31")
    births = pd.DataFrame({"year": days.year, "month": days.month, "date_of_month": days.day, "births": 11000 + (days.dayofyear % 30)})
    births_538.build_from(make_ctx("births_538"), births, births.iloc[:0])

    ind, ages, life = wpp_frames()
    ind = pd.concat([ind, ind[ind["code"] == "IDN"].assign(code="USA", Location="United States of America")])
    ages = pd.concat([ages, ages[ages["code"] == "IDN"].assign(code="USA")])
    life = {k: pd.concat([v, v.assign(code="USA")]) for k, v in life.items()}
    un_wpp.build_from(make_ctx("un_wpp"), ind, ages, life, 2026)
    wpp = read(make_ctx.data, "world.wpp.indicators")["data"]

    pip = pd.DataFrame([{"country_code": iso, "year": 2022, "percentile": q, "avg_welfare": q * f, "quantile": q * f + f / 2}
                        for iso, f in (("IDN", 0.15), ("MYS", 0.4), ("USA", 1.2)) for q in range(1, 101)])
    worldbank_pip.build_from(make_ctx("worldbank_pip"), pip, wpp)

    wdi_ctx = make_ctx("worldbank_wdi")
    values = {"PA.NUS.PRVT.PP": {"USA": 1, "IDN": 4800, "MYS": 1.6}, "FP.CPI.TOTL": {"USA": 120, "IDN": 130, "MYS": 115},
              "NY.GDP.PCAP.PP.KD": {"USA": 70000, "IDN": 14000, "MYS": 33000}, "EG.ELC.ACCS.ZS": {"USA": 100, "IDN": 97, "MYS": 100},
              "IT.NET.USER.ZS": {"USA": 92, "IDN": 66, "MYS": 97, "WLD": 67}}

    def fake(url, params=None):
        if "metadata" in url:
            return {"id": "License_Type", "value": "CC BY-4.0"}
        code = url.split("/indicator/")[1]
        rows = [{"countryiso3code": iso, "date": str(y), "value": v * (1.02 ** (y - 2021) if code == "FP.CPI.TOTL" else 1)}
                for iso, v in values[code].items() for y in range(1990, 2025)]
        return [{"pages": 1}, rows]

    monkeypatch.setattr(wdi_ctx, "fetch_json", fake)
    worldbank_wdi.build(wdi_ctx)

    datagovmy_births.build_from(make_ctx("datagovmy_births"), pd.DataFrame({"date": days.astype(str), "births": 1300 + (days.dayofyear % 20)}))

    bps_ctx = make_ctx("bps")
    bps_ctx.manual_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "pipeline/manual/bps/poverty_line.json", bps_ctx.manual_dir / "poverty_line.json")
    bps.build(bps_ctx)

    for name in ("sources.json",):
        shutil.copy(ROOT / "data" / name, make_ctx.data / name)
    run = subprocess.run(["node", str(CHECKER), str(make_ctx.data)], capture_output=True, text=True, cwd=CHECKER.parent.parent, timeout=300)
    print(run.stdout)
    assert run.returncode == 0, run.stdout + run.stderr
    summary = run.stdout.strip().splitlines()[-1]
    ran = int(summary.split(" ran")[0])
    assert ran >= 40, summary
