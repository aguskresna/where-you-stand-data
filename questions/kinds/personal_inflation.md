### `personal_inflation`
Each CPI group's 12-month change weighted by the person's spending, against the official rate. Used
by us-personal-inflation, my-personal-inflation and id-personal-inflation.

`params`: `dataset` (`{asOf: 'YYYY-MM', overall, groups: {code: {label, change, weight?}}}`);
`weights` (a weights input whose `weightsFrom` reads the same dataset's `groups`); `place`;
`barsTitle`; `noWeights` (the error when every weight is 0).

Values: `personal` ("+3.2%"), `personalPct` ("3.2%"), `overall`, `diff` ("+0.4", in points),
`month` ("September 2026"), `place`. Bars (change): every group, marking those with a weight.
