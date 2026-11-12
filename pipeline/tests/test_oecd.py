"""OECD Data Explorer CSVs (csvfilewithlabels), against tiny files in the API's layout."""

import io

import pandas as pd

from statsapp_pipeline.sources import oecd

HOURS = """STRUCTURE,STRUCTURE_ID,STRUCTURE_NAME,ACTION,REF_AREA,Reference area,MEASURE,Measure,UNIT_MEASURE,Unit of measure,SEX,Sex,AGE,Age,LABOUR_FORCE_STATUS,Labour force status,WORK_PERIOD,Work period,HOURS_TYPE,Hours type,WORKER_STATUS,Worker status,WORK_TIME_ARNGMNT,Working time arrangement,AGGREGATION_OPERATION,Aggregation operation,HOUR_BANDS,Hour bands,JOB_COVERAGE,Job coverage,TIME_PERIOD,Time period,OBS_VALUE,Observation value,OBS_STATUS,Observation status,UNIT_MULT,Unit multiplier,DECIMALS,Decimals
DATAFLOW,OECD.ELS.SAE:DSD_HW@DF_AVG_ANN_HRS_WKD(1.0),Average annual hours actually worked per worker,I,DEU,Germany,HW,Hours worked,H_Y_PS,Hours per year per person,_Z,Not applicable,_Z,Not applicable,EMP,Employment,A,Annual,ACTUAL,Actual,_T,Total,_Z,Not applicable,MEAN,Mean,_Z,Not applicable,_T,Total,2024,,1334.4,,A,Normal value,,,0,Zero
DATAFLOW,OECD.ELS.SAE:DSD_HW@DF_AVG_ANN_HRS_WKD(1.0),Average annual hours actually worked per worker,I,DEU,Germany,HW,Hours worked,H_Y_PS,Hours per year per person,_Z,Not applicable,_Z,Not applicable,EMP,Employment,A,Annual,ACTUAL,Actual,_T,Total,_Z,Not applicable,MEAN,Mean,_Z,Not applicable,_T,Total,2025,,1332.2,,A,Normal value,,,0,Zero
DATAFLOW,OECD.ELS.SAE:DSD_HW@DF_AVG_ANN_HRS_WKD(1.0),Average annual hours actually worked per worker,I,DEU,Germany,HW,Hours worked,H_Y_PS,Hours per year per person,_Z,Not applicable,_Z,Not applicable,EMP,Employment,A,Annual,ACTUAL,Actual,ICSE93_1,Employees,_Z,Not applicable,MEAN,Mean,_Z,Not applicable,_T,Total,2025,,1290.0,,A,Normal value,,,0,Zero
DATAFLOW,OECD.ELS.SAE:DSD_HW@DF_AVG_ANN_HRS_WKD(1.0),Average annual hours actually worked per worker,I,COL,Colombia,HW,Hours worked,H_Y_PS,Hours per year per person,_Z,Not applicable,_Z,Not applicable,EMP,Employment,A,Annual,ACTUAL,Actual,_T,Total,_Z,Not applicable,MEAN,Mean,_Z,Not applicable,_T,Total,2024,,2219.0,,A,Normal value,,,0,Zero
DATAFLOW,OECD.ELS.SAE:DSD_HW@DF_AVG_ANN_HRS_WKD(1.0),Average annual hours actually worked per worker,I,COL,Colombia,HW,Hours worked,H_Y_PS,Hours per year per person,_Z,Not applicable,_Z,Not applicable,EMP,Employment,A,Annual,ACTUAL,Actual,_T,Total,_Z,Not applicable,MEAN,Mean,_Z,Not applicable,_T,Total,2025,,,,A,Normal value,,,0,Zero
DATAFLOW,OECD.ELS.SAE:DSD_HW@DF_AVG_ANN_HRS_WKD(1.0),Average annual hours actually worked per worker,I,RUS,Russia,HW,Hours worked,H_Y_PS,Hours per year per person,_Z,Not applicable,_Z,Not applicable,EMP,Employment,A,Annual,ACTUAL,Actual,_T,Total,_Z,Not applicable,MEAN,Mean,_Z,Not applicable,_T,Total,2020,,1874.0,,A,Normal value,,,0,Zero
DATAFLOW,OECD.ELS.SAE:DSD_HW@DF_AVG_ANN_HRS_WKD(1.0),Average annual hours actually worked per worker,I,OECD,OECD,HW,Hours worked,H_Y_PS,Hours per year per person,_Z,Not applicable,_Z,Not applicable,EMP,Employment,A,Annual,ACTUAL,Actual,_T,Total,_Z,Not applicable,MEAN,Mean,_Z,Not applicable,_T,Total,2025,,1736.1,,A,Normal value,,,0,Zero
"""

