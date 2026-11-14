"""CDC WONDER mortality (lifetime odds by cause) and NCHS natality percentiles (public domain, NCHS/WONDER data-use rules).

us.cdc.causes
  CDC WONDER's "Underlying Cause of Death, 2018-<year>, Single Race" database (D158) through the
  WONDER API, which serves national data only and needs accept_datause_restrictions=true in each
  request. One query groups the latest year's deaths by the ICD-10 113 Cause List; a few small
  causes (air crashes, lightning, dog attacks...) get one query each for their ICD-10 codes, which
  WONDER totals itself. Queries run one after another, two minutes apart, as WONDER asks.
  Counts WONDER suppresses (0-9 deaths) are never used: such a cause is left out. Self-harm causes
  are never queried.
  Lifetime odds follow the National Safety Council's published method: one-year odds
  (population / deaths) divided by life expectancy at birth, from the NCHS US life table of the
  same year (us.nchs.lifetable, built by nchs_lifetables). Only the odds are published, not counts.

us.cdc.natality
  WONDER's natality database only gives counts in bins (500 g birth weight groups, age groups), and
  percentiles from bins would be estimates, so the percentiles are computed from the file WONDER is
  built on: the NCHS natality public-use file, every birth certificate of the year (a full count,
  not a sample), at https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/DVS/natality/Nat<year>us.zip
  with its User Guide in .../Dataset_Documentation/DVS/natality/UserGuide<year>.pdf.
  Fields used (positions from the 2025 User Guide, unchanged since 2014): DOB_YY 9-12,
  MAGER 75-76 (12 = 10-12 years, 50 = 50 and over), RESTATUS 104 (4 = foreign resident),
  LBO_REC 179 (live birth order; 1 = first), DBWT 504-507 (grams, 9999 = not stated).
  Foreign residents are left out, as in NCHS's own tables. Only national percentiles of millions of
  births are published; no record-level data leaves the pipeline.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import time
import zipfile
from html.parser import HTMLParser
from contextlib import contextmanager

import numpy as np

from ..common import USER_AGENT, PipelineError, load_json, weighted_quantiles

SOURCE = "cdc_wonder"
DEPENDS = ["nchs_lifetables"]  # us.cdc.causes divides by life expectancy at birth from us.nchs.lifetable
NATALITY = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/DVS/natality/"
MIN_LENGTH = 507  # the files hold 1345 characters a record (the 2025 guide says 1330); we read up to DBWT
FIELDS = {"year": (9, 12), "mager": (75, 76), "restatus": (104, 104), "lbo": (179, 179), "dbwt": (504, 507)}


def latest_file(ctx) -> tuple[int, str]:
    html = ctx.download(NATALITY, "natality_index.html", refresh=True).read_text(encoding="utf-8", errors="replace")
    files = {int(y): name for name, y in re.findall(r'/natality/((?i:nat)(\d{4})(?i:us)\.zip)"', html)}
    if not files:
        raise PipelineError(f"No Nat<year>us.zip in {NATALITY}")
    year = max(files)
    return year, NATALITY + files[year]


def watch(ctx) -> list[str]:
    return [latest_file(ctx)[1]]


def version(ctx) -> str:
    """The WONDER mortality database's label and vintage: they change when a new year is added."""
    form = wonder_form(ctx)
    return f"{form['dataset_label'][0]} {form['dataset_vintage'][0]}"


def _field(line: bytes, name: str) -> bytes:
    a, b = FIELDS[name]
    return line[a - 1:b]


