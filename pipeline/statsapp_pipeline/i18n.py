"""Translations of the question catalog: one overlay per language in backend/questions/i18n/<lang>.json.

An overlay holds only translated text, keyed by what it replaces, and the app lays it over the
English catalog field by field (anything missing stays English):

{
  "schema": 1,
  "language": "ms",
  "modes": {"us": {"title": "...", "blurb": "..."}},
  "topics": {"money": "..."},
  "lists": {"sex": {"F": "...", "M": "..."}},          # option value -> label
  "messages": {"noFigures": "..."},                     # the calculations' own messages
  "questions": {
    "us-income-rank": {
      "title": "...", "question": "...",
      "inputs": {"income": {"label": "...", "help": "...", "unit": "...",
                            "options": {"F": "..."}, "first": {"WLD": "..."}}},
      "params": {...},                                  # same shape as the question's params
      "text": {"headline": "...", "sentence": "...", "stats": [["...", null]], "caveats": ["..."]}
    }
  }
}

`params` and `text` mirror the English: objects by key, lists by position (same length, null keeps
the English item). Only text a person sees may be translated; dataset ids, paths, input keys,
codes and expressions may not (see translatable()). Every {placeholder} must stay as it is.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .common import QUESTIONS_DIR

LANGUAGES = ["ms", "id"]
SCHEMA = 1

# Params keys whose strings are never shown to a person: data locations, input keys, codes,
# expressions and switches. Their strings can't be translated.
STRUCTURAL = {
    "dataset", "datasets", "path", "table", "fallback", "labelsPath", "positions", "shard", "keys",
    "input", "value", "amount", "divideBy", "birthDate", "birthYear", "age", "sex", "size", "saved",
    "monthly", "down", "income", "minIncome", "seeking", "ages", "markInput", "weights", "country",
    "type", "field", "key", "currency", "bands", "layout", "series", "when", "valueExpr", "mode",
    "sort", "case", "format", "by", "labelField", "valueField", "nameField", "priceField",
    "incomeField", "ratioField", "countField", "totalField", "totalPath", "typesPath", "yearPath",
    "medianPath", "agesPath", "list", "keysOf", "codes", "nonEmpty", "pick", "mark", "scale", "ratio",
    "wdi", "wpp", "pip", "ppp", "cpi", "gdp", "power", "popAge", "totals", "labelOf", "currencyOf",
    "with", "if", "world", "first", "last", "mean", "index", "share", "exclude", "top", "groups",
    "unit", "product", "fallbackOrder", "all", "labels", "online", "from", "to", "year", "years",
    "group", "state", "sexKeys", "spreadFormat", "valueFormat", "round", "clamp", "at", "upTo",
    "below", "invalid", "allowEmpty", "limit", "after", "home", "grid", "method", "parts",
}
# Strings under these keys are text even when they look like a code ("US").
TEXT_KEYS = {"place", "people", "prefix"}
# Nothing under these keys is text: they build data paths and lookup keys.
STRUCTURAL_TREES = {"path", "table", "fallback", "labelsPath", "keys", "sexKeys", "positions"}
# Strings directly under these keys are text whatever their own key (phrase maps by input value,
# messages by input, templates by state).
TEXT_PARENTS = {"phrase", "map", "requirePositive", "when"}

_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
_LETTER = re.compile(r"[^\W\d_]")


def placeholders(text: str) -> list[str]:
    return sorted(_PLACEHOLDER.findall(text or ""))


def _has_text(s: str) -> bool:
    """Whether a string has words in it once its placeholders are taken out."""
    return bool(_LETTER.search(_PLACEHOLDER.sub("", s)))


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def _mirror(o, keep):
    """The translatable part of a JSON value: strings that keep(path, s) accepts, objects by key,
    lists by position with None for the rest. None when nothing in it is translatable."""

    def walk(v, path):
        if isinstance(v, str):
            return v if keep(path, v) else None
        if isinstance(v, dict):
            out = {k: m for k, x in v.items() if (m := walk(x, path + [k])) is not None}
            return out or None
        if isinstance(v, list):
            out = [walk(x, path + [i]) for i, x in enumerate(v)]
            return out if any(x is not None for x in out) else None
        return None

    return walk(o, [])


def translatable(catalog: dict) -> dict:
    """Everything a translator may translate, in the overlay's shape, with the English text."""
    out: dict = {
        "modes": {m["id"]: {k: m[k] for k in ("title", "blurb") if m.get(k)} for m in catalog.get("modes", [])},
        "topics": dict(catalog.get("topics", {})),
        "lists": {
            name: {str(v): label for v, label in items if _has_text(label)}
            for name, items in catalog.get("lists", {}).items()
        },
        "messages": dict(catalog.get("messages", {})),
        "questions": {},
    }
    datasets = set()
    for q in catalog.get("questions", []):
        datasets.update(q.get("datasets", []))
        datasets.update(q.get("uses", []))
    for q in catalog.get("questions", []):
        entry: dict = {k: q[k] for k in ("title", "question") if q.get(k)}
        inputs = {}
        input_keys = {i.get("key") for i in q.get("inputs", [])}
        for field in q.get("inputs", []):
            f = {k: field[k] for k in ("label", "help", "unit") if isinstance(field.get(k), str) and _has_text(field[k])}
            if isinstance(field.get("options"), list):
                opts = {str(o[0]): o[1] for o in field["options"] if isinstance(o, list) and len(o) >= 2 and _has_text(str(o[1]))}
                if opts:
                    f["options"] = opts
            first = (field.get("optionsFrom") or {}).get("first")
            if isinstance(first, list):
                opts = {str(o[0]): o[1] for o in first if isinstance(o, list) and len(o) >= 2 and _has_text(str(o[1]))}
                if opts:
                    f["first"] = opts
            if f:
                inputs[field["key"]] = f
        if inputs:
            entry["inputs"] = inputs
        # Placeholder names this question uses: a params string equal to one is a value name.
        names = {n for s in _strings([q.get("text"), q.get("params")]) for n in _PLACEHOLDER.findall(s)}

        def keep_param(path, s):
            keys = [p for p in path if isinstance(p, str)]
            last = keys[-1] if keys else None
            parent = keys[-2] if len(keys) >= 2 else None
            if not _has_text(s) or "|" in s or s.startswith("@"):
                return False
            if s in input_keys or s in datasets or s in names:
                return False
            if re.fullmatch(r"[A-Z0-9_.]+", s) and last not in TEXT_KEYS:  # codes such as WLD or NY.GDP.PCAP.PP.KD
                return False
            if STRUCTURAL_TREES.intersection(keys[:-1]) or ("parts" in keys[:-1] and last == "name"):
                return False
            return parent in TEXT_PARENTS or last not in STRUCTURAL

        params = _mirror(q.get("params", {}), keep_param)
        if params:
            entry["params"] = params
        text = _mirror(q.get("text", {}), lambda path, s: _has_text(s))
        if text:
            entry["text"] = text
        out["questions"][q["id"]] = entry
    return out


