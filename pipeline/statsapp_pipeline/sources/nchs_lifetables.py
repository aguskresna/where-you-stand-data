"""NCHS United States life tables and U.S. State Life Tables (US federal public domain).

Both are National Vital Statistics Reports whose tables NCHS also publishes as Excel files on
https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/NVSR/<volume>-<number>/:
  - United States Life Tables, <year>: Table01.xlsx (total), Table02.xlsx (males), Table03.xlsx (females)
  - U.S. State Life Tables, <year>:   <USPS>1.xlsx (total), <USPS>2.xlsx (males), <USPS>3.xlsx (females)
Each sheet is a complete life table, ages 0-1 ... 99-100 and "100 and over", with columns
qx, lx, dx, Lx, Tx, ex. The newest report folder of each kind is found from the directory listing and
each table's own title ("Life table for the total population: United States, 2024").
"""

from __future__ import annotations

import re

from ..common import PipelineError

SOURCE = "nchs_lifetables"
NVSR = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/NVSR/"
LOOK_BACK = 12  # report folders to search, newest first, for each kind of table
US_FILES = {"B": "Table01.xlsx", "M": "Table02.xlsx", "F": "Table03.xlsx"}
STATE_SUFFIX = {"B": "1", "M": "2", "F": "3"}
TITLE_WORDS = {"B": "total population", "M": "males", "F": "females"}
STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA",
    "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX",
    "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


# ---------------------------------------------------------------- finding the newest reports


def _listing(ctx, url: str, name: str) -> str:
    path = ctx.download(url, name, refresh=True)
    return path.read_text(encoding="utf-8", errors="replace")


def report_folders(html: str) -> list[str]:
    """NVSR report folders ('75-05', '68_12', ...) in the directory listing, newest first."""
    found = set(re.findall(r'/NVSR/(\d+[-_]\d+)/', html, flags=re.I))
    return sorted(found, key=lambda f: tuple(int(x) for x in re.split(r"[-_]", f)), reverse=True)


def folder_files(html: str) -> list[str]:
    return re.findall(r'/NVSR/\d+[-_]\d+/([^/"]+\.xlsx)"', html, flags=re.I)


def version(ctx) -> str:
    """The list of NVSR report folders: a new life table report adds one."""
    return " ".join(report_folders(_listing(ctx, NVSR, "nvsr_index.html")))


def find_reports(ctx) -> tuple[str, dict[str, str], str, dict[str, str]]:
    """(US folder, its files by name lowercase, state folder, its files) for the newest reports of each kind."""
    us = state = None
    us_files: dict[str, str] = {}
    state_files: dict[str, str] = {}
    for folder in report_folders(_listing(ctx, NVSR, "nvsr_index.html"))[:LOOK_BACK]:
        files = {f.lower(): f for f in folder_files(_listing(ctx, f"{NVSR}{folder}/", f"nvsr_{folder}.html"))}
        if us is None and all(n.lower() in files for n in US_FILES.values()):
            path = ctx.download(f"{NVSR}{folder}/{files['table01.xlsx']}", f"{folder}_Table01.xlsx")
            if re.search(r"life table for the total population: united states", read_title(path), re.I):
                us, us_files = folder, files
        if state is None and "ak1.xlsx" in files and "ca1.xlsx" in files:
            state, state_files = folder, files
        if us and state:
            break
    if not us or not state:
        raise PipelineError(f"Couldn't find the newest {'US' if not us else 'state'} life table report in {NVSR}")
    return us, us_files, state, state_files


# ---------------------------------------------------------------- reading one table


