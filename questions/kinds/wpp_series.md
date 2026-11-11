### `wpp_series`
Figures from the UN WPP indicator series (`pop`, `births`, `tfr`, `mac`, `e0`) at given years,
compared with an input, a past year or every country. Used by world-pop-when-born,
world-family-size, world-family-lottery, world-parenthood-age and id-family-size.

`params`: `dataset` (`{first, last, countries, series}`); `name` (phrase, value `name`);
`points`: `{NAME: {"series", "country", "year", "scale", "format", "digits", "required"}}`, read in
order (`country` and `year` are templates; `{thisYear}` is this year kept within the series;
`required` is the error when the figure is missing, otherwise it shows "–"); `sums`: `{NAME:
{"series", "country", "from", "to", "scale", "format"}}` (missing years count 0); `ratios`: `{NAME:
{"of", "to", "format", "digits"}}` (point / point); `compare`: `{"input", "with" (a point),
"tolerance", "digits", "same", "more", "less"}` (templates using `{diff}`, the absolute difference);
`trend`: `{"of", "from", "lower", "higher"}`; `extremes`: `{"series", "year", "digits"}` (highest and
lowest country); `bars`: `{"title", "series", "country", "every" (10), "to", "markInput", "unit"}`
(one bar per decade, the decade of `markInput` marked); `stats`; `caveats`; `projection` (checks
this year). Formats: `compact`, `int`, `num` (with `digits`), `pct`, `years`, `plain`.

Values: each point, sum and ratio by name, `thisYear`, `name`, `diff`, `compare`, `trend`,
`highest`, `highestValue`, `lowest`, `lowestValue`. Flags: each point found, `extremes`. No grid.

Shared with the other life-and-world kinds (`app/lib/engine/lifeworld_text.dart`): every number
input is also a value `v.KEY` written without ".0" (`{v.birthYear}` gives 1990); a text input's raw
value is `{KEY}` in templates and paths. Lists of `stats` and `caveats` in params hold plain entries
or conditional ones, `{"stat": [label, value], "when": FLAG}` / `{"text": template, "unless": FLAG}`,
added after `text.stats` / `text.caveats`; a caveat may be a phrase, skipped when it comes out empty.
`projection: {"after": 2023, "caveat": "..."}` adds the caveat when a year used is past `after`.
