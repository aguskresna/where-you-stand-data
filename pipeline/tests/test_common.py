import json

import numpy as np
import pandas as pd
import pytest

from statsapp_pipeline.common import AGE_BANDS, PipelineError, band_of, by_groups, clean, weighted_median, weighted_quantiles, weighted_share


def test_weighted_quantiles_match_plain_percentiles_with_equal_weights():
    v = np.arange(1001)
    q = weighted_quantiles(v, np.ones_like(v), digits=1)
    assert len(q) == 101
    assert q[50] == pytest.approx(500, abs=1)
    assert q[0] == 0 and q[100] == 1000
    assert all(b >= a for a, b in zip(q, q[1:]))


def test_weights_shift_the_quantiles():
    q = weighted_quantiles([1, 2], [1, 3], n=3, digits=3)
    assert q[1] == pytest.approx(1.75, abs=1e-9)
    assert weighted_median([10, 20, 30], [1, 1, 10]) == pytest.approx(28.18, abs=0.01)
    assert weighted_share([True, False], [3, 1]) == 0.75
    with pytest.raises(PipelineError):
        weighted_quantiles([np.nan], [1])


def test_band_of():
    assert list(band_of([18, 24, 25, 64.5, 65, 90, 17], AGE_BANDS)) == ["18-24", "18-24", "25-34", "", "65+", "65+", ""]
    assert list(band_of([34, 35, 80], ["<35", "35-44", "75+"])) == ["<35", "35-44", "75+"]


def test_by_groups_adds_everyone_rows_and_drops_small_groups():
    df = pd.DataFrame({"sex": ["M", "M", "F", "F", "F"], "state": ["CA", "CA", "CA", "TX", "TX"], "x": [1, 2, 3, 4, 5]})
    out = by_groups(df, {"sex": ["M", "F"], "state": ["CA", "TX"]}, lambda r: int(r["x"].sum()), min_records=2)
    assert out["*|*"] == 15
    assert out["M|CA"] == 3
    assert "F|CA" not in out
    assert out["F|*"] == 12
    assert out["*|TX"] == 9


def test_clean_makes_json_safe():
    assert clean({"a": np.float64(np.nan), "b": np.int64(3), "c": [np.inf, 1.5]}) == {"a": None, "b": 3, "c": [None, 1.5]}


def test_write_records_envelope_and_manifest(make_ctx, read):
    ctx = make_ctx("bps")
    ctx.write("id.bps.cpi", {"asOf": "2026-09", "overall": 0.02, "groups": {}}, year=2026, citation={"title": "t", "accessed": "2026-11-10", "url": "u"})
    env = read(make_ctx.data, "id.bps.cpi")
    assert env["id"] == "id.bps.cpi" and env["demo"] is False and env["citation"]["title"] == "t"
    manifest = json.loads((make_ctx.data / "manifest.json").read_text())
    assert manifest["datasets"]["id.bps.cpi"]["year"] == 2026
    with pytest.raises(PipelineError):
        ctx.write("us.acs.income_q", {}, year=2024)  # not from this source


def test_sharded_datasets_list_their_shards(make_ctx, read):
    ctx = make_ctx("ssa_names")
    with pytest.raises(PipelineError):
        ctx.write("us.ssa.names", {"names": {}}, year=2024)
    ctx.write("us.ssa.names", {"names": {}}, year=2024, shard="ab")
    ctx.write("us.ssa.names", {"names": {}}, year=2024, shard="ol")
    ctx.finish_shards("us.ssa.names", year=2024)
    manifest = json.loads((make_ctx.data / "manifest.json").read_text())
    assert manifest["datasets"]["us.ssa.names"]["shards"] == ["ab", "ol"]
    assert read(make_ctx.data, "us.ssa.names", "ol")["data"] == {"names": {}}


def test_manual_files_explain_where_to_put_them(make_ctx):
    ctx = make_ctx("un_wpp")
    with pytest.raises(PipelineError, match="Missing .*un_wpp/x.csv. Download it"):
        ctx.manual("x.csv", "Download it from the UN.")
    with pytest.raises(PipelineError, match="downloads are off"):
        ctx.download("https://example.org/file.csv")


def test_rewriting_the_same_data_keeps_the_file_byte_for_byte(make_ctx, read):
    first = make_ctx("bps")
    first.write("id.bps.cpi", {"asOf": "2026-09", "overall": 0.02, "groups": {}}, year=2026)
    path = make_ctx.data / json.loads((make_ctx.data / "contract.json").read_text())["datasets"]["id.bps.cpi"]["file"]
    before, manifest_before = path.read_bytes(), (make_ctx.data / "manifest.json").read_bytes()
    assert first.changed == ["id.bps.cpi"]

    again = make_ctx("bps")
    again.write("id.bps.cpi", {"asOf": "2026-09", "overall": 0.02, "groups": {}}, year=2026)
    assert path.read_bytes() == before and (make_ctx.data / "manifest.json").read_bytes() == manifest_before
    assert again.changed == [] and again.written == ["id.bps.cpi"]

    newer = make_ctx("bps")
    newer.write("id.bps.cpi", {"asOf": "2026-10", "overall": 0.03, "groups": {}}, year=2026)
    assert newer.changed == ["id.bps.cpi"] and read(make_ctx.data, "id.bps.cpi")["data"]["asOf"] == "2026-10"


def test_a_web_page_is_not_a_data_file():
    from statsapp_pipeline.common import _is_html_instead_of_file

    assert _is_html_instead_of_file("csv_pus.zip", {"Content-Type": "text/html; charset=utf-8"})
    assert not _is_html_instead_of_file("csv_pus.zip", {"Content-Type": "application/zip"})
    assert not _is_html_instead_of_file("release.html", {"Content-Type": "text/html"})


def test_get_retrying_tries_again_after_a_timeout_and_a_5xx(monkeypatch):
    import requests

    from statsapp_pipeline import common

    answers = [requests.Timeout("slow"), type("R", (), {"status_code": 503})(), type("R", (), {"status_code": 200})()]
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert common._get_retrying("https://x.example/a", timeout=1).status_code == 200
    assert len(calls) == 3


def test_get_retrying_gives_up_after_the_last_attempt(monkeypatch):
    import requests

    from statsapp_pipeline import common

    def always_slow(url, **kwargs):
        raise requests.Timeout("slow")

    monkeypatch.setattr(requests, "get", always_slow)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(requests.Timeout):
        common._get_retrying("https://x.example/a", attempts=3)
