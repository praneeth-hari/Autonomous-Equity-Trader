# Project Status

Persistent project memory. Read this first when returning to the project, then `docs/ENGINEERING_ROADMAP.md`.
**Last updated:** 2026-11-26.

## Purpose
Local paper-trading system for US stocks (simulated money, no broker) built to learn and to measure a frozen ML
strategy honestly. Goal: do not lose money; cash is a valid position. Rules: `AGENTS.md`, plan: `docs/PROJECT_PLAN.md`,
frozen configuration: `V1_FREEZE_REPORT.md`.

## Stack
Python 3.11, pandas, scikit-learn (frozen logistic regression), SQLAlchemy + SQLite, FastAPI, React 19 + Vite + TypeScript,
pytest / Vitest / Playwright, Windows Task Scheduler, Telegram alerts. Details: `docs/ENGINEERING_AUDIT.md` §1.

## Architecture (short)
Task Scheduler (Mon–Fri 03:30) → `run_trader.bat`: heartbeat → env pre-flight (`src.ops.envcheck`) → backup
(`src.ops.backup`) → pipeline (`src.pipeline.scheduler` → `daily_pipeline`: fetch → validate → features → model →
intelligence → ranking → risk engine (veto) → allocation → paper broker → SQLite) → heartbeat → watchdog alert → log cleanup.
Read side: SQLite → `src/services` → FastAPI (127.0.0.1:8000) → React app (127.0.0.1:5173).

## Feature state
Full table: `docs/ENGINEERING_AUDIT.md` §2.
- **Implemented:** daily pipeline, lag rule, NYSE calendar, frozen model + integrity checks, risk engine, paper broker,
  backtester with SPY known-answer test, approvals, kill switch, API, React app, Telegram alerts, backups, pre-flight.
- **Partial:** data gate (frozen rule still active; fixes available behind `GATE_SPIKE_VOLUME_EXCEPTION` and `GATE_GAPS_COUNT_SESSIONS`), heartbeat (not configured), backups (second copy available but `BACKUP_MIRROR_DIR` not set), SHAP (on demand only).
- **Broken:** none known. (CI fixed and the dead ensemble branch removed on 2026-11-27.)
- **Unverified:** live effect of intelligence layers. (First unattended trading-day run happened 2026-11-27, see below.)

## Known bugs and limitations
- Strategy trails SPY in backtests; loses money without TSLA. Forward record is short and has gaps (nightly job was
  broken until 2026-11-25).
- One flaky test (`test_ops_routes.py ... [headers1]`): failed once under severe memory pressure, 0 failures in 20 reruns; it now reports full details if it fails again. Tests needing git-ignored data now skip with a reason.
- Runs only while this PC is on; no dead-man's switch yet.
- Telegram token was once logged; rotation pending (user).

## Engineering quality (summary)
Strong: leakage controls, safety-first risk engine, test isolation incl. production-DB write guard, honest reporting.
Weak: a few large modules, docs partly stale, no type checking.

## Roadmap progress
Current phase: **Phase 5 done** (2026-11-28); next is Phase 6 (docs). Data-gate fixes are built but OFF until you turn them on.
Done: T1.2 CI green (run 45924755642), T1.4 history re-joined, T2.2 data-dependent tests skip on a fresh clone.
Waiting on you: T1.1 rotate Telegram token, T1.3 healthchecks.io check.

## Last verified state (2026-11-26)
- Full pytest run in a clean checkout (as CI sees it), 2026-11-27: 918 passed, 0 failed, 6 skipped (missing local data / gitleaks), 1 xfailed.
- First unattended trading-day run 2026-11-27: DEGRADED (exit 2). META stop-loss sell −$268.44 (−23%: no runs for ~8 weeks);
  buys vetoed by the regime filter (SPY below 200-day); UNH rejected by the spike rule. Equity $9,731.56, all cash.
- Lint gate (`ruff`, 4 real-bug rule groups): passes in CI; wider run shows 14 real findings (audit §3.2).
- Nightly 2026-11-26: pre-flight all OK, backup OK, holiday skip correct (exit 0).
- GitHub CI: green on 2026-11-27 (run 45924755642), Python tests now run in CI.

## Important decisions
- V1 frozen 2026-09-26; no tuning, no real money, no cloud.
- Kill switch halts the whole run, including stop-losses (deliberate, documented).
- Human approval of buys is opt-in; sells are never held.
- Data gate: option B and session-based gap counting chosen 2026-11-28, built behind settings that are off; switching on = new configuration (freeze report §8).
- GitHub history was rewritten (wording changes in 18 files). Local `main` was reset to it on 2026-11-27; the old local history is in branch `local-history-backup`.

## Next recommended action
Approve Phase 1 of `docs/ENGINEERING_ROADMAP.md` (T1.2 CI fix and T1.4 history re-join need approval; T1.1 and T1.3 are
yours: rotate the Telegram token, create the healthchecks.io check).
