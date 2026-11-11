"""OEWS builder against a few rows in the all-data file's layout (all_data_M_YYYY.xlsx inside oesmYYall.zip)."""

import io
import zipfile

import pandas as pd

from statsapp_pipeline.sources import bls_oews

HEAD = ["AREA", "AREA_TITLE", "AREA_TYPE", "PRIM_STATE", "NAICS", "NAICS_TITLE", "I_GROUP", "OWN_CODE", "OCC_CODE", "OCC_TITLE",
        "O_GROUP", "TOT_EMP", "EMP_PRSE", "JOBS_1000", "LOC_QUOTIENT", "PCT_TOTAL", "PCT_RPT", "H_MEAN", "A_MEAN", "MEAN_PRSE",
        "H_PCT10", "H_PCT25", "H_MEDIAN", "H_PCT75", "H_PCT90", "A_PCT10", "A_PCT25", "A_MEDIAN", "A_PCT75", "A_PCT90", "ANNUAL", "HOURLY"]


def row(area, title, atype, st, occ, otitle, ogroup, a, own="1235"):
    return [area, title, atype, st, "000000", "Cross-industry", "cross-industry", own, occ, otitle, ogroup, "1000", "1.0", "", "", "", "",
            "30", "62000", "1.0", "15", "18", "24", "31", "40", *a, "", ""]


ROWS = [
    row("99", "U.S.", "1", "US", "00-0000", "All Occupations", "total", ["30000", "37000", "50980", "79000", "120000"]),
    row("99", "U.S.", "1", "US", "13-2011", "Accountants and Auditors", "detailed", ["52000", "65000", "83680", "110000", "140000"]),
    row("99", "U.S.", "1", "US", "29-1215", "Family Medicine Physicians", "detailed", ["90000", "180000", "#", "#", "#"]),
    row("99", "U.S.", "1", "US", "13-2011", "Accountants and Auditors", "detailed", ["1", "2", "3", "4", "5"], own="5"),
    row("99", "U.S.", "1", "US", "13-0000", "Business and Financial Operations Occupations", "major", ["1", "2", "3", "4", "5"]),
    row("06", "California", "2", "CA", "13-2011", "Accountants and Auditors", "detailed", ["60000", "75000", "95000", "125000", "160000"]),
    row("72", "Puerto Rico", "3", "PR", "13-2011", "Accountants and Auditors", "detailed", ["*", "*", "*", "*", "*"]),
    row("31080", "Los Angeles-Long Beach-Anaheim, CA", "4", "CA", "13-2011", "Accountants and Auditors", "detailed", ["1", "2", "3", "4", "5"]),
]


def test_oews_keeps_published_percentiles_for_detailed_occupations(make_ctx, read, tmp_path):
    buf = io.BytesIO()
    pd.DataFrame(ROWS, columns=HEAD).to_excel(buf, index=False)
    zpath = tmp_path / bls_oews.FILE
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("oesm25all/all_data_M_2025.xlsx", buf.getvalue())
    ctx = make_ctx("bls_oews")
    counts = bls_oews.build_from(ctx, bls_oews.read_zip(zpath), 2025)
    d = read(make_ctx.data, "us.bls.oews")
    assert d["year"] == 2025
    data = d["data"]
    assert data["p"] == [10, 25, 50, 75, 90]
    assert data["groups"] == {"13-2011|CA": [60000, 75000, 95000, 125000, 160000], "13-2011|US": [52000, 65000, 83680, 110000, 140000]}
    # Top-coded or unpublished wages are left out, not filled in; metro areas, totals and private-only rows are ignored.
    assert data["occupations"] == {"13-2011": "Accountants and Auditors"}
    assert data["areas"] == {"CA": "California", "PR": "Puerto Rico", "US": "United States"}
    assert counts == {"kept": 2, "left_out": 2}
