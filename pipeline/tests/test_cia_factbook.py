"""CIA World Factbook (archived final edition): the Religions field page-data and the Country Data Codes table."""

import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import cia_factbook

ENTRIES = {
    "United States": "Protestant 46.5%, Roman Catholic 20.8%, Jewish 1.9%, other 1.8%, unaffiliated 22.8%, don't know/refused 0.6% (2014 est.)",
    "Malaysia": "Muslim (official) 63.5%, Buddhist 18.7%, Christian 9.1%, Hindu 6.1%, other (Confucianism, Taoism, other traditional Chinese religions) 0.9%, none/unspecified 1.8% (2020 est.)",
    "Algeria": "Muslim (official; predominantly Sunni) 99%, other (includes Christian, Jewish, Ahmadi Muslim, Shia Muslim, Ibadi Muslim) &lt;1% (2012 est.)",
    "Albania": "Muslim 56.7%, Roman Catholic 10%, unspecified 16.2% (2011 est.)<br><br><strong>note:</strong> all mosques and churches were closed in 1967",
    "Belgium": "Roman Catholic 57.1%, Protestant 2.3%, other Christian, 2.8%, Muslim 6.8%, other 1.7%, atheist 9.1%, nonbeliever/agnostic 20.2% (2018 est.)",
    "South Africa": "Christian 86%, ancestral, tribal, animist, or other traditional African religions 5.4%, Muslim 1.9%, other 1.5%, nothing in particular 5.2% (2015 est.)",
    "Nepal": "Hindu 81.2%, Buddhist 8.2%, Muslim 5.1%, Kirat 3.2%, Christian 1.8%; less than 1%:&nbsp; Prakriti, Bon, Jains, Sikh (2021 est.)",
    "Greece": "Greek Orthodox 81-90%, Muslim 2%, other 3%, none 4-15%, unspecified 1% (2015 est.)",
    "Eritrea": "Eritrean Orthodox, Roman Catholic, Evangelical Lutheran, Sunni Muslim",
    "Kosovo": "Muslim 93.5%, Roman Catholic 1.8%, Orthodox 1.5% (2024 est.)",
    "World": "Christian 31.1%, Muslim 24.9% (2020 est.)",
}
CODES = {"United States": ("USA", "US|USA|840"), "Malaysia": ("MYS", "MY|MYS|458"), "Algeria": ("DZA", "DZ|DZA|012"), "Albania": ("ALB", "AL|ALB|008"),
         "Belgium": ("BEL", "BE|BEL|056"), "South Africa": ("ZAF", "ZA|ZAF|710"), "Nepal": ("NPL", "NP|NPL|524"), "Greece": ("GRC", "GR|GRC|300"),
         "Eritrea": ("ERI", "ER|ERI|232"), "Kosovo": ("XKS", "-")}


def page_data():
    nodes = [{"placeName": k, "formatted": v, "place": {"region": "x"}} for k, v in ENTRIES.items()]
    return {"componentChunkName": "component---src-templates-field-js", "path": "/field/religions/",
            "result": {"data": {"fieldLabel": {"name": "Religions"}, "fields": {"nodes": nodes}}}}


def codes_page(extra=200):
    rows = [(name, genc, iso) for name, (genc, iso) in CODES.items()]
    rows += [(f"Filler {i}", "QQQ", f"QQ|Q{chr(65 + i % 26)}{chr(65 + i // 26)}|999") for i in range(extra)]  # the real table has ~260 rows
    body = "".join(f'<tr class="content-row"><td>{n}</td><td>{g}</td><td>{iso}</td><td>{g}</td><td>.x</td><td>-</td></tr>' for n, g, iso in rows)
    return ('<table class="content-table table-auto"><thead><tr class="header-row"><th>Name</th><th>GENC</th><th>ISO 3166</th><th>Stanag</th>'
            f"<th>Internet</th><th>Comment</th></tr></thead><tbody>{body}</tbody></table>")


def test_parses_shares_and_leaves_out_what_has_no_single_figure(make_ctx, read, monkeypatch):
    monkeypatch.setattr(cia_factbook, "MIN_COUNTRIES", 5)  # the real field parses to ~210 countries
    ctx = make_ctx("cia_factbook")
    cia_factbook.build_from(ctx, page_data(), codes_page())
    d = read(make_ctx.data, "world.factbook.religion")
    assert d["year"] == "2026-01-22" and "February 2026" in d["note"]
    c = d["data"]["countries"]
    assert c["USA"] == {"name": "United States", "year": "2014 est.", "groups": [["Protestant", 46.5], ["Roman Catholic", 20.8], ["Jewish", 1.9], ["other", 1.8],
                                                                                 ["unaffiliated", 22.8], ["don't know/refused", 0.6]]}
    assert c["MYS"]["groups"][0] == ["Muslim (official)", 63.5]
    assert c["DZA"]["groups"] == [["Muslim (official; predominantly Sunni)", 99.0]]  # "<1%" has no single figure
    assert c["ALB"]["groups"][-1] == ["unspecified", 16.2]  # the note is dropped
    assert ["other Christian", 2.8] in c["BEL"]["groups"]  # stray comma before the figure
    assert c["ZAF"]["groups"][1] == ["ancestral, tribal, animist, or other traditional African religions", 5.4]
    assert c["NPL"]["groups"][-1] == ["Christian", 1.8]  # the "less than 1%" list is dropped
    assert not {"GRC", "ERI"} & set(c)  # ranges and names without figures
    assert "XKS" not in c and "World" not in str(c)  # no ISO code


def test_parse_details():
    assert cia_factbook.parse("Roman Catholic, Protestant 20%") is None
    assert cia_factbook.parse("Catholic 90.7%, other 7.1% (2022)") == ([["Catholic", 90.7], ["other", 7.1]], "2022")
    assert cia_factbook.parse("Muslim 99% (official; virtually all Sunni, &lt;0.1% Shia), other 1% (includes Christian); note - Jewish about 3,000 (2020 est.)") == \
        ([["Muslim", 99.0], ["other", 1.0]], "2020 est.")


def test_too_few_countries_is_refused(make_ctx):
    with pytest.raises(PipelineError, match="Only"):
        cia_factbook.build_from(make_ctx("cia_factbook"), page_data(), codes_page())


def test_codes_page_layout_change_is_refused():
    with pytest.raises(PipelineError, match="layout"):
        cia_factbook.iso_codes("<table></table>")
