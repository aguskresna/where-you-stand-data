"""The question catalog, publishing the site, and the daily change check."""

import json
import shutil

import pytest

from statsapp_pipeline import publish, questions, update
from statsapp_pipeline.common import Context, PipelineError
from statsapp_pipeline.regions import ID_PROVINCES, MY_STATES, US_STATES
from conftest import ROOT

QDIR = ROOT / "questions"


def contract():
    return json.loads((ROOT / "data" / "contract.json").read_text())


def test_the_shipped_catalog_is_valid():
    catalog = questions.load(QDIR)
    assert questions.validate(catalog, contract()) == []
    assert len(catalog["questions"]) >= 16
    # "Time left with your parents" was left out on purpose by the owner.
    assert not any("time left with" in q["title"].lower() for q in catalog["questions"])


def test_option_lists_match_the_builders_place_codes():
    lists = questions.load(QDIR)["lists"]
    assert [c for c, _ in lists["us_states_any"][1:]] == [c for c, _, _ in US_STATES]
    assert [c for c, _ in lists["my_states_any"][1:]] == MY_STATES
    assert [c for c, _ in lists["id_provinces_any"][1:]] == ID_PROVINCES


def test_validation_catches_mistakes():
    catalog = questions.load(QDIR)
    q = json.loads(json.dumps(catalog["questions"][0]))
    q["id"] = "us-broken"
    q["kind"] = "nope"
    q["datasets"] = ["no.such"]
    q["inputs"][1]["options"] = "@missing"
    q["params"]["path"] = ["groups", "{nobody}"]
    catalog["questions"].append(q)
    problems = "\n".join(questions.validate(catalog, contract()))
    for expected in ("unknown kind nope", "unknown dataset no.such", "unknown list @missing", "unknown input {nobody}"):
        assert expected in problems


def test_only_questions_with_built_data_are_visible():
    catalog = questions.load(QDIR)
    shown = questions.visible(catalog, {"datasets": {"id.bps.poverty_line": {}}})
    assert [q["id"] for q in shown["questions"]] == ["id-kelas-sosial"]
    assert [m["id"] for m in shown["modes"]] == ["id"]
    assert shown["kinds"] == {"class_by_multiple": 1}


