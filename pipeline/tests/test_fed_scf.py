"""SCF builder against a tiny summary extract in the Fed's layout (five implicate rows per family)."""

import numpy as np
import pandas as pd
import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import fed_scf

ascending = lambda v: all(b >= a for a, b in zip(v, v[1:]))


def fake_extract(families=120, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for yy1 in range(1, families + 1):
        age = int(rng.integers(20, 90))
        for imp in range(1, 6):
            debts = {"MRTHEL": float(rng.choice([0, 150000])), "EDN_INST": float(rng.choice([0, 0, 20000])), "VEH_INST": float(rng.choice([0, 15000])),
                     "CCBAL": float(rng.choice([0, 2500])), "RESDBT": 0.0, "OTHLOC": float(rng.choice([0, 1000])), "OTH_INST": 0.0, "ODEBT": float(rng.choice([0, 500]))}
            rows.append({"YY1": yy1, "Y1": yy1 * 10 + imp, "WGT": float(rng.uniform(500, 30000)), "AGE": age,
                         "NETWORTH": float(rng.normal(300000, 400000)), "RETQLIQ": float(rng.choice([0, 0, 50000, 200000])),
                         "DEBT": sum(debts.values()), **debts})
    return pd.DataFrame(rows)


def test_scf_writes_the_shape_the_app_reads(make_ctx, read):
    ctx = make_ctx("fed_scf", min_records=10)
    fed_scf.build_from(ctx, fake_extract(), 2025)
    env = read(make_ctx.data, "us.fed.scf")
    d = env["data"]
    assert env["year"] == 2025
    assert d["bands"] == ["<35", "35-44", "45-54", "55-64", "65-74", "75+"]
    nw = d["networth"]["groups"]
    assert len(nw["*"]) == 101 and ascending(nw["*"])
    assert len(d["retirement"]["groups"]["*"]) == 101
    assert 0 < d["debt"]["total"]["holding"]["*"] <= 1
    assert set(d["debt"]["types"]) == {"mortgage", "education", "vehicle", "card", "other"}
    edu = d["debt"]["types"]["education"]
    assert edu["label"] and 0 < edu["holding"]["*"] < 1
    assert min(edu["groups"]["*"]) > 0  # debt percentiles count only families that hold that debt


def test_scf_counts_families_not_implicate_rows(make_ctx, read):
    # 15 families make 75 rows: enough rows for a 20-record minimum, but not enough families.
    fed_scf.build_from(make_ctx("fed_scf", min_records=20), fake_extract(families=15), 2025)
    assert read(make_ctx.data, "us.fed.scf")["data"]["networth"]["groups"] == {}
    fed_scf.build_from(make_ctx("fed_scf", min_records=20), fake_extract(families=30), 2025)
    groups = read(make_ctx.data, "us.fed.scf")["data"]["networth"]["groups"]
    assert list(groups) == ["*"]  # no age band has 20 families


def test_scf_refuses_debt_types_that_dont_add_up(make_ctx):
    df = fake_extract(families=20)
    df["DEBT"] += 1000
    with pytest.raises(PipelineError):
        fed_scf.build_from(make_ctx("fed_scf"), df, 2025)
