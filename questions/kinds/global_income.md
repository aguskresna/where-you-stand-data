### `global_income`
Household income per person a day at 2021 purchasing-power prices, ranked among everyone in the
world by pooling each country's PIP percentiles weighted by its population. Used by
world-income-rank and world-100-people.

The income is taken back to base-year prices with the CPI (base year / latest year), then divided by
household size, 365 and the base-year PPP rate. PIP stores per country `q`, 99 cut points at the
dataset's top-level positions `p` (1..99); every percentile here uses those positions.

`params`: `pip`, `wdi`, `wpp` (dataset ids); `country`, `income`, `size` (input keys); `ppp`, `cpi`
(WDI codes); `baseYear` (2021); `line` (the poverty line, 3); `noPpp` (error); `cpiNote` (uses
`{cpiYear}`) and `noCpiNote` (caveats added last); optional `ages` (`{"dataset", "path",
"birthDate", "missing"}`, the world population by age); optional `online` (a WDI % code: the world
aggregate, else a population-weighted mean); `sentenceParts` (texts joined "a, b and c" into
`{parts}`); `bars` (`{"title", "unit", "items": [{"label", "value": "richer"|"younger"|"online",
"when"}]}`); `gridCaption`; `stats`; `caveats`.

Values: `rank`, `pct`, `perDay` ("$2.15" under $10, "$12" above), `median`, `under` (share under the
line), `ownRank`, `name`, `richer`, `younger`, `online` (each out of 100), `onlineYear`, `parts`.
Flags: `own`, `younger`, `online`. Grid: rank, with "you".

Shared with the other life-and-world kinds (`app/lib/engine/lifeworld_text.dart`): every number
input is also a value `v.KEY` written without ".0" (`{v.birthYear}` gives 1990); a text input's raw
value is `{KEY}` in templates and paths. Lists of `stats` and `caveats` in params hold plain entries
or conditional ones, `{"stat": [label, value], "when": FLAG}` / `{"text": template, "unless": FLAG}`,
added after `text.stats` / `text.caveats`; a caveat may be a phrase, skipped when it comes out empty.
`projection: {"after": 2023, "caveat": "..."}` adds the caveat when a year used is past `after`.
