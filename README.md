# Autonomous Equity Trading Platform

An ML-driven, risk-first paper-trading platform that ranks US equities, enforces strict risk rules, and runs hands-free every trading day.

> **Paper trading only.** There is no real-money or live-broker code in this project. Nothing here is financial advice.

![Python](https://img.shields.io/badge/python-3.11-blue)
![scikit-learn](https://img.shields.io/badge/ML-scikit--learn%20%7C%20XGBoost%20%7C%20LightGBM-orange)
![Streamlit](https://img.shields.io/badge/dashboard-Streamlit-red)
![Tests](https://img.shields.io/badge/tests-pytest-green)

## Goal

**Do not lose money.** Break-even is acceptable and profit is a bonus. When in doubt the system stays in cash.

The frozen V1 strategy trails SPY buy-and-hold in historical walk-forward tests (see [V1_FREEZE_REPORT.md](V1_FREEZE_REPORT.md)). Forward paper trading exists to measure the strategy honestly, not to prove it works.

---

## What it does

Every trading day the pipeline:

1. Pulls market data (Yahoo Finance, with a fallback provider) and **validates** it before anything uses it
2. Computes scale-invariant technical features (trend, momentum, RSI, MACD, volatility, volume, relative strength vs SPY)
3. Scores each stock with an ML model: *probability the stock rises more than 1% over the next 5 trading days*
4. Adjusts scores with news sentiment, earnings proximity, sector rotation and macro regime
5. Runs everything through a **risk engine** with veto power (stop-loss, take-profit, position cap, cash reserve, market regime filter)
6. Simulates fills with transaction costs and slippage, stores everything in a database, and shows it on a dashboard

## Key features

- **Leakage-safe ML**: features use only past data, labels are isolated per ticker, and a 5-day embargo gap separates train and test sets. Adversarial leakage tests are part of the suite.
- **Honest evaluation**: walk-forward validation across 2021 bull, 2022 bear, 2023 rebound and 2024 late-cycle regimes. Reports edge over the base rate, flags small samples (N < 30), and raises an alarm on "too good to be true" metrics.
- **Risk engine with veto power**: -8% stop-loss, +15% take-profit, signal exit below 0.45, max 3 positions, 15% cash reserve, minimum trade size.
- **Market regime filter**: no new buys when SPY is below its 200-day moving average, plus crash circuit breakers (SPY -5% in 5 days or -10% in 20 days).
- **Intelligence layers**: VADER news sentiment, earnings blackout windows, sector rotation ranking, and FRED macro indicators.
- **Explainability and monitoring**: SHAP explanations per prediction and PSI-based model drift alarms that cut position size or pause buying.
- **Human-in-the-loop promotion**: models are never auto-promoted; a person reviews the evaluation report and runs the promotion step.
- **Hands-off operation**: Windows Task Scheduler jobs for the daily run, a morning health check, daily status digest and dashboard launch, with missed-run detection.
- **Data validation gate**: rejects impossible prices, volatility-aware spike detection, and NYSE-calendar-aware gap checks.
- **Storage**: SQLAlchemy repository layer with SQLite by default and PostgreSQL by changing one setting.

## Architecture

```mermaid
flowchart LR
    A[Market data<br/>yfinance + fallback] --> B[Validation gate]
    B --> C[Feature engineering<br/>15+ features]
    C --> D[Active ML model<br/>P rise &gt; 1% in 5d]
    D --> E[Intelligence layers<br/>sentiment / earnings / sector / macro]
    E --> F[Ranking]
    F --> G[Risk engine<br/>veto power]
    G --> H[Portfolio allocation]
    H --> I[Paper broker]
    I --> J[(Database)]
    J --> K[Streamlit dashboard]
```

## Strategy parameters

All defaults live in `config/settings.py` and can be overridden through `.env`.

| Parameter | Default |
|---|---|
| Starting capital | $10,000 (paper) |
| Prediction horizon / win threshold | 5 trading days / +1% |
| Buy bar / signal exit | P ≥ 0.60 / P < 0.45 |
| Stop-loss / take-profit | -8% / +15% |
| Max positions / cash reserve | 3 / 15% |
| Simulated cost per trade | 0.2% |
| Regime filter | SPY 200-day moving average |
| Universe | 25 large-cap US stocks across 8 sectors, benchmark SPY |

## Tech stack

| Area | Tools |
|---|---|
| Language | Python 3.11 |
| Data | pandas, numpy, yfinance, Alpha Vantage, pandas-market-calendars |
| ML | scikit-learn (HistGradientBoosting, Logistic Regression), XGBoost, LightGBM, SHAP, Optuna |
| NLP / alerts | VaderSentiment, python-telegram-bot, Google GenAI |
| Storage | SQLAlchemy, SQLite / PostgreSQL |
| Dashboard | Streamlit, Plotly |
| Scheduling | Windows Task Scheduler (PowerShell), APScheduler |
| Config / tests | pydantic-settings, python-dotenv, pytest |

## Project structure

```
ai-stock-trader/
├── config/          # Central settings (the only place env vars are read)
├── src/
│   ├── data/        # Market data fetching + validation gate
│   ├── features/    # Feature engineering
│   ├── ml/          # Dataset/labels, training, walk-forward evaluation
│   ├── ranking/     # Opportunity ranking and conviction tiers
│   ├── risk/        # Risk engine (stops, caps, regime filter)
│   ├── portfolio/   # Order sizing and fee accounting
│   ├── trading/     # Paper broker
│   ├── backtest/    # Day-by-day backtesting engine
│   ├── pipeline/    # Daily pipeline orchestrator and scheduler
│   └── db/          # ORM models and repository layer
├── dashboard/       # Streamlit monitoring dashboard
├── tests/           # pytest suite
├── data/            # Raw snapshots, processed data, trained models (git-ignored)
└── reports/         # Generated reports
```

## Getting started

### Prerequisites
- Python 3.11
- Windows is recommended for the scheduler scripts (`.bat` / `.ps1`). The core pipeline and dashboard run anywhere Python does.

### Install

```bash
git clone https://github.com/praneeth-hari/ai-stock-trader.git
cd ai-stock-trader

python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
```

Edit `.env` to set your capital, tickers and thresholds. Optional keys:

| Variable | Used for |
|---|---|
| `FRED_API_KEY` | Live macro indicators (free at fred.stlouisfed.org) |
| `ALPHA_VANTAGE_API_KEY` | Fallback market data provider |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram alerts |
| `ALERT_EMAIL_*` | Email alerts |

Without the optional keys the system degrades gracefully and skips that layer.

### Run

```bash
python -m src.pipeline.scheduler --force   # run the daily pipeline once
streamlit run streamlit_app.py             # open the dashboard
pytest                                     # run the test suite
```

Windows helper scripts: `run_trader.bat` (daily run with logging), `run_daily_status.bat`, `run_health_check.bat`, `run_retrain.bat`, `run_weekly_summary.bat`, `start_dashboard.bat`, and `setup_task_scheduler.ps1` (schedule the daily run).

### Automate (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_task_scheduler.ps1
```

This registers five tasks: the daily run (Mon-Fri 5:00 PM), a 9:00 AM health check, a startup health check, a dashboard launcher, and a 6:00 PM status digest. Remove them with `remove_task_scheduler.ps1`.

## Results

Historical tuning has stopped. No configuration showed a durable edge over SPY. Final benchmark for the configured strategy (2-year walk-forward, net of 0.2% per trade; optimistic, real results likely worse):

| Period | Frozen strategy (CAGR / max DD / Sharpe) | SPY buy & hold | SPY only when ≥ 200-day SMA |
|---|---|---|---|
| 2007–2016 | 1.09% / −20.7% / 0.18 | 4.66% / −56.5% / 0.32 | 3.56% / −21.1% / 0.37 |
| 2017–2026 | 1.26% / −31.4% / 0.19 | 13.40% / −34.1% / 0.78 | 7.83% / −25.1% / 0.69 |

- The strategy trails SPY buy-and-hold across both test periods. Forward results will probably trail SPY. The purpose of forward trading is to measure, not to prove.
- **TSLA dependence:** TSLA was 32–35% of the strategy's trades. Excluding TSLA, the strategy lost money in both periods (−$1,959 and −$703).
- **Method vs. model file:** The historical figures test the walk-forward method (a new model every 6 months). They do not test the exact frozen model file, which was trained on 2019–2023 data and can't be honestly backtested over those years. Forward trading is the first real test of this file.

## Documentation

- [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md): master plan and locked decisions
- [CLAUDE.md](CLAUDE.md): always-on engineering rules
- [docs/SIMPLE_GUIDE.md](docs/SIMPLE_GUIDE.md): plain-English walkthrough of each phase
- [docs/CORE_DOCUMENTATION.md](docs/CORE_DOCUMENTATION.md): technical reference
- [V1_FREEZE_REPORT.md](V1_FREEZE_REPORT.md): frozen V1 configuration and benchmark results

> **Setup:** See [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md) for the Supabase and secrets walkthrough.

## Disclaimer

This software is for educational and research purposes only. It does not place real trades and is not financial advice. Past performance, simulated or otherwise, does not predict future results.

## Author

Built by [@praneeth-hari](https://github.com/praneeth-hari).

## License

No license has been chosen yet. Add one (MIT is a common choice for portfolio projects) before inviting reuse.

## Status

V1 is frozen for forward paper trading. Real-money trading is out of scope until the checklist in [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) section 12 is satisfied.
