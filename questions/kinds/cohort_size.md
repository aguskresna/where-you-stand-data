### `cohort_size`
How many people born in a year are alive, or live in a place, today, and how many babies were born
that year. Used by us-your-generation and world-your-generation.

`params`: `dataset`; `path` to counts by single year of age; `layout` (`single` or `single_mf`);
`scale` (1000 for UN thousands); `birthYear` (input key); `method`: `age` reads the single age
(this year - birth year), `bornIn` takes half of two ages at the data year (`yearPath`);
`rangeError` (template, `{from}`/`{to}` for `bornIn`); `missing`; `births` (a number spec, below;
may use `{year}`); `place` (phrase); `birthsLine` (template that fills `{birthsLine}` when there are
births, else empty); `gridCaption` (phrase; no grid when empty or without births); `stats`;
`caveats`; `projection` (checks the data year; `bornIn` only).

Number spec: `{"dataset": id, "path": [keys]}` or `{"dataset": id, "series": field, "country":
template, "year": template}` (a UN WPP series), times `scale`. A missing dataset or figure is none.

Values: `alive`, `births`, `aliveShare` (alive / births), `year`, `place`, `birthsLine`.
Flags: `births`. Grid: share of the babies born that year alive today, with the caption.

Shared with the other life-and-world kinds (`app/lib/engine/lifeworld_text.dart`): every number
input is also a value `v.KEY` written without ".0" (`{v.birthYear}` gives 1990); a text input's raw
value is `{KEY}` in templates and paths. Lists of `stats` and `caveats` in params hold plain entries
or conditional ones, `{"stat": [label, value], "when": FLAG}` / `{"text": template, "unless": FLAG}`,
added after `text.stats` / `text.caveats`; a caveat may be a phrase, skipped when it comes out empty.
`projection: {"after": 2023, "caveat": "..."}` adds the caveat when a year used is past `after`.