def test_publish_writes_hashed_files_and_an_index(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    site = tmp_path / "site"
    index = publish.publish(site, data_dir=data, qdir=QDIR)
    entry = index["datasets"]["id.bps.poverty_line"]
    assert (site / entry["path"]).exists() and entry["path"].startswith("files/id.bps.poverty_line.")
    body = (site / entry["path"]).read_bytes()
    import hashlib

    assert hashlib.sha256(body).hexdigest() == entry["sha256"] and len(body) == entry["bytes"]
    catalog = json.loads((site / index["catalog"]["path"]).read_text())
    # Every published question has its data built; kelas sosial's (the poverty line) always is.
    assert "id-kelas-sosial" in [q["id"] for q in catalog["questions"]]
    built = set(index["datasets"])
    assert all(set(q["datasets"]) <= built for q in catalog["questions"])
    assert "lists" in catalog and "topics" in catalog
    sources = json.loads((site / index["sources"]["path"]).read_text())
    assert "bps" in sources and all(s["licenseUrl"] for s in sources.values())
    assert "max-age=300" in (site / "_headers").read_text()

    app = tmp_path / "app"
    copied = publish.bundle(site, app)
    unsharded = [d for d in index["datasets"].values() if "shards" not in d]
    assert (app / "index.json").exists() and len(copied) == 3 + len(unsharded) - 1


def test_publish_includes_every_shard(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    for shard in ("IDN", "USA"):
        (data / "world" / "lifetable").mkdir(parents=True, exist_ok=True)
        (data / "world" / "lifetable" / f"{shard}.json").write_text(json.dumps({"id": "world.wpp.lifetable", "data": {"tables": {}}}))
    for did, file in (("world.wpp.indicators", "world/wpp_indicators.json"),):
        (data / file).write_text(json.dumps({"id": did, "data": {"countries": {}}}))
    m = json.loads((data / "manifest.json").read_text())
    m["datasets"]["world.wpp.lifetable"] = {"shards": ["IDN", "USA"], "year": 2026}
    m["datasets"]["world.wpp.indicators"] = {"year": 2024}
    (data / "manifest.json").write_text(json.dumps(m))
    index = publish.publish(tmp_path / "site", data_dir=data, qdir=QDIR)
    assert set(index["datasets"]["world.wpp.lifetable"]["shards"]) == {"IDN", "USA"}
    copied = publish.bundle(tmp_path / "site", tmp_path / "app")
    assert not any("~" in c for c in copied)  # shards download on demand


def test_update_skips_unchanged_sources_and_rebuilds_changed_ones(make_ctx, monkeypatch, tmp_path):
    calls = []
    heads = {"etag": "a"}

    class Fake:
        WATCH = ["https://example.org/data.zip"]

        @staticmethod
        def build(ctx):
            calls.append(ctx.source_id)
            ctx.write("us.births.daily", {"years": [2000, 2001], "byDate": {}}, year=2001)

    monkeypatch.setitem(update.BUILDERS, "births_538", Fake)
    monkeypatch.setattr(update, "load_contract", lambda: json.loads((make_ctx.data / "contract.json").read_text()))
    monkeypatch.setattr(update, "load_sources", lambda: json.loads((make_ctx.data / "sources.json").read_text())["sources"])

    def ctx_for(sid):
        ctx = make_ctx(sid)
        monkeypatch.setattr(ctx, "head", lambda url: f"200 {heads['etag']}")
        return ctx

    state = tmp_path / "state.json"
    s1 = update.run(["births_538"], state_file=state, make_ctx=ctx_for, log=lambda *_: None)
    s2 = update.run(["births_538"], state_file=state, make_ctx=ctx_for, log=lambda *_: None)
    heads["etag"] = "b"
    s3 = update.run(["births_538"], state_file=state, make_ctx=ctx_for, log=lambda *_: None)
    assert (s1["built"], s2["unchanged"], s3["built"]) == (["births_538"], ["births_538"], ["births_538"])
    assert calls == ["births_538", "births_538"]
    s4 = update.run(["future_source"], state_file=state, make_ctx=ctx_for, log=lambda *_: None)
    assert "future_source" in s4["skipped"]
    assert "Built: nothing" in update.markdown(s4)


def test_a_failing_source_is_reported_not_fatal(make_ctx, monkeypatch, tmp_path):
    class Broken:
        MANUAL = ["x.csv"]

        @staticmethod
        def build(ctx):
            raise PipelineError("layout changed")

    monkeypatch.setitem(update.BUILDERS, "bps", Broken)
    monkeypatch.setattr(update, "load_contract", lambda: json.loads((make_ctx.data / "contract.json").read_text()))
    monkeypatch.setattr(update, "load_sources", lambda: json.loads((make_ctx.data / "sources.json").read_text())["sources"])
    (make_ctx.manual / "bps").mkdir(parents=True)
    (make_ctx.manual / "bps" / "x.csv").write_text("a\n1\n")
    s = update.run(["bps"], state_file=tmp_path / "s.json", make_ctx=make_ctx, log=lambda *_: None)
    assert s["failed"] == {"bps": "layout changed"}
    assert "layout changed" in update.markdown(s)


def test_generated_only_moves_when_the_published_content_changes(tmp_path):
    import datetime as dt

    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    state = tmp_path / "published.json"
    day1 = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
    day2 = dt.datetime(2026, 11, 2, tzinfo=dt.timezone.utc)
    a = publish.publish(tmp_path / "site", data_dir=data, qdir=QDIR, now=day1, state_file=state)
    b = publish.publish(tmp_path / "site", data_dir=data, qdir=QDIR, now=day2, state_file=state)
    assert a["generated"] == b["generated"] == "2026-11-01T00:00:00+00:00"

    contract = json.loads((data / "contract.json").read_text())
    path = data / contract["datasets"]["id.bps.poverty_line"]["file"]
    env = json.loads(path.read_text())
    env["data"]["value"] += 1
    path.write_text(json.dumps(env))
    c = publish.publish(tmp_path / "site", data_dir=data, qdir=QDIR, now=day2, state_file=state)
    assert c["generated"] == "2026-11-02T00:00:00+00:00"


def test_hand_saved_sources_keep_their_committed_build_when_the_files_are_absent(make_ctx, monkeypatch, tmp_path):
    calls = []

    class HandSaved:
        MANUAL = ["big.csv.gz"]

        @staticmethod
        def build(ctx):
            calls.append(ctx.source_id)
            ctx.write("world.pip.percentiles", {"countries": {}}, year=2025)

    monkeypatch.setitem(update.BUILDERS, "worldbank_pip", HandSaved)
    monkeypatch.setattr(update, "load_contract", lambda: json.loads((make_ctx.data / "contract.json").read_text()))
    monkeypatch.setattr(update, "load_sources", lambda: json.loads((make_ctx.data / "sources.json").read_text())["sources"])
    state = tmp_path / "s.json"

    waiting = update.run(["worldbank_pip"], state_file=state, make_ctx=make_ctx, log=lambda *_: None)
    assert "hand-saved" in waiting["skipped"]["worldbank_pip"] and calls == []

    (make_ctx.manual / "worldbank_pip").mkdir(parents=True)
    (make_ctx.manual / "worldbank_pip" / "big.csv.gz").write_bytes(b"x")
    built = update.run(["worldbank_pip"], state_file=state, make_ctx=make_ctx, log=lambda *_: None)
    assert built["built"] == ["worldbank_pip"] and calls == ["worldbank_pip"]

    (make_ctx.manual / "worldbank_pip" / "big.csv.gz").unlink()  # as in the daily job's checkout
    kept = update.run(["worldbank_pip"], state_file=state, make_ctx=make_ctx, log=lambda *_: None)
    assert kept["unchanged"] == ["worldbank_pip"] and calls == ["worldbank_pip"]
