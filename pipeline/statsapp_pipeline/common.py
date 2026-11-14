"""Shared plumbing: paths, the dataset contract, downloads, grouping helpers, and writing datasets.

Every builder gets a Context. It downloads raw files into pipeline/raw/<source>/ (kept as a cache),
finds hand-downloaded files in pipeline/manual/<source>/, and writes each dataset as a JSON envelope
into backend/data/ while recording it in backend/data/manifest.json.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"  # built datasets plus contract.json, sources.json, manifest.json
QUESTIONS_DIR = ROOT / "questions"
STATE_DIR = ROOT / "state"
PIPELINE_DIR = ROOT / "pipeline"
RAW_DIR = PIPELINE_DIR / "raw"
MANUAL_DIR = PIPELINE_DIR / "manual"

USER_AGENT = "hall-of-ranks-data/0.1 (+https://github.com/aguskresna/hall-of-ranks-data)"
MIN_RECORDS = 50  # survey records a group needs before we publish figures for it

# Keep these in step with app/lib/engine/groups.dart and backend/questions/modes.json.
AGE_BANDS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
SCF_BANDS = ["<35", "35-44", "45-54", "55-64", "65-74", "75+"]
HOUSEHOLDER_BANDS = ["<25", "25-34", "35-44", "45-54", "55-64", "65+"]
EDU_BANDS = ["25-34", "35-44", "45-54", "55-64", "65+"]


class PipelineError(Exception):
    """A problem the person running the pipeline can fix (missing file, bad layout, refused license)."""


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_contract(data_dir: Path = DATA_DIR) -> dict:
    return load_json(data_dir / "contract.json")


def load_sources(data_dir: Path = DATA_DIR) -> dict:
    return load_json(data_dir / "sources.json")["sources"]


# ---------------------------------------------------------------- numbers


def band_of(ages, bands: list[str]) -> np.ndarray:
    """The band label for each age ('25-34', '65+', '<35'), or '' when no band fits."""
    a = np.asarray(ages, dtype=float)
    out = np.full(a.shape, "", dtype=object)
    for b in bands:
        if b.startswith("<"):
            m = a < float(b[1:])
        elif b.endswith("+"):
            m = a >= float(b[:-1])
        else:
            lo, hi = (float(x) for x in b.split("-"))
            m = (a >= lo) & (a <= hi)
        out[(out == "") & m] = b
    return out


def weighted_quantiles(values, weights, n: int = 101, digits: int = 0) -> list[float]:
    """n thresholds (percentiles 0..100 by default) of a weighted distribution, ascending.

    Uses the midpoint of each record's weight, so a single record of weight w covers its own share.
    """
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    keep = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[keep], w[keep]
    if v.size == 0:
        raise PipelineError("No values to compute quantiles from")
    order = np.argsort(v, kind="mergesort")
    v, w = v[order], w[order]
    cum = (np.cumsum(w) - 0.5 * w) / w.sum()
    q = np.interp(np.linspace(0, 1, n), cum, v)
    q = np.maximum.accumulate(q)
    return [round_to(x, digits) for x in q]


def weighted_median(values, weights) -> float:
    return weighted_quantiles(values, weights, n=3, digits=6)[1]


def weighted_share(mask, weights) -> float:
    m = np.asarray(mask, dtype=bool)
    w = np.asarray(weights, dtype=float)
    total = w.sum()
    return float(w[m].sum() / total) if total > 0 else float("nan")


def round_to(x: float, digits: int = 0):
    if x is None or not math.isfinite(x):
        return None
    if digits <= 0:
        return int(round(float(x), digits))
    return round(float(x), digits)


def by_groups(df, dims: dict[str, list], fn: Callable, min_records: int = MIN_RECORDS) -> dict[str, Any]:
    """fn(rows) for every combination of the given columns, including '*' (everyone) for each.

    dims maps a column to the values to report; groups with fewer than min_records rows are left out,
    and the app falls back to a broader group. Keys join the parts with '|', in the order of dims.
    """
    names = list(dims)
    allowed = {k: {str(v) for v in vals} for k, vals in dims.items()}
    out: dict[str, Any] = {}
    for keep in itertools.product([True, False], repeat=len(names)):
        cols = [n for n, k in zip(names, keep) if k]
        if cols:
            groups = df.groupby(cols, observed=True, sort=True)
        else:
            groups = [((), df)]
        for key, rows in groups:
            if not isinstance(key, tuple):
                key = (key,)
            if len(rows) < min_records:
                continue
            it = iter(key)
            parts = [str(next(it)) if k else "*" for k in keep]
            if any(p != "*" and p not in allowed[n] for p, n in zip(parts, names)):
                continue
            out["|".join(parts)] = fn(rows)
    return out


def clean(obj):
    """JSON-safe copy: numpy scalars to Python, NaN and infinity to None."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [clean(v) for v in obj.tolist()]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# ---------------------------------------------------------------- context


