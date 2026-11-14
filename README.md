# Hall of Ranks: data backend

A daily job that downloads official statistics, turns them into small JSON datasets, and publishes
them as static files the app downloads. There is no server and no database, so the cost does not
grow with the number of app users.

```
publishers (Census, NCHS, UN, World Bank, DOSM, BPS, ...)
        │  GitHub Actions, once a day: check each source, rebuild only what changed
        ▼
data/                      the built datasets, committed (small JSON)
        │  publish: content-hashed files + index.json
        ▼
Cloudflare Pages           static hosting: unlimited requests and bandwidth on the free plan
        │  the app fetches index.json on every open, then only the files whose hash changed
        ▼
phones
```

## What it costs

| Part | Cost | Conditions |
| --- | --- | --- |
| GitHub Actions | Free | The repository is **public** and uses GitHub's standard runners. A job may run up to 6 hours. |
| Cloudflare Pages | Free | Unlimited static requests and bandwidth; 500 deploys a month, 20,000 files and 25 MiB per file. |
| Store accounts | $25 once (Google Play), $99 a year (Apple) | Not part of the backend, listed for completeness. |

Two things keep it free: the repository must stay public, and GitHub switches off scheduled
workflows in public repositories after 60 days without activity. The workflow commits a heartbeat
when nothing else has changed for 45 days, so the schedule stays on.

Never put an API key in `data/`, `questions/` or the published site. Keys the job needs live in
repository secrets.

## Setup

1. Create a **public** GitHub repository from this folder (this folder is the repository root).
2. In Cloudflare: My Profile → API Tokens → Create Token → Start from scratch → Account policy,
   permission "Cloudflare Pages: Edit". You don't need to create the Pages project; the job does.
3. In the GitHub repository settings (Secrets and variables → Actions), add the secret
   `CLOUDFLARE_API_TOKEN`, and the variables `CLOUDFLARE_ACCOUNT_ID` and `PAGES_PROJECT` (the project
   name, `hall-of-ranks-data` for this app; it becomes `https://hall-of-ranks-data.pages.dev/`).
4. Build the sources that read hand-saved files on your own computer (see below), commit `data/`.
5. Actions → Update data → Run workflow. When it finishes, `https://<project>.pages.dev/index.json`
   lists every published dataset.
6. Put that address in the app: `app/lib/config.dart` (`dataBaseUrl`), or pass
   `--dart-define=DATA_BASE_URL=...` when building.

## Running it yourself

```sh
cd pipeline
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest                                        # tests use small fixtures, no downloads
python -m statsapp_pipeline list              # every source, its license and build status
python -m statsapp_pipeline build ssa_names   # build one source now ('all' for every one)
python -m statsapp_pipeline update            # what the daily job runs: rebuild only what changed
python -m statsapp_pipeline publish --out ../site --bundle ../../app/assets/data
```

`publish --bundle` also refreshes the data snapshot inside the app (the app's
`tool/bundle_data.dart` does the same from the live site).

## Sources that need files saved by hand

Some publishers have no stable download link, or their files are too big to commit. Save them in
`pipeline/manual/<source>/` as `pipeline/manual/README.md` describes, build on your computer, and
commit the output in `data/`. The daily job keeps that build while the files are absent, and
reports the source as waiting if it was never built.

| Source | Files | How often they change |
| --- | --- | --- |
| `un_wpp` | World Population Prospects CSVs (hundreds of MB) | Every two years (WPP 2026 is due) |
| `worldbank_pip` | Poverty and Inequality Platform percentiles | About twice a year |
| `bps` | Small CSVs and `poverty_line.json` (committed) | Twice a year |

## How change detection works

Each builder in `pipeline/statsapp_pipeline/sources/` declares what to watch: URLs checked with an
HTTP HEAD (`WATCH` or `watch(ctx)`), hand-saved files (`MANUAL`), a release version
(`version(ctx)`) and other sources it reads (`DEPENDS`). The fingerprints live in
`state/fingerprints.json`. A rebuild that produces the same data leaves the files byte for byte
unchanged, so their hashes, and the copies on phones, stay valid. `index.json`'s `generated` time only
moves when published content changes (`state/published.json`).

## Questions are data

The question catalog in `questions/` is published with the data. A new question that uses an
existing calculation kind reaches every user the next time they open the app, without an app
update. A new kind needs an app update; older app versions hide questions they can't run. See
`questions/README.md`.

## Licenses

Every source in `data/sources.json` allows commercial use. Each dataset carries its sources, and the
app shows their credit lines and license links under every result. BPS also requires a citation
(title, access date, link) for each table, which the dataset carries in `citation`.

## Layout

```
.github/workflows/data.yml   the daily job
data/                        contract.json (dataset shapes), sources.json (licenses), manifest.json, built datasets
questions/                   the question catalog (see questions/README.md)
pipeline/                    the Python package, tests, hand-saved files
state/                       fingerprints.json, published.json, heartbeat.txt
site/                        the published output (not committed)
```
