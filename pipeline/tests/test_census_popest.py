"""Census population estimates against a small file in the layout of nc-est<V>-agesex-res.csv."""

import pandas as pd
import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import census_popest


def agesex(break_total=False):
    rows = []
    for sex in (0, 1, 2):
        for age in list(range(101)) + [999]:
            def pop(year):
                if age == 999:
                    return 101 * base(sex, year)
                return base(sex, year)
            rows.append({"SEX": sex, "AGE": age, "ESTIMATESBASE2020": pop(2020), "POPESTIMATE2020": pop(2020),
                         "POPESTIMATE2024": pop(2024), "POPESTIMATE2025": pop(2025)})
    df = pd.DataFrame(rows)
    if break_total:
        df.loc[(df.SEX == 0) & (df.AGE == 999), "POPESTIMATE2025"] += 1
    return df


def base(sex, year):
    one = 1000 + (year - 2020)
    return {0: 2 * one, 1: one, 2: one}[sex]


def test_census_writes_101_ages_for_the_newest_year(make_ctx, read):
    ctx = make_ctx("census_popest")
    census_popest.build_from(ctx, agesex(), vintage=2025)
    d = read(make_ctx.data, "us.census.pop_age")
    assert d["year"] == 2025 and "Vintage 2025" in d["note"]
    assert len(d["data"]["total"]) == 101 and d["data"]["total"][0] == 2010
    assert d["data"]["M"][100] + d["data"]["F"][100] == d["data"]["total"][100]


def test_census_refuses_ages_that_do_not_add_up(make_ctx):
    with pytest.raises(PipelineError, match="add up"):
        census_popest.build_from(make_ctx("census_popest"), agesex(break_total=True), vintage=2025)


def test_vintage_urls():
    assert census_popest.url_for(2025).endswith("/2020-2025/national/asrh/nc-est2025-agesex-res.csv")
    assert "/2020-2030/" in census_popest.url_for(2030) and "/2030-2031/" in census_popest.url_for(2031)
