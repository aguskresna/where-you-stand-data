### `sign_share`
The share of births under each star sign, from average births per calendar date (February 29
counts a quarter, since it comes once in four years). Used by us-zodiac-share and my-zodiac-share.

`params`: `dataset` (`{years: [first, last], byDate: {'MM-DD': births}}`), `input` (monthday key),
`people`, `signs` (`[[name, 'MM-DD' first day, 'MM-DD' last day], ...]`, in display order),
`barsTitle`.

Values: `share`, `sign`, `even` (one in the number of signs), `people`, `first`, `last`.
Grid: share. Bars: every sign, yours marked.
