"""NSFG builder against tiny respondent files in NCHS's layout, and the Kaplan-Meier estimate itself."""

import numpy as np
import pandas as pd

from statsapp_pipeline.sources import nchs_nsfg


def test_survival_matches_a_hand_worked_kaplan_meier():
    # durations in years; e=1 disrupted, e=0 censored (intact at interview, or widowed)
    t = [2, 5, 5, 8, 12, 12, 15, 25, 30, 21]
    e = [1, 1, 0, 1, 1, 0, 0, 1, 0, 0]
    s = nchs_nsfg.survival(t, e, [1] * 10, [10, 20])
    # at risk: 10 at year 2, 9 at year 5 (the marriage censored at 5 is still at risk), 7 at year 8
    expect10 = (1 - 1 / 10) * (1 - 1 / 9) * (1 - 1 / 7)
    assert abs(s[10][0] - expect10) < 1e-12 and s[10][1] == 6
    assert abs(s[20][0] - expect10 * (1 - 1 / 6)) < 1e-12 and s[20][1] == 3


def fake_respondents(n=1500, seed=6):
    rng = np.random.default_rng(seed)
    age = rng.integers(15, 50, n)
    married = (rng.random(n) < 0.6) & (age >= 20)
    fmar1age = np.where(married, np.minimum(age, rng.integers(16, 40, n)), np.nan)
    mardat = (2022 - age) + fmar1age
    ended = married & (rng.random(n) < 0.35)
    dis = np.where(ended, np.minimum(2022, mardat + rng.integers(0, 15, n)), np.nan)
    return pd.DataFrame({
        "AGE_R": age, "FMARNO": np.where(married, 1, 0), "FMAR1AGE": fmar1age,
        "MARDAT01": mardat, "MARDIS01": dis, "MAREND01": np.where(ended, rng.choice([1, 2, 3], n), np.nan),
        "HIEDUC": rng.integers(1, 12, n), "CMINTVW": 1476, "WGT2022_2023": rng.uniform(5000, 40000, n),
        "sex": rng.choice(["F", "M"], n),
    })


def test_nsfg_shares_by_age_at_marriage_and_education(make_ctx, read):
    nchs_nsfg.build_from(make_ctx("nchs_nsfg", min_records=20), fake_respondents(), "2022-2023")
    env = read(make_ctx.data, "us.nsfg.marriage")
    g = env["data"]["groups"]
    assert env["year"] == "2022-2023"
    assert "*|*" in g and "20-24|*" in g
    for key, v in g.items():
        a, edu = key.split("|")
        assert a in ("*", "<20", "20-24", "25-29", "30+") and edu in ("*", "0", "1", "2", "3", "4")
        assert 0 < v["y10"] <= 1 and (v["y20"] is None or v["y20"] <= v["y10"])
    assert g["30+|*"]["y20"] is None  # nobody aged 15-49 is 20 years into a marriage begun at 30


def test_nsfg_leaves_out_unknown_years_and_censors_widowhood():
    df = pd.DataFrame({"AGE_R": [40, 40, 40], "FMARNO": [1, 1, 1], "FMAR1AGE": [25, 25, 25], "MARDAT01": [2008, 9997, 2008],
                       "MARDIS01": [2015, np.nan, 2015], "MAREND01": [3, np.nan, 1], "HIEDUC": [8, 8, 4], "CMINTVW": [1476] * 3,
                       "WGT2022_2023": [1.0] * 3, "sex": ["F", "M", "F"]})
    d = nchs_nsfg.first_marriages(df)
    assert list(d["t"]) == [7, 7] and list(d["e"]) == [0, 1]
    assert list(d["edu"]) == ["3", "1"]
