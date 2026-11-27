# Engineering Audit

**Date:** 2026-11-26 · **Scope:** whole repository at local commit `5bc6c13` (GitHub `main` = `5063c52`, same tree).
**Method:** read the code paths, ran the test suite, lint and the CI logs. Facts below are marked with how they were checked.
Nothing in this audit changed code.

## 1. What the project is (verified)

A local, single-user **paper-trading system for US stocks** (simulated money only, no broker). Every weekday at 03:30 a
Windows Task Scheduler job runs a Python pipeline that downloads prices, validates them, scores 25 stocks with a frozen
logistic-regression model, applies a risk engine with veto power, simulates fills at the next open with costs, and
stores everything in SQLite. A read-only FastAPI layer and a React web app show the results. Telegram alerts,
backups, an environment pre-flight and a heartbeat wrap the nightly run.

| Layer | Technology (verified in `requirements*.txt`, `web/package.json`) |
|---|---|
| Language / runtime | Python 3.11 (`.venv`), TypeScript (React 19, Vite) |
| ML | scikit-learn 1.9 (frozen model), XGBoost / LightGBM / Optuna (research only, not in the live path), SHAP |
| Data | yfinance (+ Alpha Vantage fallback), exchange_calendars (NYSE), pandera, pandas |
| Storage | SQLAlchemy 2 over SQLite (`data/processed/trader.db`); PostgreSQL supported and tested |
| API / UI | FastAPI + uvicorn on 127.0.0.1:8000, React + Tailwind + Recharts + TanStack Query on 127.0.0.1:5173 |
| Ops | Task Scheduler, `run_trader.bat`, Telegram, healthchecks.io heartbeat (not configured), local backups |
| Tests / CI | pytest (~917 tests), Vitest (2 files), Playwright (21 browser tests), ruff, pip-audit, gitleaks, GitHub Actions |
| Size | `src/` 23.8k lines Python, `tests/` 18.2k, `web/src` 3.0k |

## 2. Feature inventory

Status: **IMPLEMENTED** (working and verified) · **PARTIAL** · **BROKEN** · **MISSING** · **UNVERIFIED**.

