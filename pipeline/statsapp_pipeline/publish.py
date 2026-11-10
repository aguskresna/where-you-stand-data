"""Turns backend/data into the static site the app downloads (and the snapshot it ships with).

site/
  index.json                         what's available, with a SHA-256 and size for every file
  _headers                           cache rules for Cloudflare Pages
  files/catalog.<hash>.json          questions whose data is built
  files/sources.<hash>.json          names, credits and licenses of the sources in use
  files/<dataset>.<hash>.json        one file per dataset
  files/<dataset>~<shard>.<hash>.json  one file per shard of a sharded dataset

File names carry a hash of their content, so they can be cached forever; only index.json changes
in place, and it is cached for five minutes. The app compares hashes and downloads what changed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

from . import questions as qmod
from .common import DATA_DIR, QUESTIONS_DIR, PipelineError, load_contract, load_json, load_sources, write_json_atomic

HEADERS = """/index.json
  Cache-Control: public, max-age=300
/files/*
  Cache-Control: public, max-age=31536000, immutable
"""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _put(out: Path, stem: str, data: bytes) -> dict:
    digest = _sha(data)
    rel = f"files/{stem}.{digest[:12]}.json"
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": rel, "sha256": digest, "bytes": len(data)}


def _json_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def publish(out: Path, *, data_dir: Path = DATA_DIR, qdir: Path = QUESTIONS_DIR, now: dt.datetime | None = None,
            state_file: Path | None = None) -> dict:
    """Writes the site into `out` (replacing it) and returns the index.

    With a state_file, `generated` only changes when the published content does, so the app's
    check on open finds nothing new on days the job rebuilt nothing.
    """
    contract = load_contract(data_dir)
    manifest = load_json(data_dir / "manifest.json")
    catalog = qmod.check(qdir, contract)
    shown = qmod.visible(catalog, manifest)
    needed = sorted({d for q in shown["questions"] for d in q["datasets"]})

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    index = {"schema": qmod.SCHEMA, "generated": None, "datasets": {}}
    used_sources: set[str] = set()
    for did in needed:
        spec = contract["datasets"][did]
        entry = manifest["datasets"][did]
        used_sources.update(spec["sources"])
        meta = {"year": entry.get("year"), "built": entry.get("built"), "sources": spec["sources"]}
        if spec.get("sharded"):
            shards = {}
            for shard in entry.get("shards", []):
                src = data_dir / spec["file"].replace("{shard}", shard)
                if not src.exists():
                    raise PipelineError(f"{did}: missing shard file {src}")
                shards[shard] = _put(out, f"{did}~{shard}", src.read_bytes())
            index["datasets"][did] = {**meta, "shards": shards}
        else:
            src = data_dir / spec["file"]
            if not src.exists():
                raise PipelineError(f"{did}: missing {src}")
            index["datasets"][did] = {**meta, **_put(out, did, src.read_bytes())}

    registry = load_sources(data_dir)
    keep = ("name", "publisher", "credit", "license", "licenseUrl", "licenseCode", "region")
    sources = {sid: {k: registry[sid][k] for k in keep if k in registry[sid]} for sid in sorted(used_sources)}
    index["catalog"] = _put(out, "catalog", _json_bytes(shown))
    index["sources"] = _put(out, "sources", _json_bytes(sources))

    content = _sha(_json_bytes({k: v for k, v in index.items() if k != "generated"}))
    previous = load_json(state_file) if state_file and state_file.exists() else {}
    if previous.get("content") == content and previous.get("generated"):
        index["generated"] = previous["generated"]
    else:
        index["generated"] = (now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0).isoformat()
        if state_file:
            write_json_atomic(state_file, {"content": content, "generated": index["generated"]}, indent=2)
    write_json_atomic(out / "index.json", index, indent=1)
    (out / "_headers").write_text(HEADERS, encoding="utf-8")
    return index


def bundle(site: Path, dest: Path, max_bytes: int = 8_000_000) -> list[str]:
    """Copies index.json, the catalog, the sources and every unsharded dataset into the app's assets.

    Shards (per-name or per-country files) are left out: the app downloads them when first needed.
    Datasets larger than max_bytes are left out too, to keep the app small; it downloads them on open.
    Returns the copied paths.
    """
    index = load_json(site / "index.json")
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "files").mkdir(parents=True)
    copied = []
    entries = [index["catalog"], index["sources"]] + [d for d in index["datasets"].values() if "path" in d and d["bytes"] <= max_bytes]
    for e in entries:
        shutil.copy(site / e["path"], dest / e["path"])
        copied.append(e["path"])
    shutil.copy(site / "index.json", dest / "index.json")
    return copied
