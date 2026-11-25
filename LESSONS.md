# Lessons learned

Add one line whenever an agent mistake could have been prevented by a rule. Read this file at the start of a session.

Format: `YYYY-MM-DD | what went wrong | rule that prevents it`

## Starter entries (delete the ones that never apply)

- Starter | Scaled the data before splitting, so test statistics leaked into training | Split first, then fit transforms on the training split only.
- Starter | Decided a trade using the same day's close | Decide on the prior close, fill at the next open.
- Starter | Reported a backtest return without costs or the SPY comparison | Net of 0.2% cost, SPY buy-and-hold beside it, "optimistic" label.
- Starter | Reported a metric that was not run in this session | Never state a number that was not measured; write `<not measured>`.

## Log

