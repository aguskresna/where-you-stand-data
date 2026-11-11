"""FHFA builder against the quarterly all-transactions files' layout (no header: place, year, quarter, index)."""

import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import fhfa_hpi


def write(path, places, now=200.0):
    lines = []
    for p in places:
        lines += [f"{p},2016,1,99.0", f"{p},2016,2,100.00", f"{p},2026,1,190.0", f"{p},2026,2,{300.0 if p == 'CA' else now}"]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_hpi_yearly_growth_over_ten_years(make_ctx, read, tmp_path):
    st = write(tmp_path / "hpi_at_state.csv", sorted(fhfa_hpi.STATES))
    us = write(tmp_path / "hpi_at_us_and_census.csv", ["USA", "DV_PAC"], now=150.0)
    ctx = make_ctx("fhfa_hpi")
    fhfa_hpi.build_from(ctx, fhfa_hpi.read(st), fhfa_hpi.read(us))
    d = read(make_ctx.data, "us.fhfa.hpi")
    assert d["year"] == 2026
    s = d["data"]["states"]
    assert s["TX"] == round(2 ** 0.1 - 1, 4) and s["CA"] == round(3 ** 0.1 - 1, 4) and s["*"] == round(1.5 ** 0.1 - 1, 4)
    assert len(s) == 52 and "DV_PAC" not in s


def test_hpi_needs_every_state(make_ctx, tmp_path):
    st = write(tmp_path / "hpi_at_state.csv", ["CA", "TX"])
    us = write(tmp_path / "hpi_at_us_and_census.csv", ["USA"])
    with pytest.raises(PipelineError):
        fhfa_hpi.build_from(make_ctx("fhfa_hpi"), fhfa_hpi.read(st), fhfa_hpi.read(us))