@contextmanager
def open_member(path):
    """The single data file inside the zip, as a byte stream.

    NCHS packs these zips with Deflate64, which Python's zipfile can't read on its own: the
    zipfile-deflate64 package adds it, and the unzip command is used when that isn't installed."""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise PipelineError(f"{path.name}: expected one data file, found {names}")
        method = z.getinfo(names[0]).compress_type
    if method == 9:
        try:
            import zipfile_deflate64  # noqa: F401  (registers Deflate64 with zipfile)
        except ImportError:
            unzip = shutil.which("unzip")
            if not unzip:
                raise PipelineError(f"{path.name} uses Deflate64: pip install zipfile-deflate64, or install unzip")
            proc = subprocess.Popen([unzip, "-p", str(path), names[0]], stdout=subprocess.PIPE)
            try:
                yield proc.stdout
            finally:
                proc.stdout.close()
                if proc.wait() != 0:
                    raise PipelineError(f"unzip couldn't read {path.name}")
            return
    with zipfile.ZipFile(path) as z, z.open(names[0]) as f:
        yield f


def count_file(path) -> dict:
    """Counts by value of each measure, read straight from the zipped fixed-width file."""
    weight = np.zeros(10000, dtype=np.int64)
    age = np.zeros(100, dtype=np.int64)
    first = np.zeros(100, dtype=np.int64)
    years: set[int] = set()
    records = foreign = 0
    with open_member(path) as f:
        for line in f:
            line = line.rstrip(b"\r\n")
            if not line:
                continue
            if len(line) < MIN_LENGTH:
                raise PipelineError(f"{path.name}: a record is only {len(line)} characters long; check the User Guide")
            records += 1
            if records <= 1000:
                years.add(int(_field(line, "year")))
            if _field(line, "restatus") == b"4":
                foreign += 1
                continue
            mager = int(_field(line, "mager"))
            age[mager] += 1
            if _field(line, "lbo") == b"1":
                first[mager] += 1
            weight[int(_field(line, "dbwt"))] += 1
    if len(years) != 1:
        raise PipelineError(f"{path.name}: records from several years {sorted(years)}")
    return {"year": years.pop(), "records": records, "foreign": foreign, "weight": weight, "age": age, "first": first}


MIN_BIRTHS = 10  # NCHS data-use rule: never publish a statistic representing nine or fewer births or deaths


def quantiles_from_counts(counts: np.ndarray, digits: int) -> list:
    """101 percentiles of the values counted. The 0th and 100th would be the single lightest and
    heaviest birth (or youngest and oldest mother), so they are the 10th-lowest and 10th-highest
    values instead: each published figure then stands for at least ten births."""
    values = np.repeat(np.arange(len(counts), dtype=float), counts)
    if values.size < 2 * MIN_BIRTHS:
        raise PipelineError("Too few births to publish percentiles")
    q = weighted_quantiles(values, np.ones(values.size), digits=digits)
    q[0] = max(q[0], round(float(values[MIN_BIRTHS - 1]), digits) if digits else int(values[MIN_BIRTHS - 1]))
    q[-1] = min(q[-1], round(float(values[-MIN_BIRTHS]), digits) if digits else int(values[-MIN_BIRTHS]))
    if q[0] > q[1] or q[-1] < q[-2]:
        raise PipelineError("Too few births to publish percentiles")
    return q


def build(ctx) -> None:
    build_natality(ctx)
    build_causes(ctx)


def build_natality(ctx) -> None:
    year, url = latest_file(ctx)
    path = ctx.download(url)
    c = count_file(path)
    if c["year"] != year:
        raise PipelineError(f"{path.name} holds {c['year']} births, expected {year}")
    natality_from(ctx, c)


