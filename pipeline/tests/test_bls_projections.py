"""Employment Projections builder against a trimmed copy of the data.bls.gov occupation table page."""

import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import bls_projections

PAGE = """<html><body><table>
<thead><tr><th>Occupation Title</th><th>Occupation Code</th><th>Employment 2025</th><th>Employment 2035</th>
<th>Employment Change, 2025-2035</th><th>Employment Percent Change, 2025-2035</th>
<th>Occupational Openings, 2025-2035 Annual Average</th><th>Median Annual Wage 2025</th></tr>
<tr id="search_boxes"><td><label>Filter by Title:</label><input name="title"></td><td>&nbsp;</td></tr>
<TR><TD class="cellbordered cellLeft" id="row1" headers="row1 col1">
<a href="/projections/nationalMatrix?queryParams=00-0000&ioType=o">Total, all occupations</a></TD>
<TD headers="row1 col2">00-0000</TD><TD headers="row1 col3">170,280.8</TD><TD headers="row1 col4">176,198.5</TD>
<TD headers="row1 col5">5,917.6</TD><TD headers="row1 col6">3.5</TD><TD headers="row1 col7">17,461.8</TD><TD headers="row1 col8">$50,980</TD></TR>
</thead><tbody>
@ROWS@
</tbody></table></body></html>"""

ROW = """<TR><TD class="cellbordered cellLeft" id="row{i}" headers="row{i} col1">
<a href="/projections/nationalMatrix?queryParams={code}&ioType=o">{title}</a><br>
<a href="#" id=showlay{i} class="showhide" onclick="showHideLayTitle(this.id); return false;"><div> </div>Show/hide Example Job Titles</a>
<p id=lay{i} class="laytitles">* Account Auditor<br/>* Accountant</p></TD>
<TD headers="row{i} col2">{code}</TD><TD headers="row{i} col3">{base}</TD><TD headers="row{i} col4">{proj}</TD>
<TD headers="row{i} col5">0</TD><TD headers="row{i} col6">{pct}</TD><TD headers="row{i} col7">1</TD><TD headers="row{i} col8">83,680</TD>
<TD headers="row{i} col9">Bachelor's degree</TD></TR>"""


def page(n=600):
    rows = [ROW.format(i=2, code="13-2011", title="Accountants and auditors", base="1,595.2", proj="1,674.6", pct="5.0"),
            ROW.format(i=3, code="43-9021", title="Data entry keyers", base="139.0", proj="105.6", pct="-24.0")]
    rows += [ROW.format(i=10 + k, code=f"99-{k:04d}", title=f"Job {k}", base="1.0", proj="1.1", pct="10.0") for k in range(n)]
    return PAGE.replace("@ROWS@", "\n".join(rows))


def test_projections_copy_the_published_table(make_ctx, read):
    ctx = make_ctx("bls_projections")
    bls_projections.build_from(ctx, page())
    d = read(make_ctx.data, "us.bls.projections")
    assert d["year"] == 2025
    data = d["data"]
    assert (data["baseYear"], data["projYear"]) == (2025, 2035)
    assert data["all"] == {"change": 0.035}
    assert data["occupations"]["13-2011"] == {"title": "Accountants and auditors", "base": 1595200, "proj": 1674600, "change": 0.05}
    assert data["occupations"]["43-9021"]["change"] == -0.24
    assert "00-0000" not in data["occupations"]


def test_projections_refuse_a_changed_layout(make_ctx):
    with pytest.raises(PipelineError):
        bls_projections.build_from(make_ctx("bls_projections"), page(n=3))
