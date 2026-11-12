"""NHIS builder against a tiny Sample Adult file in NCHS's layout."""

import numpy as np
import pandas as pd

from statsapp_pipeline.sources import nchs_nhis


def fake_adults(n=800, seed=4):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "SEX_A": rng.choice([1, 2, 1, 2, 9], n),
        "AGEP_A": rng.choice(list(range(18, 86)) + [97], n),
        "ORIENT_A": rng.choice([1, 2, 2, 2, 2, 2, 2, 3, 4, 5, 7, 8], n),
        "SMKCIGST_A": rng.choice([1, 2, 3, 4, 4, 5, 9], n),
        "WTFA_A": rng.uniform(2000, 20000, n),
        "SRVY_YR": 2025,
    })


def test_nhis_shares_by_sex_and_band(make_ctx, read):
    nchs_nhis.build_from(make_ctx("nchs_nhis"), fake_adults(), 2025)
    env = read(make_ctx.data, "us.nhis.traits")
    g = env["data"]["groups"]
    assert env["year"] == 2025
    assert {"*|*", "F|*", "M|*", "F|25-34", "*|65+"} <= set(g)
    assert all(k.split("|")[0] in ("*", "F", "M") for k in g)
    for v in g.values():
        assert set(v) == {"straight", "gay", "bisexual", "nonsmoker"}
        assert v["straight"] + v["gay"] + v["bisexual"] < 1  # "something else" and "don't know" make the rest
        assert 0 < v["nonsmoker"] < 1


def test_nhis_leaves_out_refusals_and_unknown_smoking(make_ctx, read):
    df = pd.DataFrame({"SEX_A": [1] * 4, "AGEP_A": [30] * 4, "ORIENT_A": [2, 1, 7, 8], "SMKCIGST_A": [4, 1, 5, 9], "WTFA_A": [1.0] * 4})
    nchs_nhis.build_from(make_ctx("nchs_nhis"), df, 2025)
    v = read(make_ctx.data, "us.nhis.traits")["data"]["groups"]["M|25-34"]
    assert v == {"straight": 0.5, "gay": 0.5, "bisexual": 0.0, "nonsmoker": 0.5}


def test_nhis_drops_small_groups(make_ctx, read):
    nchs_nhis.build_from(make_ctx("nchs_nhis", min_records=100), fake_adults(n=400), 2025)
    g = read(make_ctx.data, "us.nhis.traits")["data"]["groups"]
    assert "*|*" in g and "F|18-24" not in g
