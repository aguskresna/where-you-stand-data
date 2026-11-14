# Question catalog

Questions are data, not app code. The app downloads `catalog.json` (built from these files by
`python -m statsapp_pipeline publish`) and shows every question whose data is built and whose
`kind` it knows. A new question that uses an existing kind reaches users the next time they open
the app; a new kind needs an app update. The app ignores kinds it doesn't know.

- `modes.json`: modes, topic labels, option lists (`"@us_states_any"`), age bands (`"@AGE"`).
- `us.json`, `world.json`, `my.json`, `id.json`: the questions, one array per mode.
- The validator (`python -m statsapp_pipeline questions`) runs in the daily job and in the tests.
- `i18n/ms.json`, `i18n/id.json`: the catalog's text in Malay and Indonesian (see Translations).
- `modes.json` `messages`: the calculations' own messages (errors about inputs, and the few stats,
  captions and caveats a kind adds itself), by key. The app keeps English copies in
  `app/lib/calc/messages.dart` as the fallback; keep the two the same.

## A question

```json
{
  "id": "us-income-rank",            // <mode>-<name>
  "mode": "us",
  "topic": "money",                  // a key of modes.json "topics"
  "title": "Income rank",
  "question": "Where does your income rank?",
  "kind": "group_rank",              // the calculation, implemented in app/lib/calc/
  "datasets": ["us.acs.income_q"],   // every dataset it reads; it's hidden until all are built
  "inputs": [ ... ],
  "params": { ... },                 // depends on the kind, see below
  "text": {
    "headline": "{rank}",            // placeholders are filled from the kind's values
    "sentence": "You earn more than {pct} of {group}.",
    "stats": [["Median for this group", "{median}"]],
    "caveats": ["Counts adults with any income in the past 12 months, before tax."]
  }
}
```

Placeholders: `{name}` is a value the kind produces; `{label.KEY}` is the label of the option chosen
for input KEY; `{in.KEY}` is its raw value. Paths (`path`, `table`, `fallback`, `labelsPath`) are
arrays of keys into the dataset's `data`, and each key may contain `{KEY}` for an input's value
(arrays, because state names like `W.P. Kuala Lumpur` contain dots).

A "phrase" is either a string template or `{"input": KEY, "map": {value: text}, "default": template}`.

## Inputs

| type | fields | value |
| --- | --- | --- |
| `number` | `min`, `max`, `step`, `unit` | number |
| `money` | `currency` (USD, MYR, IDR), `min`, `step` | number |
| `height` | `allowAny` (0 means no minimum) | centimetres |
| `choice` | `options` | string (segmented buttons, for 2 to 4 options) |
| `select` | `options` or `optionsFrom` | string |
| `date` | `min` | `YYYY-MM-DD`, never in the future |
| `monthday` | | `{"month": 6, "day": 15}` |
| `toggle` | | true or false |
| `text` | `maxLength` | string |
| `range`, `multi`, `weights` | see the reference prototype | for kinds still to port |

`options` is a list of `[value, label]` or `"@listName"` from modes.json. `optionsFrom` reads them
from a dataset: `{"dataset": id, "path": [keys], "exclude": [values], "first": [[value, label]]}`;
the value at `path` may be an object `{code: label}` or a list of `[code, label]`. Options from an
object are sorted by label.

## Kinds in app build 1

### `group_rank`
Rank a value within quantiles for the person's group, falling back to broader groups when the
exact one has too few survey records.

