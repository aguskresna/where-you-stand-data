"""NCHS life tables against small Excel files in the layout of the NVSR tables on ftp.cdc.gov."""

import openpyxl
import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import nchs_lifetables as lt

HEAD = ["Age (years)", "Probability of dying between ages x and x + 1", "Number surviving to age x", "Number dying between ages x and x + 1",
        "Person-years lived between ages x and x + 1", "Total number of person-years lived above age x", "Expectation of life at age x"]


def life_xlsx(path, title, e0, dash="–", last="100 and over", extra_cols=0):
    """A complete life table sheet: title, two header rows, ages 0-1 ... 99-100, '100 and over', a SOURCE line."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([title] + [None] * (6 + extra_cols))
    ws.append(HEAD + [None] * extra_cols)
    ws.append([None, "qx", "lx", "dx", "Lx", "Tx", "ex"] + [None] * extra_cols)
    lx = 100000.0
    for a in range(101):
        label = last if a == 100 else f"{a}{dash}{a + 1}"
        q = 1.0 if a == 100 else min(0.0005 * 1.09 ** a, 0.9)
        ex = max(e0 - a * 0.8, 2.2)
        ws.append([label, q, lx, lx * q, lx, lx * ex, ex] + [None] * extra_cols)
        lx = lx * (1 - q)
    ws.append(["SOURCE: National Center for Health Statistics, National Vital Statistics System, mortality data file."] + [None] * 6)
    wb.save(path)
    return path


def us_tables(tmp_path, year=2024):
    return {
        "B": life_xlsx(tmp_path / "Table01.xlsx", f"Table 1. Life table for the total population: United States, {year}", 78.97103118896484, dash="-"),
        "M": life_xlsx(tmp_path / "Table02.xlsx", f"Table 2. Life table for males: United States, {year}", 76.52825164794922, dash="-"),
        "F": life_xlsx(tmp_path / "Table03.xlsx", f"Table 3. Life table for females: United States, {year}", 81.44568634033203, dash="-"),
    }


def state_tables(tmp_path):
    """One set of files reused for every state: the builder checks the sex in each title, not the state name."""
    files = {
        "B": life_xlsx(tmp_path / "CA1.xlsx", "Table CA–1. Life table for total population: California, 2022", 79.33352661132812, last="100 and older", extra_cols=3),
        "M": life_xlsx(tmp_path / "CA2.xlsx", "Table CA–2. Life table for males: California, 2022", 76.7, last="100 and older", extra_cols=3),
        "F": life_xlsx(tmp_path / "CA3.xlsx", "Table CA–3. Life table for females: California, 2022", 82.1, last="100 and older", extra_cols=3),
    }
    return {st: dict(files) for st in lt.STATES}


def test_lifetables_build_the_shapes_the_app_reads(make_ctx, read, tmp_path):
    ctx = make_ctx("nchs_lifetables")
    lt.build_from(ctx, us_tables(tmp_path), state_tables(tmp_path), us_report="75-05", state_report="74-12")

    d = read(make_ctx.data, "us.nchs.lifetable")
    assert d["year"] == 2024 and "NVSR vol. 75, no. 5" in d["note"]
    for s in "BMF":
        t = d["data"]["tables"][s]
        assert t["ages"] == list(range(101)) and len(t["lx"]) == 101 and len(t["ex"]) == 101
        assert t["lx"][0] == 100000 and all(b <= a for a, b in zip(t["lx"], t["lx"][1:]))
    assert d["data"]["tables"]["B"]["ex"][0] == 78.971
    assert d["data"]["tables"]["F"]["ex"][0] == 81.446

    e = read(make_ctx.data, "us.nchs.state_e0")
    assert e["year"] == 2022 and len(e["data"]["states"]) == 51
    assert e["data"]["states"]["CA"] == {"B": 79.334, "M": 76.7, "F": 82.1}


def test_a_swapped_table_is_refused(make_ctx, tmp_path):
    us = us_tables(tmp_path)
    us["M"], us["F"] = us["F"], us["M"]
    with pytest.raises(PipelineError, match="males"):
        lt.build_from(make_ctx("nchs_lifetables"), us, state_tables(tmp_path))


def test_missing_states_are_refused(make_ctx, tmp_path):
    states = state_tables(tmp_path)
    del states["WY"]
    with pytest.raises(PipelineError, match="50 states"):
        lt.build_from(make_ctx("nchs_lifetables"), us_tables(tmp_path), states)


def test_report_folders_sort_newest_first():
    html = '<A HREF="/pub/Health_Statistics/NCHS/Publications/NVSR/68_12/">68_12</A> <A HREF="/pub/Health_Statistics/NCHS/Publications/NVSR/75-1/">' \
           '<A HREF="/pub/Health_Statistics/NCHS/Publications/NVSR/75-05/"> <A HREF="/pub/Health_Statistics/NCHS/Publications/NVSR/74-12/">'
    assert lt.report_folders(html) == ["75-05", "75-1", "74-12", "68_12"]
    files = '<A HREF="/pub/Health_Statistics/NCHS/Publications/NVSR/75-05/Table01.xlsx">Table01.xlsx</A>'
    assert lt.folder_files(files) == ["Table01.xlsx"]