| Feature | Status | Where | Evidence / gaps |
|---|---|---|---|
| Daily pipeline (fetch → validate → features → predict → risk → fill → store) | IMPLEMENTED | `src/pipeline/daily_pipeline.py`, `scheduler.py` | Pipeline tests pass; manual run 2026-11-25 completed. **First unattended trading-day run not yet observed** (26 Nov was a holiday and skipped correctly). |
| Lag rule (decide on prior close, fill next open) | IMPLEMENTED | `daily_pipeline.py`, `paper_broker.py` | Dedicated tests (`INCOMPLETE_BAR`, `LAG RULE` events). |
| Market calendar / holiday skip | IMPLEMENTED | `scheduler.is_market_day`, `src/data/validation.py` (XNYS) | Verified live on 2026-11-26 (Thanksgiving skipped). |
| Frozen model + integrity | IMPLEMENTED | `data/models/active_model.joblib`, `src/ops/envcheck.py` | sha256 and golden-prediction check pass every night. |
| Risk engine (stop −8%, TP +15%, signal exit, 3 positions, 15% cash, regime filter, crash breaker) | IMPLEMENTED | `src/risk/risk_engine.py` | Unit tests; exit priority tested. |
| Data validation gate | PARTIAL (works as coded, rule is flawed) | `src/data/validation.py` | Spike rule has no volume check and excludes a stock 724 days after one flag; "6 missing days" rule never fires. See `docs/DATA_GATE_REVIEW.md`. Frozen, so not changed. |
| Intelligence layers (VADER sentiment, earnings, sector, FRED macro) | IMPLEMENTED, effect UNVERIFIED | `src/intelligence/`, `src/portfolio/intelligence.py` | Code paths and tests exist; no measurement that they add edge. |
| SHAP explanations | PARTIAL | `src/ml/explainability.py` | Used only by the API on demand (`data_loader.py:656`), not "per prediction" as the README says. |
| PSI drift alarm | IMPLEMENTED | `risk_engine.py:956`, `daily_pipeline.py:1032` | Alert path tested; real drift behaviour not yet seen live. |
| Performance-weighted ensemble | BROKEN (dead code) | `src/ranking/ranking.py:299` | Result assigned to `final_probability` and never used; only one model is loaded, so the branch never runs. |
| Walk-forward evaluation | IMPLEMENTED, minor flaw | `src/ml/evaluate.py:387` | Comment says "fit on full train partition" but `train_model(test_ratio=0.10)` fits on ~90% of it. Not leakage, wastes data. |
| Backtester + SPY known-answer test | IMPLEMENTED | `src/backtest/backtest.py` | Tests present; results labelled optimistic. 3 backtest/ML tests need ignored data files and fail on a fresh clone. |
| Paper broker (costs, fractional shares) | IMPLEMENTED | `src/trading/paper_broker.py` | Tests. |
| Optional human approval of buys | IMPLEMENTED | `src/pipeline/approvals.py`, `src/api/ops_routes.py` | API + browser tests. Off by default. |
| Kill switch | IMPLEMENTED | `ops_routes.py`, pipeline | Tested. Halts stop-losses too (documented design choice). |
| Read-only API | IMPLEMENTED | `src/api/app.py` | 51 API tests pass. |
| React web app (12 pages) | IMPLEMENTED | `web/src` | 21 Playwright tests (mocked API) and build pass; 2 Vitest files only. |
| Local LLM chat (Ollama) | IMPLEMENTED, UNVERIFIED end-to-end | `src/llm/`, `/api/chat` | Unit tests; depends on Ollama running locally. |
| Alerts (Telegram) + watchdog | IMPLEMENTED | `src/alerts/` | Tests; token-redaction test. |
| Heartbeat / dead man's switch | PARTIAL | `src/alerts/heartbeat.py` | Code done; `HEALTHCHECK_PING_URL` empty, so nothing detects a dead PC. |
| Backups | PARTIAL | `src/ops/backup.py` | Nightly backup verified; stored on the **same disk** (`data/processed/backups`). |
| Environment pre-flight | IMPLEMENTED | `src/ops/envcheck.py` | Ran 2026-11-26, all checks passed. |
| PostgreSQL support | IMPLEMENTED, unused | `src/db/` | Tested; not used in V1 (local SQLite). |
| CI | **BROKEN** | `.github/workflows/tests.yml` | Last 2 pushes failed at *Dependency audit* (runner's bundled setuptools 65.5.0 has 9 advisories), so **Python tests never run in CI**. |
| GitHub-hosted trading / retrain / weekly workflows | Deliberately disabled | `.github/workflows/*.yml` | `workflow_dispatch` only, per V1 rules. |
| Tax report | PARTIAL | `src/reports/tax_report.py` | Defaults to `country="India"` in a US-stock project; not reviewed further. |

## 3. Findings by category

### 3.1 Architecture
- **Good:** clear pipeline stages with the risk engine between model and broker; settings read only in `config/settings.py`; repository layer isolates storage; API is read-only except two guarded routes.
- **Weak:** very large modules mix responsibilities: `src/db/repository.py` 1,723 lines, `src/backtest/backtest.py` 1,655, `src/services/data_loader.py` 1,541, `daily_pipeline.py` 1,182 (one function runs most of the day). These are hard to review but are covered by tests; split only where a change is needed anyway.
- **Unused weight:** XGBoost, LightGBM, Optuna, kagglehub, apscheduler and two PostgreSQL drivers ship in the runtime `requirements.txt` although the live path uses only scikit-learn and SQLite. `kagglehub` is not imported anywhere.

### 3.2 Code quality
- Lint gate checks only 4 real-bug rule groups (by design). A wider run (`ruff --select E,F,B,UP`) shows 14 real findings: 10 unused variables (two hide dead logic: `ranking.py:299`, `risk_engine.py:111`), 2 shadowed `datetime` imports in `data_loader.py`, 1 `== True` in a SQLAlchemy filter (`repository.py:1487`, harmless there), 1 unused loop variable. The other ~2,900 are style (annotations, line length).
- No static type checking (mypy/pyright not installed) despite heavy type hints.
- Root clutter: 18 ignored `fix_test*.py` scratch files, `scratch/` is **tracked**, root scripts `daily_status.py`, `health_check.py`, `db_migrate.py` sit outside `src/`.

### 3.3 Functionality
- Strategy performance: the frozen strategy **trails SPY** in both backtest decades and loses money without TSLA (`V1_FREEZE_REPORT.md`). This is an honest, documented result, not a bug, and it caps what "earning money" can mean.
- Data gate rule flaw (above) silently removes large-cap stocks for two years after a real earnings move.
- Forward record has gaps: the nightly job crashed (missing packages) until 2026-11-25, so forward days since the 2026-09-26 freeze are incomplete. Count of valid forward days: `<not measured>`.

### 3.4 Security
- **Telegram bot token was written to the log by `httpx`** before the fix on 2026-11-25. The logging is fixed and redaction is tested, but the token itself has **not been rotated** (user action). Location: `.env` (`TELEGRAM_BOT_TOKEN`); old log files under `logs/` were redacted.
- API binds to 127.0.0.1 and CORS allows only the web app. The two state-changing routes need a marker header and an allowed origin. Gaps: `POST /api/chat` has no such guard (it only reads, but costs local CPU), and no `Host` header check, so a DNS-rebinding page could read portfolio data while the API runs. Low risk for a personal machine.
- Secrets: read only in `config/settings.py`; `.env` ignored; secret scan + gitleaks config present; secret scan passes.
- Model files are joblib (pickle). Only the project's own file is loaded, hash-checked first; a skops copy exists.
- Dependencies: CI audit found vulnerabilities only in the runner's `setuptools`; project lock file not re-audited in this session (`<not measured>`).

### 3.5 Testing and reliability
- ~917 pytest tests, conftest isolates the database (session copy), lock dir, pending orders and reports, and `repository._assert_safe_write_target` blocks writes to the production DB during tests. This is strong.
- **Flaky test:** `tests/api/test_ops_routes.py::test_state_changing_routes_refuse_requests_that_do_not_come_from_the_web_app[headers1]` failed once in a full run and passed in 6 reruns. Cause not found.
- 3 tests depend on git-ignored data (`test_auto_retrain`, `test_training_pipeline::...real_files`, `test_backtest::test_5...`), so a fresh clone fails them; they are not marked to skip.
- Pipeline-lock tests failed under memory pressure once in a fresh checkout and passed alone.
- No coverage measurement; frontend logic has only 2 unit-test files (the e2e suite covers the main flows).
- Full local run on 2026-11-26: see `PROJECT_STATUS.md` "Last verified state".

### 3.6 Performance
- Not a bottleneck: one run per day, 25 tickers, finishes in minutes. The machine is memory-constrained (~19 GB commit limit; earlier MemoryError and crashes), which matters more than code speed. No optimisation recommended.

### 3.7 Data and database
- SQLite with SQLAlchemy models, integrity check nightly, 14 rotating backups with restore test.
- Migrations: ad-hoc `db_migrate.py` and `create_all`, no versioned migration tool. Acceptable for one user; risky if the schema changes.
- Backups live on the same disk as the database; a disk failure loses both.

### 3.8 Deployment and operations
- Single Windows laptop; runs only if the PC is on (wake timers disabled in the power plan). Without the heartbeat URL a dead or sleeping PC goes unnoticed.
- `run_trader.bat` has a good order: heartbeat → pre-flight → backup → pipeline → heartbeat → watchdog → log cleanup.
- **Divergent git histories:** local `main` and GitHub `main` share no ancestor (GitHub has a rewritten history). Every push needs a manual replay; a plain `git pull` or `git push` would fail or create a mess.
- CI actions use Node 20 versions that GitHub is deprecating (warnings only).

### 3.9 Documentation
- README is accurate and honest about results. Two claims overstate: "SHAP explanations per prediction" (on demand only) and "volatility-aware spike detection" (no volume check, see data-gate review).
- `docs/CORE_DOCUMENTATION.md` (1,634 lines) and `docs/SIMPLE_GUIDE.md` (585) are phase-by-phase histories with an update banner; their bodies still describe the retired Streamlit dashboard. `docs/GITHUB_SETUP.md` explains Supabase for CI trading, which is disabled.
- No single current architecture page; README's diagram is the best one.

### 3.10 Portfolio value
- **Strong talking points (verified):** leakage controls and lag rule with tests; SPY known-answer test; honest negative result with TSLA-dependence analysis; risk engine veto; production-DB write guard in tests; nightly pre-flight with golden predictions; data-gate review that quantifies a rule's cost; browser tests with a mock API that blocks external requests.
- **Weak spots an interviewer will find:** red CI badge/run history; dead ensemble code; README claims slightly ahead of code; huge modules; root clutter.
- **Missing evidence:** a forward paper-trading record (the only real test of the frozen model) and a one-page architecture view.

## 4. Prioritised weaknesses

| ID | Pri | Weakness | Evidence | Impact | Fix | Effort |
|---|---|---|---|---|---|---|
| W1 | P0 | Telegram token exposed in old logs, not rotated | session history; `.env` | Anyone with the old logs can message as the bot | User revokes in @BotFather, updates `.env` | 5 min, user only |
| W2 | P1 | CI broken; Python tests never run on GitHub | run 45740661692, step *Dependency audit* | No independent proof the code passes; red history | Upgrade pip/setuptools in CI before audit, or audit the lock file only | Small |
| W0 | P0 | Missed runs disable the stop-loss | `trades` table: META bought 2026-09-29 at $750.80, sold 2026-11-27 at $575.05 (−23%, −$268.44) because no nightly run executed for ~8 weeks | The −8% stop only protects capital while the job runs; outages turn it into an unbounded loss | T1.3 (heartbeat) first; then a run-gap alert in the pre-flight when the last successful run is more than 1 trading day old | Small |
| W3 | P1 | No dead-man's switch configured | `HEALTHCHECK_PING_URL` empty (log 2026-11-26) | A dead or sleeping PC silently stops trading | User creates check, sets URL; verify ping | 10 min, user |
| W4 | P1 | Divergent local vs GitHub history | `git merge-base` has no result | Every push needs manual replay; risk of accidental force-push | Trees differ only by the rewording (18 files, 30 lines). Reset local `main` to `origin/main`, keep the local rules file as an ignored, untracked copy (destructive: needs approval) | Small |
| W5 | P1 | Data-gate spike rule excludes real moves for 724 days | `docs/DATA_GATE_REVIEW.md` | Stock universe silently shrinks after earnings | Decision needed (options A/B/C in review); changes frozen behaviour | Medium, needs approval |
| W6 | P2 | Flaky approvals test | full run 2026-11-26 | Erodes trust in the gate | Reproduce with repeat runs, fix isolation | Small–medium |
| W7 | P2 | Tests needing ignored data fail on fresh clone | 3 tests listed above | CI/fresh clone red for non-code reasons | Skip with a clear reason when data is absent | Small |
| W8 | P2 | Dead/misleading code | `ranking.py:299`, `risk_engine.py:111`, `paper_broker.py:91`, `evaluate.py:387`, `data_loader.py:253/287/809` | Readers believe an ensemble runs; wrong comment on walk-forward | Remove dead code, correct comment; no behaviour change | Small |
| W9 | P2 | Backups on the same disk | `backup.py:68` | Disk failure loses DB and backups | Optional second copy to another drive/folder | Small |
| W10 | P2 | README overclaims (SHAP per prediction, spike detection) | README "Key features" | Credibility in review | Reword to match code | Small |
| W11 | P2 | Stale long docs (Streamlit, Supabase) | `CORE_DOCUMENTATION.md`, `SIMPLE_GUIDE.md`, `GITHUB_SETUP.md` | New readers follow dead instructions | Mark as history, move to `docs/history/`, add short current `ARCHITECTURE.md` | Medium |
| W12 | P3 | Unused runtime dependencies | `kagglehub` unused; research libs in runtime list | Bigger install, more audit surface | Move research libs to an optional file, drop kagglehub | Small (re-run envcheck) |
| W13 | P3 | `/api/chat` unguarded, no Host check | `app.py:264` | Low; local only | Add marker header + Host allow-list | Small |
| W14 | P3 | Root clutter, tracked `scratch/` | repo root | Presentation | Delete untracked `fix_test*.py` (user files: ask), untrack `scratch/` | Small |
| W15 | P3 | No type checking, no coverage numbers | tooling | Missed type bugs; no coverage evidence | Add mypy on a few core packages; coverage report (informational) | Medium |
| W16 | P3 | Tax report defaults to India | `tax_report.py:151` | Odd default for a US project | Confirm intent with user | Small |

Not recommended: rewriting large modules wholesale, adding Docker/Kubernetes/cloud (V1 rules forbid cloud and it adds nothing for one user), adding more ML models (no edge found), or real-money/broker code (forbidden in V1).
