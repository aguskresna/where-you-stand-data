### `world_partner`
People worldwide of a sex and age range, optionally in households above an income per person (the
share above the floor from each country's PIP cut points). Age and income are combined as if
unrelated. Used by world-dream-partner.

`params`: `popAge`, `pip`, `wdi`, `wpp` (dataset ids); `seeking`, `ages` (a range), `country`,
`minIncome` (input keys); `sexKeys` (`{"F": "f", "M": "m"}`); `scale` (1000); `limit` (bars, 10);
`ppp`, `cpi`, `baseYear`, `noPpp` (as in global_income); `people` (phrase, may use `{lo}`, `{hi}`);
`sentenceAnyIncome` (replaces `text.sentence` when the floor is 0); `barsTitle`; `stats`; `caveats`.

Values: `total`, `people`, `lo`, `hi`, `threshold`, `share` (of everyone that age where income is
known), `own`, `ownName`, `missingShare`, `cpiYear`.
Flags: `income`, `own`, `missing`, `cpi`, `noCpi`. Grid: share. Bars: the top countries, yours
marked (added after them if outside the top).

Shared with the other life-and-world kinds (`app/lib/engine/lifeworld_text.dart`): every number
input is also a value `v.KEY` written without ".0" (`{v.birthYear}` gives 1990); a text input's raw
value is `{KEY}` in templates and paths. Lists of `stats` and `caveats` in params hold plain entries
or conditional ones, `{"stat": [label, value], "when": FLAG}` / `{"text": template, "unless": FLAG}`,
added after `text.stats` / `text.caveats`; a caveat may be a phrase, skipped when it comes out empty.
`projection: {"after": 2023, "caveat": "..."}` adds the caveat when a year used is past `after`.
