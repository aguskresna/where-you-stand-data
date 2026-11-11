### `life_hours`
The years an average person your age has left (period life table), split by the hours you spend on
each activity a day, with average time use where the data has it. Used by us-life-in-hours and
world-life-in-hours.

`params`: `dataset` (life table); `shard` (template, for sharded tables); `table`, `fallback` (paths
to `{ages, lx, ex}`); `age` (input key); `noTable`; optional `place` (`{"dataset", "path",
"nameField", "missing"}`: a record whose name becomes `{name}`; refused when missing); `activities`
(`[{"key": input key, "label"}]`); `rest` (the bar for the hours left over); `tooMany` (error over 24
hours); `averages` (`{"dataset", "path", "divide"}`: every number there as `avg.KEY`, divided, e.g.
minutes by 60); `who` (phrase); `barsTitle`; `stats`; `caveats`.

Values: `left`, `years.KEY` per activity, `avg.KEY`, `name`, `who`. Flags: `averages`.
Bars: your remaining years by activity (years).

Shared with the other life-and-world kinds (`app/lib/engine/lifeworld_text.dart`): every number
input is also a value `v.KEY` written without ".0" (`{v.birthYear}` gives 1990); a text input's raw
value is `{KEY}` in templates and paths. Lists of `stats` and `caveats` in params hold plain entries
or conditional ones, `{"stat": [label, value], "when": FLAG}` / `{"text": template, "unless": FLAG}`,
added after `text.stats` / `text.caveats`; a caveat may be a phrase, skipped when it comes out empty.
`projection: {"after": 2023, "caveat": "..."}` adds the caveat when a year used is past `after`.
