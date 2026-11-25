# Role: Testing and debugging (trimmed for this project)

Project rules in `docs/ENGINEERING_RULES.md` win. Tests run with `pytest` (see `pytest.ini`).

## Test rules
- Test behavior, not implementation. A test must fail when the behavior breaks.
- Independent and deterministic: fixed seeds, frozen time, no calls to real third parties (use fakes/recorded data).
- Name tests by what they prove: `test_rejects_price_spike`.
- Cover edges: empty data, NaN, wrong type, holiday/gap, dependency down, one bad ticker among good ones.
- Bug found? Write the failing test first, then fix.
- No coverage gaming. Never delete or skip a failing test to get green.
- Mocks are for slow or external things. If everything is mocked you are testing the mocks.
- Flaky test: find the cause (time, ordering, shared state, network); never retry forever.

## Project-specific tests to keep
- Backtester known-answer test: buy-and-hold SPY reproduces SPY's real return.
- Leakage tests: no feature uses the decision day's own close; lag rule holds.
- Model freeze: hash mismatch or missing model means the pipeline refuses to trade.
- Costs: every simulated fill applies the 0.2% cost.
- Risk engine veto and exit priority (stop-loss, take-profit, signal, hold).

## Debugging routine
1. **Reproduce:** a command or test that fails every time.
2. **Localize:** bisect (git bisect, comment out halves, log at boundaries).
3. **Reduce:** smallest failing input and code.
4. **Fix** the root cause, not the symptom.
5. **Guard:** add a test that would have caught it; add a `LESSONS.md` line if it was an agent mistake.

Read the full error and stack trace before guessing. Change one thing at a time.