def read_title(path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        for row in wb.worksheets[0].iter_rows(values_only=True):
            for v in row:
                if isinstance(v, str) and v.strip():
                    return v.strip()
    finally:
        wb.close()
    return ""


def read_table(path) -> dict:
    """{title, year, ages, lx, ex} from one NCHS complete life table sheet."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        rows = list(wb.worksheets[0].iter_rows(values_only=True))
    finally:
        wb.close()
    title = next((str(r[0]).strip() for r in rows if r and isinstance(r[0], str) and r[0].strip()), "")
    m = re.search(r",\s*((?:19|20)\d\d)\s*$", title)
    if not m:
        raise PipelineError(f"{path.name}: no year in the title {title!r}")
    head = next((i for i, r in enumerate(rows) if r and "qx" in [str(v).strip() for v in r if v is not None]), None)
    if head is None:
        raise PipelineError(f"{path.name}: no qx/lx/ex header row")
    names = [str(v).strip() if v is not None else "" for v in rows[head]]
    try:
        i_lx, i_ex = names.index("lx"), names.index("ex")
    except ValueError as e:
        raise PipelineError(f"{path.name}: expected lx and ex columns, found {names}") from e
    ages, lx, ex = [], [], []
    for r in rows[head + 1:]:
        label = str(r[0]).strip() if r and r[0] is not None else ""
        a = re.match(r"^(\d+)\D", label + " ")
        if not a or r[i_lx] is None or r[i_ex] is None:
            continue
        ages.append(int(a.group(1)))
        lx.append(float(r[i_lx]))
        ex.append(float(r[i_ex]))
    if ages != list(range(101)):
        raise PipelineError(f"{path.name}: expected single ages 0..100, found {ages[:3]}...{ages[-3:]} ({len(ages)} rows)")
    if not re.search(r"100 and (over|older)", str(rows[head + 101][0]), re.I):
        raise PipelineError(f"{path.name}: the last age row isn't '100 and over'")
    return {"title": title, "year": int(m.group(1)), "ages": ages, "lx": lx, "ex": ex}


def sex_of(title: str) -> str | None:
    """B, M or F from a table title such as 'Life table for females: Alaska, 2022'."""
    m = re.search(r"life table for (?:the )?(total population|males|females):", title, re.I)
    return {"total population": "B", "males": "M", "females": "F"}[m.group(1).lower()] if m else None


def _check(t: dict, sex: str, place: str, name: str) -> None:
    if sex_of(t["title"]) != sex or place.lower() not in t["title"].lower():
        raise PipelineError(f"{name}: expected the {TITLE_WORDS[sex]} table for {place}, found {t['title']!r}")


# ---------------------------------------------------------------- building


def _report(folder: str) -> str:
    """' (NVSR vol. 75, no. 5)' for the folder '75-05'."""
    parts = re.split(r"[-_]", folder) if folder else []
    return f" (NVSR vol. {int(parts[0])}, no. {int(parts[1])})" if len(parts) == 2 else ""


def build(ctx) -> None:
    us, us_files, state, state_files = find_reports(ctx)
    us_paths = {s: ctx.download(f"{NVSR}{us}/{us_files[n.lower()]}", f"{us}_{n}") for s, n in US_FILES.items()}
    codes = sorted({f[:2].upper() for f in state_files if re.fullmatch(r"[a-z]{2}1\.xlsx", f)})
    state_paths = {}
    for st in codes:
        state_paths[st] = {}
        for s, suffix in STATE_SUFFIX.items():
            name = state_files.get(f"{st.lower()}{suffix}.xlsx")
            if not name:
                raise PipelineError(f"{state}: {st}{suffix}.xlsx is missing")
            state_paths[st][s] = ctx.download(f"{NVSR}{state}/{name}", f"{state}_{name}")
    build_from(ctx, us_paths, state_paths, us_report=us, state_report=state)


def build_from(ctx, us_paths: dict, state_paths: dict, us_report: str = "", state_report: str = "") -> None:
    tables, years = {}, set()
    for sex, path in us_paths.items():
        t = read_table(path)
        _check(t, sex, "United States", path.name)
        years.add(t["year"])
        tables[sex] = {"ages": t["ages"], "lx": [round(v) for v in t["lx"]], "ex": [round(v, 3) for v in t["ex"]]}
    if set(tables) != {"B", "M", "F"} or len(years) != 1:
        raise PipelineError(f"Expected total, male and female US tables for one year, found {sorted(tables)} for {sorted(years)}")
    year = years.pop()
    ctx.write("us.nchs.lifetable", {"tables": tables}, year=year,
              note=f"United States Life Tables, {year}{_report(us_report)}. Period life tables; the last age is 100 and over.")

    states, years = {}, set()
    for st, paths in sorted(state_paths.items()):
        if st not in STATES:
            raise PipelineError(f"Unexpected state code {st}")
        e0 = {}
        for sex, path in paths.items():
            t = read_table(path)
            if sex_of(t["title"]) != sex:
                raise PipelineError(f"{path.name}: expected the {TITLE_WORDS[sex]} table, found {t['title']!r}")
            years.add(t["year"])
            e0[sex] = round(t["ex"][0], 3)
        states[st] = {k: e0[k] for k in ("B", "M", "F")}
    if len(states) != len(STATES) or len(years) != 1:
        raise PipelineError(f"Expected the 50 states and DC for one year, found {len(states)} for {sorted(years)}")
    state_year = years.pop()
    ctx.write("us.nchs.state_e0", {"states": states}, year=state_year,
              note=f"Life expectancy at birth from U.S. State Life Tables, {state_year}{_report(state_report)}.")