HEAD = "STRUCTURE,STRUCTURE_ID,STRUCTURE_NAME,ACTION,REF_AREA,Reference area,MEASURE,Measure,SEX,Sex,OBS_VALUE,Observation value,DECIMALS,Decimals,OBS_STATUS,Observation status,UNIT_MEASURE,Unit of measure,UNIT_MULT,Unit multiplier\n"
LABELS = {"LEI": "Leisure", "PCA": "Personal care", "UPW": "Unpaid work", "PAW": "Paid work or study", "OTH": "Other"}


def tu_row(iso, name, m, sex, v, status="A"):
    return f"DATAFLOW,OECD.WISE.INE:DSD_TIME_USE@DF_TIME_USE(1.0),Time use,I,{iso},{name},{m},{LABELS[m]},{sex},x,{v},,0,Zero,{status},x,MN_D,Minutes per day,0,Units\n"


def time_use():
    rows = [tu_row("USA", "United States", m, "_T", v, "D" if m == "PAW" else "A") for m, v in
            {"LEI": 279.86, "PCA": 664.04, "UPW": 197.12, "PAW": 278.21, "OTH": 20.77}.items()]
    rows += [tu_row("USA", "United States", "LEI", "F", 260.0)]
    rows += [tu_row("CHN", "China (People’s Republic of)", m, "_T", v) for m, v in {"LEI": 227.8, "PCA": 693.5, "UPW": 163.9, "PAW": 339.8, "OTH": 15.0}.items()]
    rows += [tu_row("XYZ", "Partial", "LEI", "_T", 100.0)]
    return pd.read_csv(io.StringIO(HEAD + "".join(rows)), dtype={"REF_AREA": str, "MEASURE": str})


def test_hours_newest_year_per_member_and_time_use(make_ctx, read):
    ctx = make_ctx("oecd")
    oecd.build_from(ctx, pd.read_csv(io.StringIO(HOURS), dtype={"REF_AREA": str, "MEASURE": str}), time_use())
    h = read(make_ctx.data, "world.oecd.hours")
    assert h["year"] == "2024-2025"
    assert h["data"]["countries"] == {"DEU": {"name": "Germany", "hours": 1332, "year": 2025},
                                      "COL": {"name": "Colombia", "hours": 2219, "year": 2024}}  # Russia and the OECD total are not members
    t = read(make_ctx.data, "world.oecd.time_use")["data"]["countries"]
    assert set(t) == {"USA", "CHN"}  # a country missing categories is left out
    assert t["USA"] == {"name": "United States", "minutes": {"leisure": 280, "personalCare": 664, "unpaidWork": 197, "paidWork": 278, "other": 21},
                        "definitionDiffers": True}
    assert "definitionDiffers" not in t["CHN"] and t["CHN"]["minutes"]["personalCare"] == 694


def test_housing_is_not_written(make_ctx):
    ctx = make_ctx("oecd")
    oecd.build_from(ctx, pd.read_csv(io.StringIO(HOURS), dtype={"REF_AREA": str, "MEASURE": str}), time_use())
    assert "world.oecd.housing" not in ctx.written
