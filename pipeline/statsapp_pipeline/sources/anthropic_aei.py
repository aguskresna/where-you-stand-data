"""Anthropic Economic Index (Hugging Face) with O*NET task statements: AI use by task and by country.

The Economic Index data is CC BY (dataset card, "Data released under CC-BY"). Each release lives in
its own release_YYYY_MM_DD/ folder; the newest one with an aei_claude_ai_*.csv file is used, and its
newest calendar month. That file already carries the task text (node_name) for every O*NET task ID,
but not which occupation each task belongs to, so O*NET Task Statements supplies the occupation and
the full list of tasks per occupation (O*NET database content is CC BY 4.0).

us.aei.tasks: for every O*NET-SOC occupation, the share of its listed tasks that have a published
row in the newest month (global Claude.ai usage), and those tasks with their share of all Claude.ai
conversations. Tasks the AEI reports under task IDs that the current O*NET release no longer lists
are left out (they can't be placed in an occupation).

world.aei.country: the Anthropic AI Usage Index (usage share / working-age population share) for
every country published in the newest month, with its rank.
"""

from __future__ import annotations

import re

import pandas as pd

from ..common import PipelineError

SOURCE = "anthropic_aei"
REPO = "Anthropic/EconomicIndex"
API = f"https://huggingface.co/api/datasets/{REPO}"
FILES = f"https://huggingface.co/datasets/{REPO}/resolve/main/"
# Country names as published by Anthropic alongside the September 2025 release.
NAMES_PATH = "release_2025_09_15/data/intermediate/iso_country_codes.csv"
ONET_PAGE = "https://www.onetcenter.org/database.html"
ONET_FILES = "https://www.onetcenter.org/dl_files/database/"

AEI_COLUMNS = ["date_start", "date_end", "geo_id", "geo_level", "category_name", "hierarchy_level", "metric_id", "value", "node_name", "node_external_id"]
ONET_COLUMNS = ["O*NET-SOC Code", "Title", "Task ID", "Task"]


def _sha(ctx) -> str:
    body = ctx.fetch_json(API)
    sha = body.get("sha") if isinstance(body, dict) else None
    if not sha:
        raise PipelineError(f"No commit sha in {API}")
    return sha


def onet_version(ctx) -> str:
    """The current O*NET database version ('31_0') from the download page."""
    page = ctx.download(ONET_PAGE, "onet_database.html", refresh=not ctx.offline).read_text(encoding="utf-8", errors="replace")
    found = sorted({(int(a), int(b)) for a, b in re.findall(r"db_(\d+)_(\d+)_csv/task_statements\.csv", page)})
    if not found:
        raise PipelineError(f"No Task Statements link on {ONET_PAGE}")
    a, b = found[-1]
    return f"{a}_{b}"


def version(ctx) -> str:
    """The dataset's latest commit on Hugging Face, plus the current O*NET release."""
    return f"{_sha(ctx)} onet {onet_version(ctx)}"


def latest_release_file(paths: list[str]) -> str:
    """The aei_claude_ai_*.csv of the newest release_YYYY_MM_DD folder that has one."""
    best = None
    for p in paths:
        m = re.match(r"(release_(\d{4})_(\d{2})_(\d{2}))/data/aei_claude_ai_[^/]*\.csv$", p)
        if m and (best is None or m.group(1) > best[0]):
            best = (m.group(1), p)
    if not best:
        raise PipelineError("No release_*/data/aei_claude_ai_*.csv file in the dataset")
    return best[1]


def build(ctx) -> None:
    tree = ctx.fetch_json(f"{API}/tree/main", {"recursive": "1"})
    path = latest_release_file([e["path"] for e in tree if e.get("type") == "file"])
    sha = _sha(ctx)
    release = path.split("/")[0]
    aei = pd.read_csv(ctx.download(FILES + path, f"{release}_{path.rsplit('/', 1)[-1]}"), dtype={"node_external_id": str, "geo_id": str},
                      keep_default_na=False, na_values=[""])
    names = pd.read_csv(ctx.download(FILES + NAMES_PATH, "iso_country_codes.csv"), keep_default_na=False)
    ver = onet_version(ctx)
    onet = pd.read_csv(ctx.download(f"{ONET_FILES}db_{ver}_csv/task_statements.csv", f"task_statements_{ver}.csv"), dtype={"Task ID": str})
    build_from(ctx, aei, names, onet, release=release, onet_release=ver.replace("_", "."), sha=sha)