def natality_from(ctx, c: dict) -> None:
    weight = c["weight"].copy()
    not_stated = int(weight[9999])
    weight[9999] = 0
    if weight[:227].sum() or weight[8166:].sum():
        raise PipelineError("Birth weights outside the User Guide's 227-8165 g range: check the field positions")
    age, first = c["age"], c["first"]
    if age[:12].sum() or age[51:].sum():
        raise PipelineError("Mother's ages outside 12-50: check the field positions")
    if min(weight.sum(), first.sum()) < 1000:
        raise PipelineError("Too few births to publish percentiles")
    measures = {
        "birth_weight_g": quantiles_from_counts(weight, 0),
        "mother_age": quantiles_from_counts(age, 1),
        "first_birth_age": quantiles_from_counts(first, 1),
    }
    births = int(age.sum())
    ctx.write("us.cdc.natality", {"measures": measures}, year=c["year"],
              note=(f"All {births:,} births to US residents in {c['year']} (NCHS natality public-use file). "
                    f"Birth weight leaves out {not_stated:,} births with no weight stated. Mother's age is in completed years; "
                    "12 stands for 10-12 and 50 for 50 and over. First births are first live births. "
                    "The 0th and 100th percentiles are the 10th-lowest and 10th-highest values, so no figure stands for fewer than ten births."))


# ---------------------------------------------------------------- causes of death (CDC WONDER)

WONDER = "https://wonder.cdc.gov/controller/datarequest/D158"
PAUSE_SECONDS = 120  # WONDER: run automated queries in series; "a query every 2 minutes" lets it recover

# From the ICD-10 113 Cause List, matched on WONDER's label (the part before the ICD codes).
CAUSES_113 = {
    "heart": ("Heart disease", "Diseases of heart"),
    "cancer": ("Cancer", "Malignant neoplasms"),
    "stroke": ("Stroke", "Cerebrovascular diseases"),
    "lung": ("Chronic lung disease (such as COPD)", "Chronic lower respiratory diseases"),
    "alzheimers": ("Alzheimer disease", "Alzheimer disease"),
    "diabetes": ("Diabetes", "Diabetes mellitus"),
    "kidney": ("Kidney disease", "Nephritis, nephrotic syndrome and nephrosis"),
    "liver": ("Chronic liver disease and cirrhosis", "Chronic liver disease and cirrhosis"),
    "flu": ("Flu and pneumonia", "Influenza and pneumonia"),
    "covid": ("COVID-19", "COVID-19"),
    "sepsis": ("Sepsis", "Septicemia"),
    "car": ("Motor vehicle crash", "Motor vehicle accidents"),
    "fall": ("Fall", "Falls"),
    "poisoning": ("Accidental poisoning, including drug overdose", "Accidental poisoning and exposure to noxious substances"),
    "drowning": ("Drowning", "Accidental drowning and submersion"),
    "fire": ("Fire or smoke", "Accidental exposure to smoke, fire and flames"),
    "gun_accident": ("Accidental gun discharge", "Accidental discharge of firearms"),
    "assault": ("Assault (homicide)", "Assault (homicide)"),
}

# Small causes, by their ICD-10 codes (all unintentional injuries, so no intent filter is needed).
CAUSES_ICD = {
    "plane": ("Air or space travel accident", ["V95", "V96", "V97"]),
    "motorcycle": ("Motorcycle crash", ["V20-V29"]),
    "bicycle": ("Cycling crash", ["V10-V19"]),
    "pedestrian": ("Pedestrian accident", ["V01-V09"]),
    "choking": ("Choking on food", ["W79"]),
    "electrocution": ("Electric current", ["W85", "W86", "W87"]),
    "heat": ("Excessive natural heat", ["X30"]),
    "cold": ("Excessive natural cold", ["X31"]),
    "lightning": ("Lightning", ["X33"]),
    "dog": ("Dog attack", ["W54"]),
    "venom": ("Venomous animal or plant", [f"X{n}" for n in range(20, 30)]),
}
SELF_HARM = re.compile(r"self-harm|suicide", re.I)


