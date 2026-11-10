"""The daily job: rebuild only the sources whose published files changed.

Each builder module can declare what to watch:
  WATCH = [urls]             checked with an HTTP HEAD (ETag, Last-Modified, size)
  watch(ctx) -> [urls]       the same, worked out at run time (e.g. the newest ACS year)
  MANUAL = [file names]      hand-saved files in pipeline/manual/<source>/, hashed
  version(ctx) -> str        anything else that changes with a new release
  DEPENDS = [source ids]     sources whose output this one reads

Their fingerprint is compared with backend/state/fingerprints.json. A source is rebuilt when the
fingerprint changed, when its datasets aren't all built, or when --force is given. One failing
source doesn't stop the others; the summary lists failures so the workflow can report them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from .common import STATE_DIR, Context, PipelineError, load_contract, load_json, load_sources, write_json_atomic
from .sources import BUILDERS, ORDER

STATE_FILE = STATE_DIR / "fingerprints.json"


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hand_saved_only_and_absent(ctx: Context, module) -> bool:
    """True for a source that reads only files saved by hand, when none of them are in this checkout.

    Big hand-saved files (UN WPP, World Bank PIP) aren't committed: build those sources on your own
    computer and commit the output. The daily job then keeps that build instead of failing.
    """
    names = getattr(module, "MANUAL", [])
    if not names or hasattr(module, "watch") or getattr(module, "WATCH", None) or hasattr(module, "version"):
        return False
    return not any((folder / n).exists() for n in names for folder in (ctx.manual_dir, ctx.raw))


def fingerprint(ctx: Context, module, state: dict) -> str | None:
    """A hash of everything that would change if the publisher released new data, or None if unknown."""
    parts: list[str] = []
    urls = module.watch(ctx) if hasattr(module, "watch") else getattr(module, "WATCH", [])
    for url in urls:
        parts.append(f"url {url} {ctx.head(url)}")
    for name in getattr(module, "MANUAL", []):
        for folder in (ctx.manual_dir, ctx.raw):
            if (folder / name).exists():
                parts.append(f"file {name} {_file_hash(folder / name)}")
                break
        else:
            parts.append(f"file {name} missing")
    if hasattr(module, "version"):
        parts.append(f"version {module.version(ctx)}")
    for dep in getattr(module, "DEPENDS", []):
        parts.append(f"depends {dep} {state.get(dep, {}).get('fingerprint')}")
    if not parts:
        return None
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def run(targets: list[str] | None = None, *, force: bool = False, state_file: Path = STATE_FILE, make_ctx=None, log=print) -> dict:
    """Checks and rebuilds sources. Returns {'built': [...], 'unchanged': [...], 'failed': {sid: reason}, 'skipped': {...}}."""
    sources = load_sources()
    contract = load_contract()
    state = load_json(state_file) if state_file.exists() else {}
    make_ctx = make_ctx or (lambda sid: Context(sid))
    summary = {"built": [], "unchanged": [], "failed": {}, "skipped": {}}
    for sid in targets or ORDER:
        if sid not in BUILDERS or sources.get(sid, {}).get("pipeline") == "pending":
            summary["skipped"][sid] = "builder not written yet"
            continue
        module = BUILDERS[sid]
        ctx = make_ctx(sid)
        manifest = load_json(ctx.data_dir / "manifest.json").get("datasets", {})
        datasets = [d for d, spec in contract["datasets"].items() if sid in spec["sources"]]
        complete = all(d in manifest for d in datasets)
        if not force and hand_saved_only_and_absent(ctx, module):
            if complete:
                summary["unchanged"].append(sid)
                log(f"{sid}: its hand-saved files aren't here; keeping the committed build")
            else:
                summary["skipped"][sid] = "waiting for hand-saved files (see pipeline/manual/README.md)"
                log(f"{sid}: waiting for hand-saved files")
            continue
        try:
            fp = fingerprint(ctx, module, state)
        except Exception as e:  # network trouble: try the build, which reports a clear error
            log(f"{sid}: couldn't check for changes ({e})")
            fp = None
        if not force and fp and state.get(sid, {}).get("fingerprint") == fp and complete:
            summary["unchanged"].append(sid)
            log(f"{sid}: unchanged")
            continue
        log(f"{sid}: building")
        try:
            module.build(ctx)
        except PipelineError as e:
            summary["failed"][sid] = str(e)
            log(f"{sid}: not built: {e}")
            continue
        except Exception as e:  # a bug or an unexpected file layout; keep going with the other sources
            summary["failed"][sid] = f"{type(e).__name__}: {e}"
            log(f"{sid}: failed: {type(e).__name__}: {e}")
            continue
        prev = state.get(sid)
        if ctx.changed or not prev or prev.get("fingerprint") != fp:
            # Only touch the state when something changed, so quiet days leave nothing to commit.
            state[sid] = {"fingerprint": fp, "built": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "datasets": ctx.written}
        summary["built"].append(sid)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(state_file, dict(sorted(state.items())), indent=2)
    return summary


def markdown(summary: dict) -> str:
    """A short report for the GitHub Actions run page."""
    lines = ["## Data update", ""]
    lines.append(f"Built: {', '.join(summary['built']) or 'nothing'}")
    lines.append(f"Unchanged: {', '.join(summary['unchanged']) or 'none'}")
    if summary["failed"]:
        lines += ["", "### Failed", *[f"- **{s}**: {r}" for s, r in summary["failed"].items()]]
    if summary["skipped"]:
        lines += ["", "### Skipped", *[f"- **{s}**: {r}" for s, r in summary["skipped"].items()]]
    return "\n".join(lines) + "\n"
