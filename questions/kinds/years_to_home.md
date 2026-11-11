### `years_to_home`
Months of saving until a down payment on a typical home, month by month for up to 100 years (1,200
months), at today's prices and, where the data has it, with prices rising at the recent yearly rate.
Used by us-years-to-home and world-years-to-home.

`params`: `dataset`; `groups` (path to the places); `place` (input key); `all` (the "everyone" key to
fall back to, e.g. `*`); either `priceField` (a price in the data; `incomeField` gives the typical
ratio) or `ratioField` (price = ratio x your income); `income`, `saved`, `monthly`, `down` (input
keys; money in the income input's currency); `growth` (`{"dataset", "path"}` to yearly growth by
place; optional data); `missing`; `labels` and `when` (`{"ready", "over", "years"}` templates,
`{years}` = "4.2 years"); `placePhrase`; `bars` (`{"title", "labelField", "valueField", "limit",
"unit"}`: top `limit` plus yours); `stats`; `caveats`.

Values: `wait`, `when`, `price`, `priceRatio` (price / your income), `typicalRatio`, `monthly`,
`name`, `dataYear`, `place`, `growth`, `growthLabel`. Flags: `growth`. No grid.

Shared with the other life-and-world kinds (`app/lib/engine/lifeworld_text.dart`): every number
input is also a value `v.KEY` written without ".0" (`{v.birthYear}` gives 1990); a text input's raw
value is `{KEY}` in templates and paths. Lists of `stats` and `caveats` in params hold plain entries
or conditional ones, `{"stat": [label, value], "when": FLAG}` / `{"text": template, "unless": FLAG}`,
added after `text.stats` / `text.caveats`; a caveat may be a phrase, skipped when it comes out empty.
`projection: {"after": 2023, "caveat": "..."}` adds the caveat when a year used is past `after`.
