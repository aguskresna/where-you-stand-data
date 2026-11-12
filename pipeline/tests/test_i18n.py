"""Translations of the question catalog: the overlays in questions/i18n/ and their publishing."""

import json
import shutil

from statsapp_pipeline import i18n, publish, questions
from conftest import ROOT

QDIR = ROOT / "questions"


def catalog():
    return questions.load(QDIR)


def overlay(**sections):
    return {"schema": 1, "language": "ms", **sections}


def test_every_shipped_overlay_is_valid_and_complete():
    c = catalog()
    overlays = i18n.load_overlays(QDIR)
    assert set(overlays) == set(i18n.LANGUAGES)
    for lang, o in overlays.items():
        assert i18n.validate_overlay(c, o, lang) == []
        left = i18n.missing(c, o)
        # Only proper names (states and provinces) may stay as they are.
        assert set(left) <= {"lists"}, f"{lang} leaves {sorted(left)} untranslated"
        assert set(o["questions"]) == {q["id"] for q in c["questions"]}
        assert set(o["messages"]) == set(c["messages"])


def test_translatable_text_leaves_structure_out():
    c = catalog()
    t = i18n.translatable(c)
    q = t["questions"]["us-income-rank"]
    assert q["title"] == "Income rank"
    assert q["inputs"]["income"]["label"] == "Your yearly income"
    assert q["params"]["parts"][0]["phrase"] == {"F": "women", "M": "men", "*": "adults"}
    # Dataset ids, paths and input keys are never translatable.
    assert "dataset" not in q["params"] and "path" not in q["params"] and "value" not in q["params"]
    assert q["params"]["parts"][0].get("input") is None
    assert t["lists"]["us_states_any"]["*"] == "Whole US"
    assert "messages" in t and t["messages"]["noFigures"]


def test_placeholders_must_match_the_english():
    c = catalog()
    o = overlay(questions={"us-income-rank": {"text": {"sentence": "Anda memperoleh lebih daripada {pct} {kumpulan}."}}})
    problems = "\n".join(i18n.validate_overlay(c, o, "ms"))
    assert "placeholders" in problems and "us-income-rank" in problems
    # Missing a placeholder is as wrong as adding one.
    o = overlay(messages={"noPpp": "Tiada kadar kuasa beli lagi."})
    assert any("placeholders" in p for p in i18n.validate_overlay(c, o, "ms"))
    o = overlay(messages={"noPpp": "Tiada kadar kuasa beli untuk {name} lagi."})
    assert i18n.validate_overlay(c, o, "ms") == []


def test_unknown_ids_fields_and_structure_are_rejected():
    c = catalog()
    bad = overlay(
        questions={
            "us-no-such-question": {"title": "x"},
            "us-income-rank": {
                "kind": "group_rank",
                "params": {"dataset": "us.acs.other", "parts": [{"phrase": {"F": "wanita"}}, None, None]},
                "inputs": {"nobody": {"label": "x"}, "sex": {"default": "M"}},
                "text": {"stats": [["a", "b", "c"]]},
            },
        },
        modes={"mars": {"title": "x"}},
        lists={"sex": {"X": "x"}},
        messages={"noSuchMessage": "x"},
        extra={},
    )
    bad["language"] = "id"
    problems = "\n".join(i18n.validate_overlay(c, bad, "ms"))
    for expected in (
        "language must be 'ms'",
        "unknown section extra",
        "questions.us-no-such-question: unknown",
        "us-income-rank.kind: unknown",
        "params.dataset: unknown",
        "inputs.nobody: unknown",
        "inputs.sex.default: unknown",
        "modes.mars: unknown",
        "lists.sex.X: unknown",
        "messages.noSuchMessage: unknown",
        "must be a list of",
    ):
        assert expected in problems, expected


def test_missing_lists_what_a_language_still_needs():
    c = catalog()
    left = i18n.missing(c, overlay(topics={"money": "Wang dan kerja"}))
    assert "money" not in left["topics"] and "home" in left["topics"]
    assert "us-income-rank" in left["questions"]


def test_publish_writes_one_overlay_per_language(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    qdir = tmp_path / "questions"
    shutil.copytree(QDIR, qdir)
    (qdir / "i18n").mkdir(exist_ok=True)
    for lang in i18n.LANGUAGES:
        o = {"schema": 1, "language": lang, "topics": {"money": f"money-{lang}"},
             "questions": {"id-kelas-sosial": {"title": f"kelas-{lang}"}, "us-income-rank": {"title": f"rank-{lang}"}}}
        (qdir / "i18n" / f"{lang}.json").write_text(json.dumps(o), encoding="utf-8")
    site = tmp_path / "site"
    index = publish.publish(site, data_dir=data, qdir=qdir)
    assert set(index["catalogI18n"]) == set(i18n.LANGUAGES)
    for lang, entry in index["catalogI18n"].items():
        assert entry["path"].startswith(f"files/catalog.{lang}.")
        o = json.loads((site / entry["path"]).read_text(encoding="utf-8"))
        assert o["topics"] == {"money": f"money-{lang}"}
        shown = {q["id"] for q in json.loads((site / index["catalog"]["path"]).read_text(encoding="utf-8"))["questions"]}
        # Only questions the published catalog shows.
        assert set(o["questions"]) <= shown and "id-kelas-sosial" in o["questions"]
    copied = publish.bundle(site, tmp_path / "app")
    assert all(e["path"] in copied for e in index["catalogI18n"].values())

    # A broken overlay stops publishing.
    (qdir / "i18n" / "ms.json").write_text(json.dumps({"schema": 1, "language": "ms", "messages": {"noPpp": "x"}}), encoding="utf-8")
    try:
        publish.publish(tmp_path / "site2", data_dir=data, qdir=qdir)
    except Exception as e:  # PipelineError
        assert "placeholders" in str(e)
    else:
        raise AssertionError("publish accepted a broken overlay")