class _Form(HTMLParser):
    """The default values of a WONDER request form: checked radios/boxes, selected options, hidden fields."""

    def __init__(self):
        super().__init__()
        self.values: dict[str, list[str]] = {}
        self._select = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        name = a.get("name")
        if tag == "input" and name:
            kind = (a.get("type") or "text").lower()
            if kind in ("radio", "checkbox"):
                if "checked" in a:
                    self.values.setdefault(name, []).append(a.get("value") or "")
            elif kind in ("hidden", "text"):
                self.values.setdefault(name, []).append(a.get("value") or "")
        elif tag == "select" and name:
            self._select = name
            self.values.setdefault(name, [])
        elif tag == "option" and self._select and "selected" in a:
            self.values[self._select].append(a.get("value") or "")

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None


def _post(ctx, data: dict) -> str:
    if ctx.offline:
        raise PipelineError("Can't query CDC WONDER: downloads are off")
    import requests

    r = requests.post(WONDER, data=data, headers={"User-Agent": USER_AGENT}, timeout=900)
    if r.status_code != 200:
        msg = re.search(r"<message>(.*?)</message>", r.text, re.S)
        raise PipelineError(f"CDC WONDER answered HTTP {r.status_code}: {msg.group(1).strip() if msg else r.text[:200]}")
    return r.text


def wonder_form(ctx) -> dict[str, list[str]]:
    """The request form's defaults, after accepting the data-use restrictions."""
    form = _Form()
    form.feed(_post(ctx, {"stage": "about", "action-I Agree": "I Agree"}))
    v = {k: list(dict.fromkeys(x)) for k, x in form.values.items()}
    for key in ("dataset_label", "dataset_vintage", "F_D158.V1", "F_D158.V2", "O_ucd"):
        if not v.get(key):
            raise PipelineError(f"The CDC WONDER D158 request form has no {key} field any more; check the API")
    return v


def request_xml(form: dict, **overrides) -> str:
    keep = ("B_", "M_", "F_", "I_", "O_", "V_", "VM_", "finder-stage", "stage")
    params = {k: v for k, v in form.items() if k.startswith(keep)}
    params.update({"B_2": ["*None*"], "B_3": ["*None*"], "B_4": ["*None*"], "B_5": ["*None*"], "O_javascript": ["on"],
                   "O_show_suppressed": ["true"], "O_show_zeros": ["false"], "O_title": ["hall-of-ranks"],
                   "action-Send": ["Send"], "accept_datause_restrictions": ["true"]})
    params.update({k.replace("__", "."): v if isinstance(v, list) else [v] for k, v in overrides.items()})
    out = ["<request-parameters>"]
    for k, values in params.items():
        if values:
            out.append(f"<parameter><name>{html.escape(k)}</name>" + "".join(f"<value>{html.escape(x)}</value>" for x in values) + "</parameter>")
    out.append("</request-parameters>")
    return "\n".join(out)


def parse_rows(xml: str) -> list[tuple[str, str, str]]:
    """(label, deaths, population) for each data row of a WONDER response; totals rows are skipped."""
    m = re.search(r"<data-table[^>]*>(.*?)</data-table>", xml, re.S)
    if not m:
        msg = re.findall(r"<message>(.*?)</message>", xml, re.S)
        raise PipelineError(f"CDC WONDER returned no data table: {msg[:2]}")
    rows = []
    for r in re.findall(r"<r>(.*?)</r>", m.group(1), re.S):
        label = re.search(r'<c l="([^"]*)"', r)
        values = re.findall(r'<c v="([^"]*)"', r)
        if label and len(values) >= 2:
            rows.append((html.unescape(label.group(1)).strip(), values[0], values[1]))
    return rows


def _count(text: str) -> int | None:
    """A count as a number; None when WONDER suppressed it or left it out."""
    t = text.replace(",", "").strip()
    return int(t) if t.isdigit() else None


