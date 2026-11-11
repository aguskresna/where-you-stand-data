"""Questions as data: loading, checking and filtering the catalog the app downloads.

The catalog is backend/questions/modes.json (modes, topics, option lists, bands) plus one file of
question definitions per mode. Each question names a calculation `kind` that the app implements.
A new question that uses an existing kind reaches users without an app update; a new kind needs one.
See backend/questions/README.md for the schema.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .common import QUESTIONS_DIR, PipelineError

SCHEMA = 1

# Calculation kinds and the first app build that implements them. The app hides questions whose
# kind it doesn't know, so a catalog can list kinds that only newer app versions understand.
# Every kind ships in app build 1: no build has been released yet, so nothing older needs hiding
# from. From the first store release on, a new kind gets the next build number.
KINDS = {
    "group_rank": 1,
    "class_by_multiple": 1,
    "age_rank": 1,
    "date_rank": 1,
    "life_table": 1,
    "group_share": 1,
    "category_rank": 1,
    "rank_tiers": 1,
    "debt_rank": 1,
    "count_in_range": 1,
    "item_record": 1,
    "compare_set": 1,
    "pay_vs_typical": 1,
    "personal_inflation": 1,
    "name_popularity": 1,
    "sign_share": 1,
    "chinese_zodiac": 1,
    "cohort_size": 1,
    "wpp_series": 1,
    "global_income": 1,
    "birth_lottery": 1,
    "world_partner": 1,
    "years_to_home": 1,
    "life_hours": 1,
}

INPUT_TYPES = {"number", "money", "height", "choice", "select", "date", "monthday", "toggle", "text", "range", "multi", "weights"}
MODE_FILES = ["us", "world", "my", "id"]


def load(qdir: Path = QUESTIONS_DIR) -> dict:
    """modes.json plus every question file, as one catalog dict."""
    with open(qdir / "modes.json", encoding="utf-8") as f:
        catalog = json.load(f)
    questions = []
    for name in MODE_FILES:
        # <mode>.json, then any <mode>.<part>.json files (a mode's questions may be split by topic).
        for path in [qdir / f"{name}.json", *sorted(qdir.glob(f"{name}.*.json"))]:
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    questions.extend(json.load(f))
    catalog["questions"] = questions
    return catalog


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{([^{}]+)\}", text or ""))


def validate(catalog: dict, contract: dict) -> list[str]:
    """Problems with the catalog (empty when all is well)."""
    problems: list[str] = []
    datasets = contract["datasets"]
    modes = {m["id"] for m in catalog.get("modes", [])}
    topics = set(catalog.get("topics", {}))
    lists = catalog.get("lists", {})
    bands = catalog.get("bands", {})
    if catalog.get("schema") != SCHEMA:
        problems.append(f"catalog schema must be {SCHEMA}")
    seen = set()
    for q in catalog.get("questions", []):
        qid = q.get("id", "?")
        bad = lambda msg: problems.append(f"{qid}: {msg}")
        for k in ("id", "mode", "topic", "title", "question", "kind", "datasets", "inputs", "params", "text"):
            if k not in q:
                bad(f"missing {k}")
        if qid in seen:
            bad("duplicate id")
        seen.add(qid)
        if not re.fullmatch(r"(us|world|my|id)-[a-z0-9-]+", qid) or not qid.startswith(f"{q.get('mode')}-"):
            bad("id must start with its mode, like us-name")
        if q.get("mode") not in modes:
            bad(f"unknown mode {q.get('mode')}")
        if q.get("topic") not in topics:
            bad(f"unknown topic {q.get('topic')}")
        if q.get("kind") not in KINDS:
            bad(f"unknown kind {q.get('kind')} (known: {', '.join(KINDS)})")
        for d in q.get("datasets", []):
            if d not in datasets:
                bad(f"unknown dataset {d}")
        # "uses": optional datasets, read when built; the question shows without them.
        for d in q.get("uses", []):
            if d not in datasets:
                bad(f"unknown optional dataset {d}")
            elif d in q.get("datasets", []):
                bad(f"{d} is in both datasets and uses")
        params = q.get("params", {})
        if params.get("dataset") and params["dataset"] not in q.get("datasets", []):
            bad(f"params.dataset {params['dataset']} isn't in datasets")
        if params.get("shard") and not datasets.get(params.get("dataset", ""), {}).get("sharded"):
            bad("params.shard is set but the dataset isn't sharded")
        keys = set()
        for field in q.get("inputs", []):
            key = field.get("key")
            if not key or key in keys:
                bad(f"input key {key!r} missing or repeated")
            keys.add(key)
            if field.get("type") not in INPUT_TYPES:
                bad(f"input {key} has unknown type {field.get('type')}")
            if not field.get("label"):
                bad(f"input {key} has no label")
            if "default" not in field:
                bad(f"input {key} has no default")
            opts = field.get("options")
            if isinstance(opts, str) and (not opts.startswith("@") or opts[1:] not in lists):
                bad(f"input {key} uses unknown list {opts}")
            src = field.get("optionsFrom")
            if src and src.get("dataset") not in q.get("datasets", []):
                bad(f"input {key} takes options from {src.get('dataset')}, which isn't in datasets")
            if field.get("type") in ("choice", "select", "multi") and not opts and not src:
                bad(f"input {key} has no options")
            wsrc = field.get("weightsFrom")
            if field.get("type") == "weights" and (not wsrc or wsrc.get("dataset") not in q.get("datasets", [])):
                bad(f"weights input {key} needs weightsFrom with a dataset the question reads")
            if field.get("type") == "range" and not (isinstance(field.get("default"), list) and len(field["default"]) == 2):
                bad(f"range input {key} needs a [low, high] default")
        for field in q.get("inputs", []):
            for other in (field.get("showIf") or {}):
                if other not in keys:
                    bad(f"input {field.get('key')} shows only for unknown input {other}")
            if field.get("currencyFrom") and field["currencyFrom"] not in keys:
                bad(f"input {field.get('key')} takes its currency from unknown input {field['currencyFrom']}")
        for part in params.get("parts", []):
            if part.get("input") not in keys:
                bad(f"group part uses unknown input {part.get('input')}")
            b = part.get("bands")
            if isinstance(b, str) and (not b.startswith("@") or b[1:] not in bands):
                bad(f"unknown bands {b}")
        for k in ("value", "amount", "birthDate", "age", "input"):
            if isinstance(params.get(k), str) and params[k] not in keys:
                bad(f"params.{k} refers to unknown input {params[k]}")
        text = q.get("text", {})
        if not text.get("headline") or not text.get("sentence"):
            bad("text needs a headline and a sentence")
        for path_key in ("path", "table", "fallback", "labelsPath"):
            for part in params.get(path_key, []) or []:
                for name in _placeholders(part):
                    if name not in keys:
                        bad(f"params.{path_key} uses unknown input {{{name}}}")
    return problems


def visible(catalog: dict, manifest: dict) -> dict:
    """The catalog limited to questions whose datasets are all built, and modes that have any."""
    built = manifest.get("datasets", {})
    questions = [q for q in catalog["questions"] if all(d in built for d in q["datasets"])]
    used_modes = {q["mode"] for q in questions}
    out = {k: v for k, v in catalog.items() if k not in ("questions", "modes", "note")}
    out["modes"] = [m for m in catalog["modes"] if m["id"] in used_modes]
    out["questions"] = questions
    out["kinds"] = {k: v for k, v in KINDS.items() if any(q["kind"] == k for q in questions)}
    return out


def check(qdir: Path, contract: dict) -> dict:
    catalog = load(qdir)
    problems = validate(catalog, contract)
    if problems:
        raise PipelineError("Question catalog problems:\n  " + "\n  ".join(problems))
    return catalog
