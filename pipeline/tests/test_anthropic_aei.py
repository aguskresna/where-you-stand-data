"""Anthropic Economic Index + O*NET task statements, against tiny files in the publishers' layouts."""

import io

import pandas as pd
import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import anthropic_aei

AEI = """date_start,date_end,geo_id,geo_level,category_name,hierarchy_level,metric_id,value,node_name,node_external_id
2026-04-01,2026-05-01,GLOBAL,global,onet,0,pct,9.99,"Old month task.",8823
2026-04-01,2026-05-01,AUS,country,overall,0,usage_per_capita_index,9.0,Overall,
2026-05-01,2026-06-01,GLOBAL,global,onet,0,pct,0.59,"Confer with board members, organization officials, or staff members to discuss issues, coordinate activities, or resolve problems.",8824
2026-05-01,2026-06-01,GLOBAL,global,onet,0,pct,1.25,"Prepare budgets for approval, including those for funding or implementation of programs.",8827
2026-05-01,2026-06-01,GLOBAL,global,onet,0,pct,0.0,"Write code.",16960
2026-05-01,2026-06-01,GLOBAL,global,onet,1,pct,4.2,"Advise others on business or operational matters.",4.A.4.b.6.I05.D10
2026-05-01,2026-06-01,ZA-WC,subregion,onet,0,pct,0.4,"Prepare budgets for approval, including those for funding or implementation of programs.",8823
2026-05-01,2026-06-01,AUS,country,overall,0,usage_per_capita_index,6.4,Overall,
2026-05-01,2026-06-01,SGP,country,overall,0,usage_per_capita_index,5.81,Overall,
2026-05-01,2026-06-01,USA,country,overall,0,usage_per_capita_index,3.87,Overall,
2026-05-01,2026-06-01,USA,country,overall,0,usage_pct,21.6,Overall,
2026-05-01,2026-06-01,GLOBAL,global,overall,0,usage_per_capita_index,1.0,Overall,
"""

NAMES = """iso_alpha_2,iso_alpha_3,country_name
AU,AUS,Australia
SG,SGP,Singapore
US,USA,United States
NA,NAM,Namibia
"""

ONET = """O*NET-SOC Code,Title,Task ID,Task,Task Type,Incumbents Responding,Date,Domain Source
11-1011.00,Chief Executives,8823,"Direct or coordinate an organization's financial or budget activities to fund operations, maximize investments, or increase efficiency.",Core,95,08/2023,Incumbent
11-1011.00,Chief Executives,8824,"Confer with board members, organization officials, or staff members to discuss issues, coordinate activities, or resolve problems.",Core,95,08/2023,Incumbent
11-1011.00,Chief Executives,8827,"Prepare budgets for approval, including those for funding or implementation of programs.",Core,95,08/2023,Incumbent
11-1011.00,Chief Executives,8828,"Analyze operations to evaluate performance of a company or its staff.",Core,95,08/2023,Incumbent
15-1252.00,Software Developers,16960,"Write code.",Core,30,08/2024,Incumbent
47-2111.00,Electricians,2176,"Install wiring.",Core,40,08/2024,Incumbent
"""


def frames(aei=AEI):
    return (pd.read_csv(io.StringIO(aei), dtype={"node_external_id": str, "geo_id": str}, keep_default_na=False, na_values=[""]),
            pd.read_csv(io.StringIO(NAMES), keep_default_na=False),
            pd.read_csv(io.StringIO(ONET), dtype={"Task ID": str}))


def test_tasks_and_countries_from_the_newest_month(make_ctx, read):
    ctx = make_ctx("anthropic_aei")
    anthropic_aei.build_from(ctx, *frames(), release="release_2026_06_26", onet_release="31.0", sha="abc")
    t = read(make_ctx.data, "us.aei.tasks")
    assert t["year"] == "2026-05" and t["citation"]["url"].endswith("/release_2026_06_26")
    occ = t["data"]["occupations"]
    ceo = occ["11-1011.00"]
    assert ceo["title"] == "Chief Executives"
    assert ceo["taskShare"] == 0.5  # 2 of 4 listed tasks; the April row and the subregion row don't count
    assert ceo["tasks"] == [["Prepare budgets for approval, including those for funding or implementation of programs.", 0.0125],
                            ["Confer with board members, organization officials, or staff members to discuss issues, coordinate activities, or resolve problems.", 0.0059]]
    assert occ["15-1252.00"] == {"title": "Software Developers", "taskShare": 1.0, "tasks": [["Write code.", 0.0]]}
    assert occ["47-2111.00"]["taskShare"] == 0 and occ["47-2111.00"]["tasks"] == []

    c = read(make_ctx.data, "world.aei.country")["data"]
    assert c["count"] == 3
    assert c["countries"]["AUS"] == {"name": "Australia", "index": 6.4, "rank": 1}
    assert c["countries"]["USA"] == {"name": "United States", "index": 3.87, "rank": 3}
    assert "NAM" not in c["countries"]


def test_mismatched_onet_release_is_refused(make_ctx):
    extra = "".join(f"2026-05-01,2026-06-01,GLOBAL,global,onet,0,pct,0.1,Unknown task {i},{90000 + i}\n" for i in range(5))
    with pytest.raises(PipelineError, match="aren't in O\\*NET"):
        anthropic_aei.build_from(make_ctx("anthropic_aei"), *frames(AEI + extra), release="release_2026_06_26", onet_release="31.0")


def test_newest_release_file_is_picked():
    paths = ["release_2026_03_24/data/aei_raw_claude_ai_2026-02-05_to_2026-02-12.csv", "release_2026_06_26/data/aei_claude_ai_2026-06-26.csv",
             "release_2026_06_26/data/aei_1p_api_2026-06-26.csv", "robot_exposure/robot_exposure_tasks.csv"]
    assert anthropic_aei.latest_release_file(paths) == "release_2026_06_26/data/aei_claude_ai_2026-06-26.csv"