def build_causes(ctx) -> None:
    form = wonder_form(ctx)
    year = int(form["dataset_vintage"][0])
    pause = ctx.options.get("wonder_pause", PAUSE_SECONDS)
    ctx.log(f"  CDC WONDER {form['dataset_label'][0]}: {1 + len(CAUSES_ICD)} queries for {year}, {pause}s apart")

    def query(name, **overrides):
        # Each answer is kept in the raw cache for this vintage, so a re-run doesn't query WONDER again.
        cache = ctx.raw / f"wonder_D158_{year}_{name}.xml"
        if cache.exists() and not ctx.options.get("refresh"):
            return parse_rows(cache.read_text(encoding="utf-8"))
        if query.sent:
            time.sleep(pause)
        query.sent += 1
        text = _post(ctx, {"request_xml": request_xml(form, **overrides), "accept_datause_restrictions": "true"})
        rows = parse_rows(text)
        ctx.raw.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
        return rows

    query.sent = 0
    table = query("113", B_1="D158.V4", F_D158__V1=str(year))
    coded = {}
    for cid, (_, codes) in CAUSES_ICD.items():
        rows = query(cid, B_1="D158.V1-level1", F_D158__V1=str(year), F_D158__V2=codes)
        coded[cid] = [r for r in rows if r[0].startswith(str(year))]
    path = ctx.data_dir / ctx.contract["datasets"]["us.nchs.lifetable"]["file"]
    if not path.exists():
        raise PipelineError("us.cdc.causes needs us.nchs.lifetable: build nchs_lifetables first")
    causes_from(ctx, table, coded, year, load_json(path))


def causes_from(ctx, table: list, coded: dict, year: int, lifetable: dict) -> None:
    if lifetable.get("demo") or not isinstance(lifetable.get("year"), int) or abs(lifetable["year"] - year) > 1:
        raise PipelineError(f"Needs the NCHS US life table for {year} (or a year either side); us.nchs.lifetable is for {lifetable.get('year')}")
    e0, e0_year = lifetable["data"]["tables"]["B"]["ex"][0], lifetable["year"]
    by_label, pops = {}, set()
    for label, deaths, pop in table:
        if SELF_HARM.search(label):
            continue
        by_label[re.sub(r"\s*\([^()]*\)\s*$", "", label.lstrip("#")).strip()] = deaths  # drop the trailing ICD codes
        pops.add(pop)
    for rows in coded.values():
        pops.update(p for _, _, p in rows)
    if len(pops) != 1 or _count(next(iter(pops))) is None:
        raise PipelineError(f"Expected one US population figure in the WONDER results, found {sorted(pops)[:5]}")
    population = _count(pops.pop())
    deaths, skipped = {}, []
    for cid, (_, wonder_label) in CAUSES_113.items():
        if wonder_label not in by_label:
            raise PipelineError(f"'{wonder_label}' isn't in WONDER's 113 Cause List results any more")
        n = _count(by_label[wonder_label])
        (skipped.append(cid) if n is None else deaths.__setitem__(cid, n))
    for cid, rows in coded.items():
        n = _count(rows[0][1]) if len(rows) == 1 else None
        (skipped.append(cid) if n is None else deaths.__setitem__(cid, n))
    if skipped:
        ctx.log(f"  left out (suppressed or missing): {', '.join(skipped)}")
    labels = {**{k: v[0] for k, v in CAUSES_113.items()}, **{k: v[0] for k, v in CAUSES_ICD.items()}}
    causes = {cid: {"label": labels[cid], "oneIn": round(population / n / e0)} for cid, n in deaths.items() if n >= 10}
    if "car" not in causes or len(causes) < 10:
        raise PipelineError(f"Only {len(causes)} causes came back from CDC WONDER")
    ctx.write("us.cdc.causes", {"causes": causes}, year=year,
              note=(f"Lifetime odds of dying from each cause: the {year} US resident population ({population:,}) divided by US deaths "
                    f"from that cause in {year} (CDC WONDER, underlying cause of death), divided by life expectancy at birth "
                    f"({e0:.1f} years, NCHS US life table {e0_year}). The National Safety Council's method; it assumes {year}'s "
                    "death rates for a whole lifetime."))
