# Engineering Roadmap

Source: `docs/ENGINEERING_AUDIT.md` (2026-11-26). Weakness IDs (W#) refer to that file.
Rule for every task: smallest change that fixes the real problem, a test or a command as proof, no change to the frozen
model or locked strategy values without explicit approval.

Status: ☐ pending · ◐ in progress · ☑ done (with evidence)

## Phase 1: Critical fixes (essential)

| ID | Pri | Task | Files | Acceptance criteria | Verify by | Depends | Effort | Status |
|---|---|---|---|---|---|---|---|---|
| T1.1 | P0 | Rotate the Telegram bot token (user does it) | `.env` | Old token revoked; new token works | `python -m src.alerts.watchdog test` sends a message | none | 5 min | ☐ |
| T1.2 | P1 | Fix CI: upgrade pip/setuptools before `pip-audit` | `.github/workflows/tests.yml` | All 3 CI jobs green on push | `gh run list` shows success | none | 30 min | ◐ local fix done (pip/setuptools upgraded before audit); CI result pending push |
| T1.3 | P1 | Set up the dead man's switch (user creates the check; I verify) | `.env` | Ping received at start and end of a run | healthchecks.io shows pings; log no longer says "not configured" | none | 15 min | ☐ |
| T1.4 | P1 | Re-join local and GitHub history (reset local `main` to `origin/main`, keep the rules file locally and ignored) | git only | `git merge-base main origin/main` returns a commit; normal `git push` works | git commands | approval (destructive) | 15 min | ☑ 2026-11-27: `git merge-base main origin/main` = `5063c52`; old history kept in branch `local-history-backup`; rules file kept local and ignored |

## Phase 2: Test reliability (essential)

| ID | Pri | Task | Files | Acceptance criteria | Verify by | Depends | Effort | Status |
|---|---|---|---|---|---|---|---|---|
| T2.1 | P2 | Find and fix the flaky approvals test | `tests/api/test_ops_routes.py`, maybe `src/api/ops_routes.py` | Passes 20 full-suite-order runs in a row | repeated `pytest tests/api` + one full run | none | 1–2 h | ☐ |
| T2.2 | P2 | Skip data-dependent tests with a clear reason when the ignored data is absent | 3 test files | Fresh clone: those 3 show SKIPPED with reason; main folder: they still run and pass | run in a fresh worktree and in the main folder | T1.2 | 30 min | ☑ 2026-11-27 (pulled into Phase 1): main folder 3 passed; clean checkout full suite 918 passed, 0 failed, 6 skipped with reasons |

## Phase 3: Correctness and code clarity (essential, no behaviour change)

| ID | Pri | Task | Files | Acceptance criteria | Verify by | Depends | Effort | Status |
|---|---|---|---|---|---|---|---|---|
| T3.1 | P2 | Remove dead ensemble branch and unused variables; fix shadowed imports; correct the walk-forward comment | `ranking.py`, `risk_engine.py`, `paper_broker.py`, `evaluate.py`, `data_loader.py`, `tune.py`, `scorer.py`, `gate_review.py` | `ruff --select F841,F811` clean on `src`; golden predictions unchanged; full suite passes | ruff + envcheck + pytest | T2.1 | 1 h | ☐ |
| T3.2 | P2 | Add F841/F811 to the lint gate so they stay fixed | `ruff.toml` | Gate fails on a new unused variable | `ruff check` | T3.1 | 10 min | ☐ |

## Phase 4: Operations hardening (recommended)

| ID | Pri | Task | Files | Acceptance criteria | Verify by | Depends | Effort | Status |
|---|---|---|---|---|---|---|---|---|
| T4.1 | P2 | Optional second backup copy on another drive or folder (`BACKUP_MIRROR_DIR`) | `src/ops/backup.py`, `config/settings.py`, test | When set, newest backup is mirrored and verified; when empty, nothing changes | unit test + one real run | none | 1 h | ☐ |
| T4.2 | P3 | Guard `/api/chat` with the marker header; reject unexpected `Host` headers | `src/api/app.py`, `ops_routes.py`, web `api.ts`, tests | Requests without header or with a foreign Host get 403; web app still works | API tests + Playwright | none | 1 h | ☐ |
| T4.3 | P3 | Move research-only libraries (xgboost, lightgbm, optuna, shap?) to `requirements-research.txt`; drop unused `kagglehub` | requirements files, lock, envcheck | Nightly pre-flight passes; research scripts document the extra install | envcheck + full suite | T1.2 | 1 h | ☐ |

## Phase 5: Data-gate decision (needs your decision; changes frozen behaviour)

| ID | Pri | Task | Files | Acceptance criteria | Verify by | Depends | Effort | Status |
|---|---|---|---|---|---|---|---|---|
| T5.1 | P1 | Choose option A/B/C from `docs/DATA_GATE_REVIEW.md` and implement it behind a setting, defaulting to the frozen behaviour until you switch it on | `src/data/validation.py`, settings, tests, freeze report change log | Real earnings gaps on high volume pass; the TSLA-type bad print is still rejected; frozen mode reproduces today's results exactly | `python -m src.ops.gate_review` before/after + tests | approval | 2–3 h | ☐ |

## Phase 6: Documentation and presentation (recommended)

| ID | Pri | Task | Files | Acceptance criteria | Verify by | Depends | Effort | Status |
|---|---|---|---|---|---|---|---|---|
| T6.1 | P2 | Correct README overclaims (SHAP on demand, spike rule) and add a CI badge once green | `README.md` | Every README feature maps to a code path | manual check against audit table | T1.2 | 20 min | ☐ |
| T6.2 | P2 | Write a short current `docs/ARCHITECTURE.md`; move phase histories (`CORE_DOCUMENTATION`, `SIMPLE_GUIDE`, `GITHUB_SETUP`) to `docs/history/` with a note | docs | One current page explains components and the nightly flow | read-through | none | 1–2 h | ☐ |
| T6.3 | P3 | Untrack `scratch/`; delete the 18 ignored `fix_test*.py` files (ask first: they are yours) | repo root | Clean root listing | `git ls-files` | approval | 10 min | ☐ |
| T6.4 | P3 | Forward paper-trading record page: days run, trades, net return vs SPY, with the optimistic label | API + web or a report script | Shows only measured numbers | tests + real data | 30+ trading days of runs | 2 h | ☐ |

## Optional (only if you want more depth)

- T7.1 P3: mypy on `src/risk`, `src/trading`, `src/pipeline` (strict-optional), fix what it finds.
- T7.2 P3: coverage report in CI (informational, not a gate).
- T7.3 P3: confirm the tax report's `country="India"` default.

## Deliberately not planned

Docker, cloud hosting, Kubernetes, more ML models, live broker code, wholesale refactors of the large modules.
They add risk or appearance, not reliability, for a single-user paper system under V1 rules.
