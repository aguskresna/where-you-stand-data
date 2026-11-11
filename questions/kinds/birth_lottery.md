### `birth_lottery`
Of every baby born in a year, the share born in countries poorer than yours by GDP per person,
weighting each country by its births; plus the births-weighted share with electricity and the share
born where most people were online. Used by world-birth-lottery.

`params`: `wpp`, `wdi` (dataset ids); `birthYear`, `country` (input keys); `scale` (1000); `gdp`,
`power`, `online` (WDI codes; the last two optional); `onlineThreshold` (50); `noYear`, `noCountry`
(errors using `{year}`, `{name}`); `gridCaption`; `stats`; `caveats`.

Values: `pct`, `allBirths`, `year`, `name`, `gdp`, `power`, `online`, `missingShare`.
Flags: `power`, `online`, `missing` (countries with figures cover under 95% of births).
Grid: rank, with "you".

Shared with the other life-and-world kinds (`app/lib/engine/lifeworld_text.dart`): every number
input is also a value `v.KEY` written without ".0" (`{v.birthYear}` gives 1990); a text input's raw
value is `{KEY}` in templates and paths. Lists of `stats` and `caveats` in params hold plain entries
or conditional ones, `{"stat": [label, value], "when": FLAG}` / `{"text": template, "unless": FLAG}`,
added after `text.stats` / `text.caveats`; a caveat may be a phrase, skipped when it comes out empty.
`projection: {"after": 2023, "caveat": "..."}` adds the caveat when a year used is past `after`.
