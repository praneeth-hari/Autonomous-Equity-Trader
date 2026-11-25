# Role: Data (trimmed for this project)

Project rules in `docs/ENGINEERING_RULES.md` (validation gate, rule 7) win.

## Pipeline principles
- **Idempotent:** running a job twice gives the same result. Upsert or overwrite by date; no blind appends.
- **Re-runnable by date:** a backfill is the same code as a daily run.
- **Small stages:** fetch, validate, transform, load, each inspectable.
- **Immutable raw data:** save raw pulls unmodified (`data/raw/`); derive everything else.
- **Retries with backoff** on network/API calls; never silently drop rows.
- **Count rows in, out and rejected** at each stage and log them.
- **Secrets only via `config/settings.py`.**

## Quality checks (in the pipeline, not a notebook)
| Check | Examples |
|---|---|
| Schema | columns, types, required fields |
| Validity | price > 0, High >= Low, Close within [Low, High], volume >= 0 |
| Spikes | single-day move beyond +/-50% flagged |
| Gaps | expected vs received NYSE trading days |
| Freshness | newest bar is recent enough |
| Volume | row count within the normal band vs last run |
| Consistency | joins do not drop or multiply rows |

- A failed critical check skips that stock and logs why. Never fill fake data; never crash the whole run.
- Many skips at once means the source is degrading: pause and check.
- A held stock with bad data is held untouched and flagged.

## Analysis habits
- Start from the question. Check counts, missing data, outliers, duplicates, time coverage.
- Say "associated with", not "causes". Include sample sizes.
- Survivorship and selection bias: the 25-ticker universe is current large caps, so label results optimistic.

## Output checklist
- [ ] Source, grain (what one row means), refresh schedule stated
- [ ] Re-runnable by date
- [ ] Quality checks with a failure behavior
- [ ] Row counts logged
- [ ] Sample output inspected by eye
- [ ] No secrets in logs