def _check(df, columns, what):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise PipelineError(f"{what} has a new layout: missing {missing}; found {list(df.columns)}")


def build_from(ctx, aei: pd.DataFrame, names: pd.DataFrame, onet: pd.DataFrame, *, release: str, onet_release: str, sha: str = "") -> None:
    _check(aei, AEI_COLUMNS, "The AEI file")
    _check(onet, ONET_COLUMNS, "O*NET Task Statements")
    _check(names, ["iso_alpha_3", "country_name"], "iso_country_codes.csv")
    month = aei["date_start"].max()
    rows = aei[aei["date_start"] == month]
    period = str(month)[:7]
    cite = {"title": f"Anthropic Economic Index, {release.replace('_', ' ', 1).replace('_', '-')}", "url": f"https://huggingface.co/datasets/{REPO}/tree/main/{release}",
            **({"commit": sha} if sha else {})}

    # ------------------------------------------------ tasks by occupation
    tasks = rows[(rows["geo_level"] == "global") & (rows["category_name"] == "onet") & (rows["hierarchy_level"] == 0) & (rows["metric_id"] == "pct")]
    share = dict(zip(tasks["node_external_id"].astype(str), tasks["value"].astype(float) / 100))
    if not share:
        raise PipelineError(f"No global task rows for {month}")
    onet = onet.dropna(subset=["Task ID"]).copy()
    onet["Task ID"] = onet["Task ID"].astype(str).str.replace(r"\.0$", "", regex=True)
    occupations = {}
    for code, g in onet.groupby("O*NET-SOC Code", sort=True):
        used = g[g["Task ID"].isin(share)]
        listed = [[t, round(share[i], 6)] for i, t in zip(used["Task ID"], used["Task"])]
        listed.sort(key=lambda r: (-r[1], r[0]))
        occupations[code] = {"title": g["Title"].iloc[0], "taskShare": round(len(used) / len(g), 4), "tasks": listed}
    unplaced = set(share) - set(onet["Task ID"])
    if len(unplaced) > 0.05 * len(share):
        raise PipelineError(f"{len(unplaced)} of {len(share)} AEI task IDs aren't in O*NET {onet_release}: the releases don't match")
    ctx.write("us.aei.tasks", {"occupations": occupations}, year=period, citation=cite,
              note=f"Claude.ai conversations in {period} (Anthropic Economic Index {release}), matched to O*NET {onet_release} task statements. "
                   "taskShare is the share of an occupation's listed tasks with a published usage figure; each task's figure is its share of "
                   f"all conversations. {len(unplaced)} task IDs not in O*NET {onet_release} are left out.")

    # ------------------------------------------------ countries
    c = rows[(rows["geo_level"] == "country") & (rows["category_name"] == "overall") & (rows["metric_id"] == "usage_per_capita_index")]
    label = dict(zip(names["iso_alpha_3"], names["country_name"]))
    c = c[c["geo_id"].isin(label)].sort_values(["value", "geo_id"], ascending=[False, True])
    if c.empty:
        raise PipelineError(f"No country usage index rows for {month}")
    ranks = c["value"].rank(method="min", ascending=False).astype(int)
    countries = {iso: {"name": label[iso], "index": round(float(v), 2), "rank": int(r)} for iso, v, r in zip(c["geo_id"], c["value"], ranks)}
    ctx.write("world.aei.country", {"countries": dict(sorted(countries.items())), "count": len(countries)}, year=period, citation=cite,
              note=f"Anthropic AI Usage Index for Claude.ai in {period}: a country's share of usage divided by its share of the world's "
                   "working-age (15-64) population. Countries below Anthropic's publication threshold are not listed.")
