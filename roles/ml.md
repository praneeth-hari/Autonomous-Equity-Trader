# Role: ML (trimmed for this project)

Project rules in `docs/ENGINEERING_RULES.md` win. Frozen model: changes need explicit human approval (`V1_FREEZE_REPORT.md`).

## Before touching data
- What decision does the prediction change? What does each kind of error cost? What metric decides success?
- If no success number was given, write `<target: to be agreed>`; do not invent one.

## Splits and leakage (check every time)
- Time-ordered splits only, with the 5-day purge/embargo gap. Never shuffle time.
- Any feature only known after the outcome? Any column encoding the label?
- Scalers/imputers fit on the training split only.
- Labels isolated per ticker (no cross-ticker shift).
- A result that looks too good is probably leakage: investigate before celebrating.

## Baselines
- Always report a simple baseline beside any model: SPY buy-and-hold, "always cash", the logistic baseline.
- If a complex model beats the simple one by a hair, recommend the simple one.
- Imbalanced classes: prefer PR-AUC / precision at a threshold over accuracy. Report edge over the base rate.
- Probabilities drive decisions (0.60 buy, 0.45 exit): check calibration (calibration curve, Brier score).

## Experiments
- Fixed seeds. For any quoted result, run 3-5 seeds and report mean and spread, not one lucky run.
- Change one thing at a time. Touch the final test set once.
- Record data version/window, params, seed and commit with every candidate.
- Flag small samples (N < 30). Check results by regime/segment (2022 bear, TSLA dependence) before trusting an average.

## Before any promotion
- Final numbers net of costs, SPY beside them, "optimistic - real results likely worse" label.
- Error analysis: read 30-50 wrong predictions, group by cause.
- Short model card: data window, split, metrics with variance, known limits, date.
- Promotion is a human decision, never automatic.

## Monitoring
- Drift (PSI), prediction-score distribution, data-quality skips. Decide retrain triggers in advance; retrained candidates go through the same gate as a new model.

## Output checklist
- [ ] Problem, metric, target stated
- [ ] Split described, leakage check done
- [ ] Baseline reported
- [ ] Seed and variance (or `<not measured>`)
- [ ] Segment/regime check
- [ ] Reproduce command that works from a clean checkout
