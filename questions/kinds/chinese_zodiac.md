### `chinese_zodiac`
The share of people alive today born in the same Chinese zodiac year. People aged a at mid-year
were born in (data year - a) or the year before, so half of each age goes to each of the two
animals. Used by world-chinese-zodiac.

`params`: `dataset`; `path` to the population by single year of age; `layout` (`single_mf` for
`{m, f}` arrays, or `single`); `yearPath` (default `["year"]`, the data year); `birthYear` (input
key); `animals` (12 names, Rat first: year 4 was a Rat year); `place` (phrase); `missing` (error
template); `barsTitle`.

Values: `share` (one decimal), `even` (1 in 12), `animal`, `place`.
Grid: share. Bars: every animal (share), yours marked.

Shared with the other life-and-world kinds (`app/lib/engine/lifeworld_text.dart`): every number
input is also a value `v.KEY` written without ".0" (`{v.birthYear}` gives 1990); a text input's raw
value is `{KEY}` in templates and paths. Lists of `stats` and `caveats` in params hold plain entries
or conditional ones, `{"stat": [label, value], "when": FLAG}` / `{"text": template, "unless": FLAG}`,
added after `text.stats` / `text.caveats`; a caveat may be a phrase, skipped when it comes out empty.
`projection: {"after": 2023, "caveat": "..."}` adds the caveat when a year used is past `after`.