class Context:
    """What a builder needs: where files live, how to fetch them, and how to write datasets."""

    def __init__(
        self,
        source_id: str,
        *,
        data_dir: Path = DATA_DIR,
        raw_dir: Path = RAW_DIR,
        manual_dir: Path = MANUAL_DIR,
        options: dict | None = None,
        min_records: int = MIN_RECORDS,
        today: dt.date | None = None,
        log: Callable[[str], None] = print,
        offline: bool = False,
    ):
        self.source_id = source_id
        self.data_dir = Path(data_dir)
        self.raw = Path(raw_dir) / source_id
        self.manual_dir = Path(manual_dir) / source_id
        self.options = options or {}
        self.min_records = min_records
        self.today = today or dt.date.today()
        self.log = log
        self.offline = offline
        self.contract = load_contract(self.data_dir)
        self.sources = load_sources(self.data_dir)
        self.written: list[str] = []
        # Datasets (and 'id~shard' shards) whose content changed in this run.
        self.changed: list[str] = []
        self._shards: dict[str, list[str]] = {}

    # -------------------------------------------------- files in

    def download(self, url: str, name: str | None = None, *, refresh: bool = False) -> Path:
        """Downloads url into the raw cache (once) and returns the local path."""
        name = name or url.rstrip("/").split("/")[-1].split("?")[0]
        path = self.raw / name
        if path.exists() and not refresh:
            return path
        if self.offline:
            raise PipelineError(f"{name} isn't in {self.raw} and downloads are off")
        import requests

        self.raw.mkdir(parents=True, exist_ok=True)
        self.log(f"  downloading {url}")
        with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=120) as r:
            if r.status_code != 200:
                raise PipelineError(f"{url} returned HTTP {r.status_code}")
            if _is_html_instead_of_file(name, r.headers):
                raise PipelineError(f"{url} returned a web page instead of the file (moved, not published yet, or refused)")
            fd, tmp = tempfile.mkstemp(dir=self.raw, prefix=".part-")
            with os.fdopen(fd, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        os.replace(tmp, path)
        return path

    def head(self, url: str) -> str:
        """Status, ETag, Last-Modified and size of a URL, to spot new releases without downloading."""
        if self.offline:
            raise PipelineError(f"Can't check {url}: downloads are off")
        import requests

        r = requests.head(url, headers={"User-Agent": USER_AGENT}, allow_redirects=True, timeout=60)
        if r.status_code in (403, 405, 501):  # some servers refuse HEAD; read the headers of a GET instead
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, allow_redirects=True, timeout=60, stream=True)
            r.close()
        h = r.headers
        return f"{r.status_code} {h.get('ETag', '')} {h.get('Last-Modified', '')} {h.get('Content-Length', '')}"

    def exists(self, url: str) -> bool:
        """True when url serves the file itself (some servers answer a missing file with a 200 web page)."""
        if self.offline:
            raise PipelineError(f"Can't check {url}: downloads are off")
        import requests

        r = requests.head(url, headers={"User-Agent": USER_AGENT}, allow_redirects=True, timeout=60)
        if r.status_code in (403, 405, 501):
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, allow_redirects=True, timeout=60, stream=True)
            r.close()
        return r.status_code == 200 and not _is_html_instead_of_file(url.split("?")[0], r.headers)

    def fetch_json(self, url: str, params: dict | None = None) -> Any:
        if self.offline:
            raise PipelineError(f"Can't fetch {url}: downloads are off")
        import requests

        r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
        if r.status_code != 200:
            raise PipelineError(f"{r.url} returned HTTP {r.status_code}")
        return r.json()

    def manual(self, name: str, how: str) -> Path:
        """A file the person downloads by hand, from pipeline/manual/<source>/ (or the raw cache)."""
        for folder in (self.manual_dir, self.raw):
            path = folder / name
            if path.exists():
                return path
        raise PipelineError(f"Missing {(self.manual_dir / name).as_posix()}. {how}")

    def download_or_manual(self, url: str, name: str, page: str) -> Path:
        """Downloads a file, or uses a copy saved by hand if the download fails."""
        for folder in (self.manual_dir, self.raw):
            if (folder / name).exists():
                return folder / name
        try:
            return self.download(url, name)
        except Exception as e:  # network refused, moved file, ...
            raise PipelineError(
                f"Couldn't download {url} ({e}). Download it from {page} and save it as {(self.manual_dir / name).as_posix()}"
            ) from e

    # -------------------------------------------------- files out

    def spec(self, dataset_id: str) -> dict:
        spec = self.contract["datasets"].get(dataset_id)
        if not spec:
            raise PipelineError(f"{dataset_id} isn't in the contract")
        if self.source_id not in spec["sources"]:
            raise PipelineError(f"{dataset_id} doesn't come from {self.source_id}")
        return spec

    def write(self, dataset_id: str, data: dict, *, year, note: str | None = None, citation: dict | None = None, shard: str | None = None) -> Path:
        """Writes one dataset (or one shard of it) as an envelope and records it in the manifest."""
        spec = self.spec(dataset_id)
        if spec.get("sharded") and not shard:
            raise PipelineError(f"{dataset_id} is sharded: pass shard=")
        rel = spec["file"].replace("{shard}", shard or "")
        envelope = {
            "id": dataset_id,
            "kind": spec["kind"],
            "sources": spec["sources"],
            "year": year,
            "built": _now(),
            "demo": False,
            **({"note": note} if note else {}),
            **({"citation": citation} if citation else {}),
            "data": clean(data),
        }
        path = self.data_dir / rel
        old = _read_json(path)
        if old is not None and _without(old, "built") == _without(envelope, "built"):
            # Same content as last time: keep the file byte for byte, so its hash (and the app's copy) stays valid.
            envelope["built"] = old.get("built", envelope["built"])
        else:
            write_json_atomic(path, envelope)
            self.changed.append(f"{dataset_id}~{shard}" if shard else dataset_id)
        if shard:
            self._shards.setdefault(dataset_id, []).append(shard)
        else:
            self._record(dataset_id, spec, year, built=envelope["built"])
        return path

    def finish_shards(self, dataset_id: str, year) -> None:
        """Records a sharded dataset in the manifest once all its shards are written."""
        spec = self.spec(dataset_id)
        shards = sorted(set(self._shards.get(dataset_id, [])))
        if not shards:
            raise PipelineError(f"No shards were written for {dataset_id}")
        manifest_path = self.data_dir / "manifest.json"
        prev = (load_json(manifest_path) if manifest_path.exists() else {}).get("datasets", {}).get(dataset_id) or {}
        unchanged = not any(c.startswith(dataset_id + "~") for c in self.changed) and prev.get("shards") == shards and prev.get("year") == year
        self._record(dataset_id, spec, year, shards=shards, built=prev.get("built") if unchanged else None)

    def _record(self, dataset_id: str, spec: dict, year, shards: list[str] | None = None, built: str | None = None) -> None:
        manifest_path = self.data_dir / "manifest.json"
        manifest = load_json(manifest_path) if manifest_path.exists() else {"datasets": {}}
        entry = {
            "built": built or _now(),
            "file": spec["file"],
            "sources": spec["sources"],
            "year": year,
        }
        if shards is not None:
            entry["shards"] = shards
        datasets = manifest.setdefault("datasets", {})
        if datasets.get(dataset_id) != entry:
            datasets[dataset_id] = entry
            manifest["datasets"] = dict(sorted(datasets.items()))
            write_json_atomic(manifest_path, manifest, indent=2)
        self.written.append(dataset_id)
        self.log(f"  wrote {dataset_id}" if dataset_id in self.changed or shards is not None else f"  {dataset_id} unchanged")


def _is_html_instead_of_file(name: str, headers) -> bool:
    """A web page served where a data file (zip, csv, parquet, xpt, ...) was expected."""
    kind = str(headers.get("Content-Type", "")).lower()
    return kind.startswith("text/html") and not name.lower().endswith((".html", ".htm", ".aspx"))


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _without(d: dict, key: str) -> dict:
    return {k: v for k, v in d.items() if k != key}


def write_json_atomic(path: Path, obj: Any, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, allow_nan=False, indent=indent, separators=None if indent else (",", ":"))
        f.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def latest(df, column: str = "date"):
    """Rows for the most recent value of a date column (no-op if the column is missing)."""
    if column not in df.columns:
        return df
    return df[df[column] == df[column].max()]


def pick_column(df, candidates: Iterable[str], what: str) -> str:
    """The first of the candidate column names present in df, case-insensitively."""
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    raise PipelineError(f"Expected a {what} column (one of {list(candidates)}); found {list(df.columns)}")
