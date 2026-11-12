"""Births history against text in the layout pypdf extracts from the NCHS "Births: Final Data" reports."""

import pytest

from statsapp_pipeline.common import PipelineError
from statsapp_pipeline.sources import nchs_births_history as bh

DOTS = ". . . . . . . . . . . . . . . . . . ."

LATEST = f"""National Vital
Statistics Reports
Births: Final Data for 2024
Table 1. Births and birth rates: United States, 2010–2024, and by race and Hispanic origin of mother: United States,
2016–2024
Race and Hispanic origin and year Number of births Birth rate Fertility rate
All races and origins1
2024 {DOTS}  3,628,934 10.7 53.8
2023 {DOTS}  3,596,017 10.7 54.5
2016 {DOTS}  3,945,875 12.2 62.0
2015 {DOTS}  3,978,497 12.4 62.5
Non-Hispanic, single race2
American Indian and Alaska Native:
2024 {DOTS}  24,021 10.0 46.8
--- page 15
National Vital Statistics Reports, Vol. 75, No. 2, June 9, 2026  15
Table 1. Births and birth rates: United States, 2010–2024, and by race and Hispanic origin of mother: United States,
2016–2024—Con.
Table 2. Birth rates, by age of mother: United States, 2010–2024, and by age and race and Hispanic origin of mother:
United States, 2016–2024
[Total fertility rates are sums of birth rates for 5-year age groups multiplied by 5. Birth rates are births per 1,000 women]
Race and Hispanic origin
of mother and year
Total fertility
rate
All races and origins2
2024{DOTS} 1,599.5 0.2 12.6 5.3 23.6 55.8 89.5 93.7 54.3 12.7 1.1
2023{DOTS} 1,621.0 0.2 13.1 5.5 24.6 57.7 91.0 94.3 54.3 12.5 1.1
2016{DOTS} 1,820.5 0.2 20.3 8.8 37.5 73.8 102.1 102.7 52.7 11.4 0.9
2015{DOTS} 1,843.5 0.2 22.3 9.9 40.7 76.8 104.3 101.5 51.8 11.0 0.8
Non-Hispanic, single race3
American Indian and Alaska Native:
2024 {DOTS} 1,380.5 0.4 20.3 9.1 37.1 70.4 79.0 61.8 35.6 8.1 0.5
Table 3. Births, by age of mother, live-birth order, and race and Hispanic origin of mother: United States, 2024
"""

HISTORY = f"""Births: Final Data for 2015
Table 1. Births and birth rates, by race: United States, specified years 1940–1955 and each year, 1960–2015
 Number Birth rate Fertility rate
Registered births  Race of mother
2015 {DOTS} 3,978,497 3,012,855 640,079 44,299 281,264 12.4 12.0 14.3 9.7 14.0 62.5 63.1 64.0 43.9 58.5
2014 {DOTS} 3,988,076 3,019,863 640,562 44,928 282,723 12.5 12.0 14.5 9.9 14.6 62.9 63.2 64.6 44.8 60.7
21981 {DOTS} 3,629,238 2,947,679 564,955 29,688 84,553 15.8 15.0 2
21980 {DOTS} 3,612,258 2,936,351 568,080 29,389 74,355 15.9 15.1 2
Race of child
21980 {DOTS} 3,612,258 2,898,732 589,616 36,797 --- 15.9 14.9 22.1
21979 {DOTS} 3,494,398 2,808,420 577,855 34,269 --- 15.6 14.5 22.0
19623,5 {DOTS} 4,167,362 3,394,068 584,610 21,968 --- 22.4 21.4 ---
Table 2. Births, by age of mother, live-birth order, and race of mother: United States, 2015
Table 3. Birth rates, by age of mother, live-birth order, and race of mother: United States, 2015
2015 {DOTS} 62.5 0.2
Table 4. Birth rates, by age of mother: United States, 1970–2015, and by age and race of mother: United States,
[Total fertility rates are sums of birth rates for 5-year age groups multiplied by 5.]
Year and race
Total
fertility
rate
All races2
2015 {DOTS}1,843.5 0.2 22.3 9.9 40.7 76.8 104.3 101.5 51.8 11.0 0.8
2014 {DOTS}1,862.5 0.3 24.2 10.9 43.8 79.0 105.8 100.8 51.0 10.6 0.8
31981 {DOTS} 1,812.0 1.1 52.2 32.0 80.0 112.2 111.5 61.4 20.0 3.8 0.2
31980 {DOTS}1,839.5 1.1 53.0 32.5 82.1 115.1 112.9 61.9 19.8 3.9 0.2
31979 {DOTS}1,808.0 1.2 52.3 32.3 81.3 112.8 111.4 60.3 19.5 3.9 0.2
White
2015 {DOTS}1,864.0 0.2 21.3 9.2 39.3 75.3 107.6 104.8 52.2 10.6 0.8
"""


def test_births_history_joins_the_two_reports(make_ctx, read):
    ctx = make_ctx("nchs_births_history")
    latest = LATEST
    # Fill 2017-2022 so the series is continuous, as in the real report.
    rows_b = "".join(f"{y} {DOTS}  3,700,000 11.0 56.0\n" for y in range(2022, 2016, -1))
    rows_t = "".join(f"{y}{DOTS} 1,700.0 0.2\n" for y in range(2022, 2016, -1))
    latest = latest.replace(f"2016 {DOTS}  3,945,875", rows_b + f"2016 {DOTS}  3,945,875").replace(f"2016{DOTS} 1,820.5", rows_t + f"2016{DOTS} 1,820.5")
    history = HISTORY
    fill_b = "".join(f"{y} {DOTS} 3,800,000 1 2 3 4 15.0\n" for y in range(2013, 1981, -1))
    fill_t = "".join(f"{y} {DOTS}1,900.0 0.2\n" for y in range(2013, 1981, -1))
    history = history.replace(f"21981 {DOTS} 3,629,238", fill_b + f"21981 {DOTS} 3,629,238").replace(f"31981 {DOTS} 1,812.0", fill_t + f"31981 {DOTS} 1,812.0")
    bh.build_from(ctx, latest, history, expect_year=2024)
    d = read(make_ctx.data, "us.nchs.births_history")
    y = d["data"]["years"]
    assert d["year"] == 2024
    assert min(map(int, y)) == 1979 and max(map(int, y)) == 2024 and len(y) == 2024 - 1979 + 1
    assert y["2024"] == {"births": 3628934, "tfr": 1.5995}
    assert y["1980"] == {"births": 3612258, "tfr": 1.8395}
    assert y["2015"] == {"births": 3978497, "tfr": 1.8435}
    assert "1962" not in y  # births only, no total fertility rate


def test_year_labels_with_footnotes():
    assert [bh.year_of(s) for s in ("2015", "31984", "21980", "19623", "41970")] == [2015, 1984, 1980, 1962, 1970]


def test_the_newest_report_must_be_the_one_linked(make_ctx):
    with pytest.raises(PipelineError, match="expected 2025"):
        bh.build_from(make_ctx("nchs_births_history"), LATEST, HISTORY, expect_year=2025)


def test_gaps_are_refused(make_ctx):
    with pytest.raises(PipelineError, match="without both"):
        bh.build_from(make_ctx("nchs_births_history"), LATEST, HISTORY, expect_year=2024)
