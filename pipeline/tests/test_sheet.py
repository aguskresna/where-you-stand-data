"""The catalog's translation sheet: export, checks on a returned sheet, and writing the overlays back."""

import shutil

from statsapp_pipeline import i18n, questions, sheet
from conftest import ROOT

QDIR = ROOT / "questions"


def load():
    return questions.load(QDIR), i18n.load_overlays(QDIR)


def exported(tmp_path):
    c, o = load()
    path = tmp_path / "translations.csv"
    n = sheet.export(path, c, o)
    return c, o, path, sheet.read_sheet(path), n


def col(rows, name):
    return rows[0].index(name)


def test_sheet_layout_matches_the_shared_workflow(tmp_path):
    _, _, path, rows, n = exported(tmp_path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 with a byte-order mark, for Excel
    assert raw[3:].startswith(b'"#","Key (do not change)","English"')  # every field quoted
    assert rows[0] == sheet.COLUMNS + ["Indonesian (id) - current", "Malay (ms) - current", "Translator comments"]
    assert len(rows) == n + 1 and n > 1000
    keys = [r[1] for r in rows[1:]]
    assert len(set(keys)) == len(keys)
    assert [r[0] for r in rows[1:]] == [str(i) for i in range(1, n + 1)]


def test_rows_describe_the_text(tmp_path):
    c, _, _, rows, _ = exported(tmp_path)
    by_key = {r[1]: r for r in rows[1:]}
    r = by_key["questions/us-income-rank/text/sentence"]
    assert r[2] == "You earn more than {pct} of {group}."
    assert r[3] == "You vs the US › Income rank"
    assert r[5] == "Result sentence"
    assert "{pct} = 72%" in r[6] and "{" not in r[7]
    assert r[12] and r[13]  # id and ms already translated
    assert by_key["modes/id/title"][2] == "You vs Indonesia"
    assert "BPS" in by_key["questions/id-kelas-sosial/text/caveats/0"][10]
    assert by_key["questions/us-income-rank/text/stats/0/0"][5] == "Stat label"
    # Every placeholder has an example value.
    assert not any("(a value)" in r[6] or "<" in r[7] for r in rows[1:])
    # US state names stay English on purpose and aren't in the sheet; translated list items are.
    assert "lists/us_states_any/TX" not in by_key and "lists/us_states_any/*" in by_key
    # Every key maps back to the overlay entry it stands for.
    english = i18n.translatable(c)
    for r in rows[1:]:
        assert sheet.resolve(english, r[1]) is not None, r[1]


def test_keys_escape_slashes():
    path = ["lists", "x", "a/b~c"]
    key = sheet.make_key(path)
    assert key == "lists/x/a~1b~0c"
    assert sheet.split_key(key) == path


def test_round_trip_leaves_the_overlays_byte_identical(tmp_path):
    c, o, _, rows, _ = exported(tmp_path)
    new, problems, warnings, changes = sheet.apply(c, o, rows)
    assert problems == [] and warnings == []
    assert changes == {"id": 0, "ms": 0}
    for lang in i18n.LANGUAGES:
        target = tmp_path / f"{lang}.json"
        shutil.copy(QDIR / "i18n" / f"{lang}.json", target)
        before = target.read_bytes()
        assert sheet.write_overlay(target, new[lang]) is False
        assert target.read_bytes() == before
        # Writing the overlay out from scratch gives the same bytes too.
        assert sheet.dump_overlay(new[lang]) == before


def test_returned_sheet_is_checked(tmp_path):
    c, o, _, rows, _ = exported(tmp_path)
    keyc, idc, msc = 1, col(rows, "Indonesian (id) - current"), col(rows, "Malay (ms) - current")
    find = {r[1]: i for i, r in enumerate(rows)}
    rows[find["questions/us-income-rank/text/sentence"]][idc] = "Penghasilan Anda melebihi {persen} dari {group}."
    rows[find["questions/us-income-rank/title"]][msc] = "  "
    rows[find["modes/us/title"]][keyc] = "modes/mars/title"
    caveat = find["questions/id-kelas-sosial/text/caveats/0"]
    rows[caveat][idc] = rows[caveat][idc].replace("BPS", "Badan Pusat Statistik")
    new, problems, warnings, changes = sheet.apply(c, o, rows)
    text = "\n".join(problems)
    assert "placeholders" in text and "us-income-rank/text/sentence" in text
    assert "ms questions/us-income-rank/title: empty" in text
    assert 'unknown key "modes/mars/title"' in text
    assert len(problems) == 3
    assert len(warnings) == 1 and "missing BPS" in warnings[0]
    assert changes["id"] == 1  # the warned row is still taken


def test_changes_are_written_and_pass_the_validator(tmp_path):
    c, o, _, rows, _ = exported(tmp_path)
    msc = col(rows, "Malay (ms) - current")
    find = {r[1]: i for i, r in enumerate(rows)}
    rows[find["questions/us-income-rank/text/sentence"]][msc] = "Pendapatan anda melebihi {pct} daripada {group}."
    new, problems, _, changes = sheet.apply(c, o, rows)
    assert problems == [] and changes == {"id": 0, "ms": 1}
    assert new["ms"]["questions"]["us-income-rank"]["text"]["sentence"].startswith("Pendapatan anda")
    assert i18n.validate_overlay(c, new["ms"], "ms") == []
    assert o["ms"]["questions"]["us-income-rank"]["text"]["sentence"] != new["ms"]["questions"]["us-income-rank"]["text"]["sentence"]
    target = tmp_path / "ms.json"
    shutil.copy(QDIR / "i18n" / "ms.json", target)
    assert sheet.write_overlay(target, new["ms"]) is True
    assert target.read_bytes().count(b"\n") == (QDIR / "i18n" / "ms.json").read_bytes().count(b"\n")


def test_new_text_goes_in_at_the_english_position(tmp_path):
    c, o, _, rows, _ = exported(tmp_path)
    # A language that lacks a question's text entirely gets it in the overlay's shape.
    trimmed = {lang: dict(v) for lang, v in o.items()}
    trimmed["id"] = {**o["id"], "questions": {k: v for k, v in o["id"]["questions"].items() if k != "us-income-rank"}}
    new, problems, _, changes = sheet.apply(c, trimmed, rows)
    assert problems == []
    assert changes["id"] > 0 and changes["ms"] == 0
    assert list(new["id"]["questions"]) == list(o["id"]["questions"])
    assert new["id"]["questions"]["us-income-rank"] == o["id"]["questions"]["us-income-rank"]
    assert i18n.validate_overlay(c, new["id"], "id") == []


def test_committed_sheet_is_current(tmp_path):
    _, _, path, _, _ = exported(tmp_path)
    assert path.read_bytes() == (QDIR / "i18n" / "translations.csv").read_bytes(), (
        "questions/i18n/translations.csv is out of date: run python -m statsapp_pipeline sheet"
    )
