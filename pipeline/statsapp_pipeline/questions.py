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
KINDS = {
    "group_rank": 1,
    "class_by_multiple": 1,
    "age_rank": 1,
    "date_rank": 1,
    "life_table": 1,
}

INPUT_TYPES = {"number", "money", "height", "choice", "select", "date", "monthday", "toggle", "text", "range", "multi", "weights"}
MODE_FILES = ["us", "world", "my", "id"]


def load(qdir: Path = QUESTIONS_DIR) -> dict:
    """modes.json plus every question file, as one catalog dict."""
    with open(qdir / "modes.json", encoding="utf-8") as f:
        catalog = json.load(f)
    questions = []
    for name in MODE_FILES:
        path = qdir / f"{name}.json"
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
            if field.get("type") in ("choice", "select") and not opts and not src:
                bad(f"input {key} has no options")
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
