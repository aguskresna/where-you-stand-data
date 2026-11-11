"""CPI builder against BLS API v1 responses and a relative importance table in the published layout."""

import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import bls_cpi

REL = """<html><body><table>
<thead><tr><th>Indent Level</th><th>Expenditure category</th><th>Relative importance, CPI-U, December 2025</th><th>Relative importance, CPI-W, December 2025</th></tr></thead>
<tbody>
<tr><td>0</td><td>All items</td><td>100.000</td><td>100.000</td></tr>
<tr><td>1</td><td>Food and beverages</td><td>14.000</td><td>15.000</td></tr>
<tr><td>2</td><td>Food</td><td>13.000</td><td>14.000</td></tr>
<tr><td>1</td><td>Housing</td><td>44.500</td><td>42.000</td></tr>
<tr><td>2</td><td>Shelter</td><td>35.000</td><td>33.000</td></tr>
<tr><td>1</td><td>Apparel</td><td>2.500</td><td>2.600</td></tr>
<tr><td>1</td><td>Transportation</td><td>16.000</td><td>18.000</td></tr>
<tr><td>1</td><td>Medical care</td><td>8.000</td><td>7.000</td></tr>
<tr><td>1</td><td>Recreation</td><td>5.500</td><td>5.400</td></tr>
<tr><td>1</td><td>Education and communication</td><td>6.000</td><td>6.500</td></tr>
<tr><td>1</td><td>Other goods and services</td><td>3.500</td><td>3.500</td></tr>
<tr><td>2</td><td>Personal care</td><td>2.500</td><td>2.500</td></tr>
</tbody></table></body></html>"""


def api(values):
    """A BLS API v1 'data' list: {(year, month): value or '-'} plus an annual average row."""
    rows = [{"year": "2025", "period": "M13", "periodName": "Annual", "value": "321.9", "footnotes": [{}]}]
    for (y, m), v in values.items():
        rows.append({"year": str(y), "period": f"M{m:02d}", "periodName": "", "value": v, "footnotes": [{}]})
    return rows


def series():
    out = {}
    for k, code in enumerate(["SA0", *bls_cpi.GROUPS]):
        base = 100.0 + k
        # October 2025 wasn't published, so October 2026 has no 12-month change: September 2026 is used.
        out[code] = bls_cpi.monthly(api({(2025, 9): str(base), (2025, 10): "-", (2026, 9): str(round(base * 1.037, 3)), (2026, 10): str(base * 1.05)}))
    return out


def test_cpi_uses_the_latest_month_with_a_12_month_change_and_the_weights(make_ctx, read, tmp_path):
    rel = tmp_path / "relative-importance-2025.htm"
    rel.write_text(REL, encoding="utf-8")
    weights = bls_cpi.weights_from(bls_cpi.table_rows(rel))
    assert weights["SAH"] == 0.445 and abs(sum(weights.values()) - 1) < 1e-9
    ctx = make_ctx("bls_cpi")
    bls_cpi.build_from(ctx, series(), weights)
    d = read(make_ctx.data, "us.bls.cpi")
    data = d["data"]
    assert data["asOf"] == "2026-09" and d["year"] == 2026
    assert data["overall"] == 0.037
    assert data["groups"]["SAF"] == {"label": "Food and beverages", "change": 0.037, "weight": 0.14}
    assert list(data["groups"]) == list(bls_cpi.GROUPS)


def test_cpi_builds_without_weights_when_the_table_isnt_saved(make_ctx, read):
    bls_cpi.build_from(make_ctx("bls_cpi"), series(), None)
    g = read(make_ctx.data, "us.bls.cpi")["data"]["groups"]
    assert all("weight" not in v for v in g.values())


def test_cpi_weights_must_add_up():
    rows = [["All items", "100.0"], *[[label, "10.0"] for label in bls_cpi.GROUPS.values()]]
    with pytest.raises(PipelineError):
        bls_cpi.weights_from(rows)
