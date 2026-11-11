"""BEA Regional Price Parities by state: the all-items price level (US = 100) for the latest year.

Read from BEA's downloadable SARPP.zip (the BEA API needs a key, the file doesn't).
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd

from ..common import PipelineError

SOURCE = "bea_rpp"
URL = "https://apps.bea.gov/regional/zip/SARPP.zip"
PAGE = "https://apps.bea.gov/regional/downloadzip.htm"
WATCH = [URL]

FIPS_USPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC",
    "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
    "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY",
}


def read_zip(path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.upper().startswith("SARPP_STATE") and n.lower().endswith(".csv")]
        if not names:
            raise PipelineError(f"No SARPP_STATE_*.csv in {path}: {z.namelist()}")
        raw = z.read(sorted(names)[-1]).decode("latin-1")
    # The file ends with a few quoted note lines (source, last updated); only rows with a GeoFIPS code are data.
    return pd.read_csv(io.StringIO(raw), dtype=str, skipinitialspace=True, on_bad_lines="skip")


def build_from(ctx, df: pd.DataFrame) -> None:
    df = df.rename(columns=lambda c: str(c).strip())
    years = [c for c in df.columns if c.isdigit()]
    if not years:
        raise PipelineError(f"No year columns in the SARPP file: {list(df.columns)}")
    year = max(years, key=int)
    df = df[pd.to_numeric(df["LineCode"], errors="coerce") == 1]  # RPPs: All items
    states = {}
    for _, row in df.iterrows():
        fips = str(row["GeoFIPS"]).strip().strip('"')
        usps = FIPS_USPS.get(fips[:2]) if len(fips) == 5 and fips.endswith("000") else None
        value = pd.to_numeric(str(row[year]).strip(), errors="coerce")
        if usps and pd.notna(value):
            states[usps] = round(float(value), 3)
    if len(states) != len(FIPS_USPS):
        raise PipelineError(f"Expected 50 states and DC in the SARPP file, found {len(states)}")
    ctx.write("us.bea.rpp", {"states": dict(sorted(states.items()))}, year=int(year),
              note=f"All-items regional price parities, {year} (US = 100).")


def build(ctx) -> None:
    # A copy saved by hand wins; otherwise download afresh (the file is small and WATCH saw it change).
    path = ctx.manual_dir / "SARPP.zip"
    if not path.exists():
        try:
            path = ctx.download(URL, "SARPP.zip", refresh=not ctx.offline)
        except PipelineError as e:
            raise PipelineError(f"{e}. Download SARPP.zip from {PAGE} and save it as {path.as_posix()}") from e
    build_from(ctx, read_zip(path))