def load_overlays(qdir: Path = QUESTIONS_DIR) -> dict[str, dict]:
    out = {}
    for lang in LANGUAGES:
        path = qdir / "i18n" / f"{lang}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                out[lang] = json.load(f)
    return out


def validate_overlay(catalog: dict, overlay: dict, lang: str) -> list[str]:
    """Problems with one language's overlay (empty when all is well)."""
    problems: list[str] = []
    if overlay.get("schema") != SCHEMA:
        problems.append(f"{lang}: schema must be {SCHEMA}")
    if overlay.get("language") != lang:
        problems.append(f"{lang}: language must be {lang!r}")
    allowed = translatable(catalog)

    def check(tr, en, where):
        if tr is None:
            return
        if isinstance(en, str):
            if not isinstance(tr, str):
                problems.append(f"{lang} {where}: must be a string")
            elif not tr.strip():
                problems.append(f"{lang} {where}: is empty")
            elif placeholders(tr) != placeholders(en):
                problems.append(f"{lang} {where}: placeholders {placeholders(tr)} must be {placeholders(en)} as in English")
        elif isinstance(en, dict):
            if not isinstance(tr, dict):
                problems.append(f"{lang} {where}: must be an object")
                return
            for k, v in tr.items():
                if k not in en:
                    problems.append(f"{lang} {where}.{k}: unknown or not translatable")
                else:
                    check(v, en[k], f"{where}.{k}")
        elif isinstance(en, list):
            if not isinstance(tr, list) or len(tr) != len(en):
                problems.append(f"{lang} {where}: must be a list of {len(en)} items (null keeps the English)")
                return
            for i, (t, e) in enumerate(zip(tr, en)):
                if e is None and t is not None:
                    problems.append(f"{lang} {where}[{i}]: not translatable")
                else:
                    check(t, e, f"{where}[{i}]")
        else:
            problems.append(f"{lang} {where}: not translatable")

    for k in overlay:
        if k not in ("schema", "language", "modes", "topics", "lists", "messages", "questions"):
            problems.append(f"{lang}: unknown section {k}")
    for section in ("modes", "topics", "lists", "messages", "questions"):
        check(overlay.get(section), allowed[section], section)
    return problems


def missing(catalog: dict, overlay: dict) -> dict:
    """The English text an overlay doesn't translate yet, in the overlay's shape."""

    def walk(en, tr):
        if isinstance(en, str):
            return en if not isinstance(tr, str) else None
        if isinstance(en, dict):
            tr = tr if isinstance(tr, dict) else {}
            out = {k: m for k, v in en.items() if (m := walk(v, tr.get(k))) is not None}
            return out or None
        if isinstance(en, list):
            tr = tr if isinstance(tr, list) and len(tr) == len(en) else [None] * len(en)
            out = [walk(e, t) for e, t in zip(en, tr)]
            return out if any(x is not None for x in out) else None
        return None

    return walk(translatable(catalog), overlay) or {}


def published(overlay: dict, shown: dict) -> dict:
    """An overlay limited to the questions and modes the published catalog shows."""
    qids = {q["id"] for q in shown["questions"]}
    modes = {m["id"] for m in shown["modes"]}
    out = {k: v for k, v in overlay.items() if k not in ("questions", "modes")}
    out["modes"] = {k: v for k, v in overlay.get("modes", {}).items() if k in modes}
    out["questions"] = {k: v for k, v in overlay.get("questions", {}).items() if k in qids}
    return out
