# Data-gate review: what the spike rule does to the universe

**Date:** 2026-11-25 · **Status:** report only. Nothing in the frozen V1 configuration was changed.

Reproduce it with `python -m src.ops.gate_review`. It reads stored prices and writes nothing.

## The finding in one paragraph

The validation gate rejects any single-day move larger than the stock's dynamic limit (10 times its recent average
daily move, never below 20%), **with no check of volume**. A second rule does use volume, but only for 25%+ jumps.
So a real earnings gap on enormous volume is rejected exactly like a bad data print. A rejected day then excludes the
stock for **724 calendar days**. Of the 8 days the rule flagged in your stored history, 7 carry the signature of
real market events, and one looks like a genuine bad print.

## The flagged days

How to read it: *Volume* is the day's volume against its prior 20-day average. *Level kept* is how much of the move is
still there five trading days later (a bad print reverts, so it falls toward 0%). A day is labelled **looks real** when
volume was at least 2x and at least half the move was kept. This is a heuristic: it cannot read the news.

| Ticker | Day | Move | Gate limit | Volume vs 20-day avg | Level kept after 5 days | Heuristic verdict | Excluded until |
|---|---|---|---|---|---|---|---|
| META | 2022-02-03 | -26.4% | 20% | 8.0x | 111% | looks real | 2024-01-28 |
| META | 2022-10-27 | -24.6% | 22% | 6.4x | 128% | looks real | 2024-10-20 |
| META | 2023-02-02 | +23.3% | 20% | 5.3x | 70% | looks real | 2025-01-26 |
| META | 2024-02-02 | +20.3% | 20% | 4.9x | 91% | looks real | 2026-01-26 |
| NVDA | 2023-05-25 | +24.4% | 20% | 3.8x | 118% | looks real | 2025-05-18 |
| TSLA | 2024-09-19 | +23.3% | 20% | 1.4x | 122% | possible bad print | 2026-09-13 |
| TSLA | 2024-10-24 | +21.9% | 20% | 2.8x | 77% | looks real | 2026-10-18 |
| UNH | 2025-04-17 | -22.4% | 20% | 5.0x | 127% | looks real | 2027-04-11 |

Several of these are well-known earnings moves (the META days in 2022, 2023 and 2024, NVDA in May 2023, TSLA in
October 2024, UNH in April 2025). That is from general knowledge, not something this report verified from a news source.

## What it costs

| Stock | Days excluded, 2022-01-01 to the freeze (1,729 days) | Days excluded in the 12-month forward test (365 days) |
|---|---|---|
| META | 1,453 (84%) | 0 |
| NVDA | 724 (42%) | 0 |
| TSLA | 737 (43%) | 22 |
| UNH | 527 (30%) | **197 (54%)** |

- **Right now:** UNH is excluded until 2027-04-11, so it is out for more than half of the 12-month verdict window.
  The daily run reports "Skipped (bad data): 1" every day for this reason, and the status shows DEGRADED.
- **Looking back:** under today's rules the system could not have traded META for about 4 of the last 5 years, or
  NVDA and TSLA for about 2 years each. Those are the stocks with the biggest moves.
- **Possible mismatch with the backtests:** the code to replay these exclusions in a backtest exists
  (`data_exclusions` in `src/backtest/backtest.py`), but I found no tracked script that uses it, and the freeze report
  does not say whether the reported walk-forward numbers applied it. If they did not, the backtest traded names the live
  system would have excluded, so the tested universe and the live universe differ. This needs checking before the
  backtest numbers are used to judge the live system.

## Options (a decision for you, because the gate is frozen)

| Option | What changes | Look-ahead safe? | Effect on the 8 flagged days |
|---|---|---|---|
| **A. Keep the rule** | Nothing | Yes | 7 real events stay rejected. UNH is out until April 2027. |
| **B. Volume exception** | Do not reject a spike when that day's volume is at least 2x its 20-day average | Yes: volume is known at that day's close | The 7 real events pass; the TSLA September 2024 print (1.4x) is still rejected. |
| **C. Shorter exclusion** | Exclude for about 20 trading days after a flag, not 724 calendar days | Yes | Same days flagged, but each stock returns within weeks. |

Persistence (the "level kept" column) is not an option for a live rule: it needs prices from five days *after* the spike,
which the system does not have on that day.

**My reading of the evidence:** B is the smallest change that fixes the real problem and keeps the safeguard that
caught the one bad print. Whether to adopt it is your call, and it carries real consequences:

1. It changes the frozen configuration, so it must be logged in `V1_FREEZE_REPORT.md` section 8 and treated as a new
   configuration, with a new forward-test clock. Forward results before the change would not be comparable.
2. Before adopting it, replay the backtest with and without the exclusions (the `data_exclusions` hook exists) to see
   how much the result moves. A change that helps in the data you already looked at is not evidence that it helps going forward.
3. Admitting volatile earnings gaps adds exactly the kind of trade (large gap, high volatility) that the -8% stop
   cannot protect against, because a gap can open far below the stop. Option B improves coverage; it does not improve
   safety, and it could increase losses.

## Two more findings (2026-11-25)

**1. The gap check used the wrong holiday calendar (fixed, with no change in any pass or fail).** It used pandas'
*federal* holiday list, which treats Columbus Day and Veterans Day as closed (the market is open) and misses Good Friday
and one-off closures. It was replaced with the real NYSE calendar (`exchange_calendars`). On all 26 stocks' stored
history, no pass or fail changed and false "missing trading day" warnings fell from 619 to 65.

**2. The "reject after 6 missing days in a row" rule can never fire (found, NOT fixed).** The code only counts dates
exactly one calendar day apart as consecutive, so every weekend splits a gap and no run can exceed 5. A stock missing
weeks of data therefore passes with a warning. This is not theoretical: **AAPL, MSFT, NVDA, GOOGL, META, AMZN, TSLA and
JPM each have a 56-session hole (2024-07-01 to 2024-09-18) in the stored history.** It lies outside the window the live
run fetches fresh each day, so live trading is not affected, but any backtest or training that reads the stored history
is missing about 11 weeks for those stocks. The freeze report's backtests should be checked against this. The fix is
small (count consecutive trading sessions, not calendar days) but it changes a frozen rule, so it is your decision. A
test (`test_eight_consecutive_missing_sessions_should_be_rejected`) is marked as an expected failure until it is fixed.

## Limits of this review

- 8 flagged days is a small sample.
- "Looks real" is a heuristic from volume and persistence. It is not proof, and the one "possible bad print" is the
  same kind of judgement.
- The stored history may itself be affected by the data source's adjustments.
