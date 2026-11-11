"""RPP builder against a SARPP.zip in BEA's layout."""

import zipfile

from statsapp_pipeline.sources import bea_rpp

HEAD = "GeoFIPS,GeoName,Region,TableName,LineCode,IndustryClassification,Description,Unit,2023,2024\n"
NOTES = '"Note: See the included footnote file."\n"SARPP: Regional price parities by state "\n"U.S. Bureau of Economic Analysis"\n'


def test_rpp_keeps_all_items_for_states_and_dc(make_ctx, read, tmp_path):
    lines = [' "00000","United States", ,SARPP,1,"...","RPPs: All items ","Index",100.000,100.000\n']
    for fips, usps in bea_rpp.FIPS_USPS.items():
        v = "110.720" if usps == "CA" else "95.500"
        lines.append(f' "{fips}000","State {usps}",8,SARPP,1,"...","RPPs: All items ","Index",99.000,{v}\n')
        lines.append(f' "{fips}000","State {usps}",8,SARPP,3,"..."," RPPs: Services: Housing ","Index",120.000,130.000\n')
    zpath = tmp_path / "SARPP.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("SARPP_STATE_2008_2024.csv", HEAD + "".join(lines) + NOTES)
        z.writestr("SARPP__Footnotes.html", "<html></html>")
    ctx = make_ctx("bea_rpp")
    bea_rpp.build_from(ctx, bea_rpp.read_zip(zpath))
    d = read(make_ctx.data, "us.bea.rpp")
    assert d["year"] == 2024
    states = d["data"]["states"]
    assert len(states) == 51 and states["CA"] == 110.72 and states["DC"] == 95.5
