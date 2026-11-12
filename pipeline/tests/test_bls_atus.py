"""ATUS builder against a tiny Activity summary file in BLS's layout, and the hand-saved file it needs."""

import numpy as np
import pandas as pd
import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import bls_atus

ascending = lambda v: all(b >= a for a, b in zip(v, v[1:]))


def fake_summary(n=600, seed=5):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "TUCASEID": np.arange(n) + 20240101240000,
        "TUFNWGTP": rng.uniform(1e6, 2e7, n),
        "TEAGE": rng.integers(15, 86, n),
        "TESEX": rng.choice([1, 2], n),
        "TUYEAR": 2024,
        "t010101": rng.integers(300, 660, n),
        "t010102": rng.choice([0, 0, 30], n),
        "t050101": rng.choice([0, 480], n),
        "t050201": rng.choice([0, 15], n),
        "t120303": rng.integers(0, 240, n),
        "t120308": rng.choice([0, 60], n),
        "t180501": rng.choice([0, 50], n),
        "t181201": rng.choice([0, 20], n),
    })


def test_atus_sleep_percentiles_and_averages(make_ctx, read):
    df = fake_summary()
    bls_atus.build_from(make_ctx("bls_atus"), df)
    env = read(make_ctx.data, "us.bls.atus")
    d = env["data"]
    assert env["year"] == 2024
    assert set(d["averages"]) == {"sleep", "work", "screens", "travel"}
    w = df["TUFNWGTP"]
    avg = lambda minutes: round((minutes / 60 * w).sum() / w.sum(), 2)
    assert d["averages"]["sleep"] == avg(df["t010101"] + df["t010102"])
    assert d["averages"]["work"] == avg(df["t050101"])  # work-related activities (0502) aren't work
    assert d["averages"]["screens"] == avg(df["t120303"] + df["t120308"])
    assert d["averages"]["travel"] == avg(df["t180501"] + df["t181201"])
    g = d["sleep"]["groups"]
    assert {"*", "18-24", "65+"} <= set(g) and len(g["*"]) == 101 and ascending(g["*"])


def test_atus_uses_only_the_latest_year(make_ctx, read):
    df = pd.concat([fake_summary().assign(TUYEAR=2023, t010101=900), fake_summary()])
    bls_atus.build_from(make_ctx("bls_atus"), df)
    assert read(make_ctx.data, "us.bls.atus")["data"]["averages"]["sleep"] < 13


def test_atus_asks_for_the_hand_saved_file(make_ctx):
    with pytest.raises(PipelineError, match="atussum.zip"):
        bls_atus.build(make_ctx("bls_atus"))
