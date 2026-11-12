"""cdc_wonder: natality percentiles from a tiny public-use file, and lifetime odds from WONDER-style XML."""

import zipfile

import numpy as np
import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import cdc_wonder as w

RECORD = 1345  # the real files' record length


def record(year=2025, mager=30, restatus=1, lbo=1, dbwt=3300):
    line = [" "] * RECORD
    def put(start, text):
        line[start - 1:start - 1 + len(text)] = list(text)
    put(9, f"{year:04d}")
    put(75, f"{mager:02d}")
    put(104, str(restatus))
    put(179, str(lbo))
    put(504, f"{dbwt:04d}")
    return "".join(line)


def natality_zip(path, n=6000, seed=3):
    rng = np.random.default_rng(seed)
    lines = []
    for i in range(n):
        lines.append(record(mager=int(rng.integers(15, 45)), lbo=int(rng.choice([1, 2, 3, 9])), dbwt=int(rng.integers(500, 5000)) if i % 50 else 9999))
    lines.append(record(mager=12, lbo=1, dbwt=227))
    lines.append(record(mager=50, lbo=2, dbwt=8165))
    lines.append(record(mager=25, restatus=4, dbwt=8100))  # foreign resident: left out
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Nat2025PublicUS.c20260624.r20260922.txt", "\r\n".join(lines) + "\r\n")
    return path


def test_natality_percentiles(make_ctx, read, tmp_path):
    c = w.count_file(natality_zip(tmp_path / "Nat2025us.zip"))
    assert c["year"] == 2025 and c["foreign"] == 1 and c["records"] == 6003
    ctx = make_ctx("cdc_wonder")
    w.natality_from(ctx, c)
    d = read(make_ctx.data, "us.cdc.natality")
    assert d["year"] == 2025
    m = d["data"]["measures"]
    for key in ("birth_weight_g", "mother_age", "first_birth_age"):
        v = m[key]
        assert len(v) == 101 and all(b >= a for a, b in zip(v, v[1:]))
    # The extremes are the 10th-lowest and 10th-highest values, never one baby's weight (227 g, 8165 g here).
    assert 500 <= m["birth_weight_g"][0] < 600 and 4900 < m["birth_weight_g"][100] < 5000  # 9999 (not stated) left out
    assert m["mother_age"][0] == 15 and m["mother_age"][100] == 44
    assert m["first_birth_age"][100] == 44
    assert "6,002 births" in d["note"]


def test_extremes_stand_for_at_least_ten_births():
    counts = np.zeros(100, dtype=np.int64)
    counts[12], counts[20], counts[30], counts[49], counts[50] = 3, 500, 500, 9, 1
    q = w.quantiles_from_counts(counts, 1)
    assert q[0] == 20 and q[100] == 49  # the 3 aged 12 and the 1 aged 50 never show alone


def test_natality_refuses_shifted_fields(make_ctx):
    c = {"year": 2025, "weight": np.zeros(10000, dtype=np.int64), "age": np.zeros(100, dtype=np.int64), "first": np.zeros(100, dtype=np.int64)}
    c["weight"][99] = 5000  # a weight below the guide's 227 g floor
    c["age"][30] = c["first"][30] = 5000
    with pytest.raises(PipelineError, match="field positions"):
        w.natality_from(make_ctx("cdc_wonder"), c)


POP = "340,110,988"


def row(label, deaths, h=1):
    return f'<r><c l="{label}" h="{h}"/><c v="{deaths}"/><c v="{POP}"/><c v="1.0" a="c"><l v="(0.9 - 1.1)"/></c></r>'


def table_xml():
    rows = [row(f"#{lab} (X00)" if not lab.startswith("Motor") else f"{lab} (V02-V04)", f"{(i + 1) * 1000:,}") for i, (_, lab) in enumerate(w.CAUSES_113.values())]
    rows.append(row("#Intentional self-harm (suicide) (*U03,X60-X84,Y87.0)", "49,000"))
    rows[0] = row("#Diseases of heart (I00-I09,I11,I13,I20-I51)", "683,491")
    rows.append(row("#Scarlet fever and erysipelas (A38,A46)", "Suppressed"))
    return '<?xml version="1.0"?><page><data-table show-all-labels="false">' + "".join(rows) + "</data-table></page>"


def year_xml(deaths):
    return (f'<page><data-table><r><c l="2024 "/><c v="{deaths}"/><c v="{POP}"/><c v="0.1" a="c"/></r>'
            f'<r><c c="1"/><c dt="{deaths}"/><c dt="{POP}"/></r></data-table></page>')


def lifetable(year=2024):
    return {"year": year, "demo": False, "data": {"tables": {"B": {"ages": [0], "lx": [100000], "ex": [78.971]}}}}


def test_causes_lifetime_odds(make_ctx, read):
    table = w.parse_rows(table_xml())
    coded = {cid: w.parse_rows(year_xml("325" if cid == "plane" else "Suppressed" if cid == "lightning" else "1,200")) for cid in w.CAUSES_ICD}
    ctx = make_ctx("cdc_wonder")
    w.causes_from(ctx, table, coded, 2024, lifetable())
    d = read(make_ctx.data, "us.cdc.causes")
    c = d["data"]["causes"]
    assert d["year"] == 2024
    assert c["heart"] == {"label": "Heart disease", "oneIn": round(340110988 / 683491 / 78.971)}
    assert c["plane"]["oneIn"] == round(340110988 / 325 / 78.971)
    assert "lightning" not in c  # suppressed by WONDER
    assert not any("self" in v["label"].lower() or "suicide" in v["label"].lower() for v in c.values())
    assert all(set(v) == {"label", "oneIn"} for v in c.values())


def test_causes_need_the_same_year_life_table(make_ctx):
    table = w.parse_rows(table_xml())
    with pytest.raises(PipelineError, match="life table for 2024"):
        w.causes_from(make_ctx("cdc_wonder"), table, {}, 2024, lifetable(2021))


def test_request_xml_carries_the_data_use_agreement():
    x = w.request_xml({"B_1": ["D158.V9"], "F_D158.V2": ["*All*"], "dataset_code": ["D158"]}, B_1="D158.V4", F_D158__V2=["V95", "V96"])
    assert "<name>accept_datause_restrictions</name><value>true</value>" in x
    assert "<name>B_1</name><value>D158.V4</value>" in x and "<value>V95</value><value>V96</value>" in x
    assert "dataset_code" not in x
