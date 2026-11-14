# Notes for Claude Code: data backend

This repository builds the datasets and question catalog for the "Where you stand" mobile app and
publishes them as static files on Cloudflare Pages. Read README.md first.

## Rules that don't bend

- Real data only. Every number must come from the named publisher's own files. Never generate,
  interpolate across countries, or invent data to fill a gap; leave the dataset unbuilt instead, and
  the app hides its questions.
- Only sources whose license allows commercial use, recorded in `data/sources.json` with the
  license name, link and credit line. If a license is unclear, stop and ask.
- Free to run at any number of users: no servers, databases, paid APIs or paid runners. The
  repository stays public so GitHub Actions is free.
- No keys in `data/`, `questions/` or `site/`. A key the job needs goes in a repository secret and
  is read from the environment.
- Respect publishers' rate limits (data.gov.my allows 4 requests a minute) and send the
  User-Agent in `common.py`.
- Cloudflare Pages limits: 25 MiB per file, 20,000 files. Shard big datasets (see
  `us.ssa.names`, `world.wpp.lifetable`) and keep shard counts in the hundreds.

## Commands

```sh
cd pipeline
pytest -q                                   # must pass before every commit
python -m statsapp_pipeline questions       # the catalog validator
python -m statsapp_pipeline sheet           # re-generate questions/i18n/translations.csv after text changes
python -m statsapp_pipeline check           # built files against data/contract.json
python -m statsapp_pipeline build <source>  # build one source
python -m statsapp_pipeline update          # the daily job
python -m statsapp_pipeline publish --out ../site
```

## Adding a source

1. Add it to `data/sources.json` (license, licenseUrl, licenseCode on the cleared list in
   `__main__.py`, credit, region, pipeline, todo).
2. Add its datasets to `data/contract.json`: id, file, kind, sources, sharded, and the shape the app
   reads.
3. Write `pipeline/statsapp_pipeline/sources/<source>.py` with `SOURCE`, `build(ctx)` and what to
   watch (`WATCH`, `watch(ctx)`, `MANUAL`, `version(ctx)`, `DEPENDS`). Register it in
   `sources/__init__.py` (BUILDERS and ORDER).
4. Test it with a small fixture in the publisher's real layout (tests/test_sources.py has examples).
5. Run the real build once, and compare a few figures with the publisher's own published numbers.

## Adding a question

Write it in `questions/<mode>.json` using an existing kind (see `questions/README.md`). If no kind
fits, the app needs a new one: implement it in `app/lib/calc/`, register it in
`app/lib/calc/registry.dart`, bump `appBuild` in `app/lib/config.dart`, and add the kind to `KINDS`
in `pipeline/statsapp_pipeline/questions.py` with that build number. The specification for every
planned question is in `reference/web-prototype/web/js/features/` next to this repository.

## Don't

- Don't remove the heartbeat step in the workflow, or the schedule switches off after 60 days.
- Don't add "Time left with your parents" or similar questions; the owner left it out on purpose.
- Don't publish `pipeline/raw/` or anything with personal data; microdata (ACS PUMS, NHANES) is
  only ever published as aggregates over groups of at least `MIN_RECORDS` records. No row-level
  samples either, even anonymous ones (the owner decided this on 2026-11-11); questions that stack
  several filters use precomputed group figures.
