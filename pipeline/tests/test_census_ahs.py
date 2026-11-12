"""AHS builder against a tiny national household file in Census's layout (quoted codes)."""

import pandas as pd

from statsapp_pipeline.sources import census_ahs


def fake_households():
    rows = []
    for size in range(1, 10):
        rows.append({"UNITSIZE": f"'{size}'", "TENURE": "'1'", "WEIGHT": 100.0 * size, "INTSTATUS": "'1'"})
        rows.append({"UNITSIZE": f"'{size}'", "TENURE": "'2'", "WEIGHT": 100.0, "INTSTATUS": "'1'"})
    rows.append({"UNITSIZE": "'-9'", "TENURE": "'1'", "WEIGHT": 5000.0, "INTSTATUS": "'1'"})  # size not reported
    rows.append({"UNITSIZE": "'4'", "TENURE": "'-6'", "WEIGHT": 5000.0, "INTSTATUS": "'3'"})  # vacant
    rows.append({"UNITSIZE": "'2'", "TENURE": "'3'", "WEIGHT": 900.0, "INTSTATUS": "'1'"})  # no cash rent: a renter
    return pd.DataFrame(rows)


def test_ahs_shares_of_size_classes(make_ctx, read):
    census_ahs.build_from(make_ctx("census_ahs"), fake_households(), 2023)
    env = read(make_ctx.data, "us.ahs.size")
    d = env["data"]
    assert env["year"] == 2023 and d["unit"] == "sq ft"
    assert [b[0] for b in d["groups"]["all"]] == [0, 500, 750, 1000, 1500, 2000, 2500, 3000, 4000]
    assert d["groups"]["all"][-1][1] is None
    for key in ("all", "owner", "renter"):
        assert len(d["groups"][key]) == 9 and abs(sum(b[2] for b in d["groups"][key]) - 1) < 1e-3
    assert d["groups"]["owner"][0][2] == round(100 / 4500, 4)
    assert d["groups"]["renter"][1][2] == round(1000 / 1800, 4)


def test_ahs_finds_the_newest_puf_version():
    listing = ('href="AHS%202023%20National%20PUF%20v1.0%20CSV.zip" href="AHS%202023%20National%20PUF%20v1.1%20CSV.zip" '
               'href="AHS%202023%20National%20PUF%20v1.1%20Flat%20CSV.zip"')
    assert census_ahs.puf_name(listing, 2023) == "AHS%202023%20National%20PUF%20v1.1%20CSV.zip"
