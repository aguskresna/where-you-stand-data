"""Command line.

    python -m statsapp_pipeline list                      sources, licenses, build status
    python -m statsapp_pipeline build census_acs_pums     build named sources now ('all' for every one)
    python -m statsapp_pipeline update                    the daily job: rebuild only what changed
    python -m statsapp_pipeline questions                 check the question catalog
    python -m statsapp_pipeline publish --out ../site     write the static site the app downloads
    python -m statsapp_pipeline check                     check built files against the contract
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .common import DATA_DIR, Context, PipelineError, load_contract, load_json, load_sources
from .sources import BUILDERS, ORDER

LICENSED = {"PD", "CC0", "CC BY 4.0", "CC BY 3.0 IGO", "NCHS", "BPS"}


def cmd_list(_args) -> int:
    sources = load_sources()
    manifest = load_json(DATA_DIR / "manifest.json").get("datasets", {})
    contract = load_contract()["datasets"]
    for sid, s in sources.items():
        ds = [d for d, spec in contract.items() if sid in spec["sources"]]
        built = sum(1 for d in ds if d in manifest)
        status = "builder ready" if sid in BUILDERS else "not written yet"
        print(f"{sid:22} {s['region']:6} {s['licenseCode']:14} {s['pipeline']:8} {status:16} built {built}/{len(ds)}")
    return 0


def gate(sid: str, sources: dict) -> None:
    """Refuses sources that aren't registered, aren't cleared, or have no builder yet."""
    s = sources.get(sid)
    if not s:
        raise PipelineError(f"Unknown source {sid}. Run 'list' to see them.")
    if s.get("licenseCode") not in LICENSED:
        raise PipelineError(f"{sid} has license '{s.get('licenseCode')}', which isn't on the cleared list")
    if sid not in BUILDERS or s.get("pipeline") == "pending":
        raise PipelineError(f"The builder for {sid} isn't written yet. To do: {s.get('todo', 'see sources.json')}")


def cmd_build(args) -> int:
    sources = load_sources()
    targets = ORDER if args.sources == ["all"] else args.sources
    options = {"year": args.year, "sample_size": args.sample_size}
    failed = []
    for sid in targets:
        print(f"{sid}")
        start = time.time()
        try:
            gate(sid, sources)
            ctx = Context(sid, options={k: v for k, v in options.items() if v is not None}, offline=args.offline)
            BUILDERS[sid].build(ctx)
            print(f"  done in {time.time() - start:.0f}s: {', '.join(ctx.written) or 'nothing written'}")
        except PipelineError as e:
            failed.append(sid)
            print(f"  not built: {e}")
    if failed:
        print(f"\nNot built: {', '.join(failed)}")
    return 1 if failed and args.sources != ["all"] else 0


def check_quantiles(obj, path, problems, n=101):
    if isinstance(obj, list) and obj and all(isinstance(x, (int, float)) for x in obj) and len(obj) == n:
        if any(b < a for a, b in zip(obj, obj[1:])):
            problems.append(f"{path} isn't ascending")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            check_quantiles(v, f"{path}.{k}", problems, n)


def cmd_check(_args) -> int:
    contract = load_contract()["datasets"]
    manifest = load_json(DATA_DIR / "manifest.json").get("datasets", {})
    problems = []
    for did, entry in manifest.items():
        spec = contract.get(did)
        if not spec:
            problems.append(f"{did}: in the manifest but not the contract")
            continue
        files = [spec["file"].replace("{shard}", s) for s in entry.get("shards", [])] if spec.get("sharded") else [spec["file"]]
        for rel in files[:50]:
            path = DATA_DIR / rel
            if not path.exists():
                problems.append(f"{did}: missing {rel}")
                continue
            env = load_json(path)
            if env.get("id") != did or "data" not in env:
                problems.append(f"{did}: {rel} isn't a {did} envelope")
            if spec["kind"] == "quantiles":
                check_quantiles(env["data"], did, problems)
    missing = [d for d in contract if d not in manifest]
    print(f"{len(manifest)} of {len(contract)} datasets built.")
    if missing:
        print("Not built yet: " + ", ".join(missing))
    for p in problems:
        print(f"PROBLEM {p}")
    return 1 if problems else 0


def cmd_update(args) -> int:
    from . import update

    summary = update.run(args.sources or None, force=args.force)
    report = update.markdown(summary)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"failed={','.join(summary['failed'])}\n")
    return 0  # failures are reported after deploying what did build


def cmd_questions(_args) -> int:
    from . import questions

    catalog = questions.load()
    problems = questions.validate(catalog, load_contract())
    manifest = load_json(DATA_DIR / "manifest.json")
    shown = questions.visible(catalog, manifest)
    for p in problems:
        print(f"PROBLEM {p}")
    print(f"{len(catalog['questions'])} questions defined, {len(shown['questions'])} have their data built.")
    return 1 if problems else 0


def cmd_publish(args) -> int:
    from . import publish

    from .common import STATE_DIR

    index = publish.publish(Path(args.out), state_file=STATE_DIR / "published.json")
    print(f"Published {len(index['datasets'])} datasets to {args.out}")
    if args.bundle:
        copied = publish.bundle(Path(args.out), Path(args.bundle))
        print(f"Copied {len(copied)} files into the app bundle at {args.bundle}")
    return 0


def _use_system_certificates() -> None:
    """Trust the operating system's certificate store (some PCs and proxies need it); no-op if unavailable."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass


def main(argv=None) -> int:
    _use_system_certificates()
    parser = argparse.ArgumentParser(prog="python -m statsapp_pipeline", description="Build the app's datasets from official statistics.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="every source, its license and build status").set_defaults(fn=cmd_list)
    b = sub.add_parser("build", help="build one or more sources now, or 'all'")
    b.add_argument("sources", nargs="+")
    b.add_argument("--year", type=int, help="ACS PUMS year (default: the newest published)")
    b.add_argument("--sample-size", type=int, help="rows in the ACS sample for stacked filters (default 80000)")
    b.add_argument("--offline", action="store_true", help="use only files already downloaded or saved by hand")
    b.set_defaults(fn=cmd_build)
    u = sub.add_parser("update", help="rebuild only the sources whose published files changed")
    u.add_argument("sources", nargs="*")
    u.add_argument("--force", action="store_true", help="rebuild even if nothing changed")
    u.set_defaults(fn=cmd_update)
    sub.add_parser("questions", help="check the question catalog").set_defaults(fn=cmd_questions)
    pub = sub.add_parser("publish", help="write the static site the app downloads")
    pub.add_argument("--out", required=True, help="folder to write, e.g. ../site")
    pub.add_argument("--bundle", help="also copy a snapshot into the app, e.g. ../../app/assets/data")
    pub.set_defaults(fn=cmd_publish)
    sub.add_parser("check", help="check built files against the contract").set_defaults(fn=cmd_check)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