`params`: `dataset`; `path` to an object of `{groupKey: [101 ascending thresholds]}`; `value` (input
key); `parts`: one per key segment, `{"input": KEY, "bands": "@AGE" (turns an age into a band),
"all": "*" (the token meaning everyone, e.g. "Malaysia"), "phrase": {value: text, "_": template,
"*": text when generalised}}` where `_` may use `{label}`, `{band}`, `{value}`; `fallbackOrder`
(indexes of parts to generalise first); `suffix` (added to the group phrase); `positions` (path to
custom percentile positions such as OEWS's `p`); `format` for `{median}`: `{"type": "money",
"currency": "USD"}`, `{"type": "number", "digits": 0, "suffix": " minutes"}` or `{"type": "height"}`.

Values: `rank` ("72nd percentile" or "Top 3%"), `pct` ("72%"), `median`, `group` ("women aged
25–34 in Texas"). Adds a caveat when it had to fall back. Grid: rank, with "you".

### `class_by_multiple`
Place spending per person in classes defined as multiples of a line (BPS kelas sosial).

`params`: `dataset` (with `value`, `period`, `bands: [[label, from, to|null]]`); `amount` and
`divideBy` (input keys); `currency`; `localNote` (template using `{local}`, the part of a band
label in brackets); `nextStat` and `thresholdStat` (stat templates).

Values: `class`, `local`, `localNote`, `perPerson`, `multiple`, `line`, `period`. Adds stats for the
next class and every class threshold. No grid.

### `age_rank`
Share of a population older than the person.

`params`: `dataset`; `layout`: `single` (an array of counts by single year of age, last open),
`single_mf` (an object with `m` and `f` arrays) or `grouped` (counts by age group, labels at
`labelsPath`); `path`; `birthDate` (input key); `place` and `who` (phrases).

Values: `younger`, `older`, `place`, `who`. Grid: rank (younger than you), with "you".

### `date_rank`
How a calendar date ranks by average births.

`params`: `dataset` (with `years: [first, last]` and `byDate: {"MM-DD": births}`); `input`
(monthday key); `place`.

Values: `rank` ("120th"), `of`, `births`, `mean`, `date`, `top`, `bottom`, `first`, `last`.
Grid: rank (dates with fewer births), with "you".

### `life_table`
Years left and the chance of reaching 80, 90 and 100.

`params`: `dataset`; `shard` (template, for sharded datasets); `table` and `fallback` (paths to a
table `{ages, lx, ex}`); `age` (input key); `who` and `place` (phrases).

Values: `left`, `liveTo`, `age`, `who`, `place`. Adds the chances as stats and a caveat when the
table stops early (Malaysia's stops at 80+). Refuses ages past the table. Grid: share reaching 90.

## Adding a kind

1. Implement it in `app/lib/calc/` and register it in `app/lib/calc/registry.dart`; add tests.
2. Add it to `KINDS` in `pipeline/statsapp_pipeline/questions.py` with the app build that ships it.
3. Port questions that use it from `reference/web-prototype/web/js/features/` into these files.
4. Ship the app update. Older app builds keep hiding questions of the new kind.

## Translations

Each language has an overlay in `i18n/<lang>.json` holding only translated text, keyed by what it
replaces. The app lays the overlay for its language over the English catalog field by field, so
anything missing stays English and a new question works before it's translated.

```json
{
  "schema": 1, "language": "ms",
  "modes": {"us": {"title": "...", "blurb": "..."}},
  "topics": {"money": "..."},
  "lists": {"sex": {"F": "Perempuan"}, "us_states_any": {"*": "Seluruh AS"}},
  "messages": {"noFigures": "..."},
  "questions": {
    "us-income-rank": {
      "title": "...", "question": "...",
      "inputs": {"income": {"label": "...", "help": "...", "unit": "..."},
                 "sex": {"options": {"F": "..."}}, "country": {"first": {"WLD": "..."}}},
      "params": {"parts": [{"phrase": {"F": "wanita"}}, {"phrase": {"_": "berumur {band}"}}]},
      "text": {"sentence": "...", "stats": [["...", null]], "caveats": ["..."]}
    }
  }
}
```

- `params` and `text` mirror the English: objects by key, lists by position with the same length,
  `null` keeping the English item. Option values, input keys, dataset ids, paths, codes and
  expressions are never translated; the validator only accepts text a person sees
  (`i18n.translatable()` decides, and `STRUCTURAL` lists the params keys that are never text).
- Every `{placeholder}` must appear exactly as in the English, no more and no fewer.
- `python -m statsapp_pipeline i18n <lang>` prints what a language doesn't translate yet, in the
  overlay's shape (proper names such as US states stay English on purpose).
- `python -m statsapp_pipeline sheet` writes `i18n/translations.csv`, every text as a row for a
  translator or native speaker (the shared workflow's columns; the key is the text's path in the
  overlay). `python -m statsapp_pipeline sheet-import <returned.csv>` checks a returned sheet
  (empty text, unknown keys and changed placeholders are refused; a missing do-not-translate word
  is a warning) and `--write` updates the overlays. See `i18n/README.md`.
- Publishing writes one hashed file per language (`files/catalog.<lang>.<hash>.json`, listed in
  `index.json` under `catalogI18n`), so a phone downloads only its own language.
- Placeholders are filled with values the app has already put into the person's language: ranks
  ("persentil ke-72", "3% teratas"), "1 daripada 1,250", age bands ("bawah 35", "65 ke atas"),
  dates ("15 Jun"). Names read from datasets (countries, occupations, BPS class names) stay as the
  data has them. The Malay and Indonesian texts were written by Claude and still need a native
  speaker's check.
