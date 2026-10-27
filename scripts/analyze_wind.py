"""Reproduce the corrected baseline/shift diagnosis using local CSVs only."""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.analytics import (  # noqa: E402
    breakdowns,
    correlation,
    evaluate,
    hourly_actuals,
    summary,
)


def analyze() -> dict:
    paths = {
        name: ROOT / "data/processed" / name
        for name in ("forecasts.csv", "actuals_half_hourly.csv")
    }
    forecasts = pd.read_csv(paths["forecasts.csv"])
    actuals = hourly_actuals(pd.read_csv(paths["actuals_half_hourly.csv"]))
    frame = evaluate(forecasts, actuals, date(2026, 1, 2), date(2026, 2, 1))
    shifted = frame[["startTime", "forecast_mw"]].copy()
    series = actuals.set_index("startTime").actual_mw
    for k in range(-3, 4):
        shifted[f"actual_{k}"] = (shifted.startTime + pd.Timedelta(hours=k)).map(series)
    common = shifted.dropna()
    shifts = []
    for k in range(-3, 4):
        sample = common[["forecast_mw", f"actual_{k}"]].rename(
            columns={f"actual_{k}": "actual_mw"}
        )
        shifts.append(
            {"shift_hours": k, **summary(sample), "correlation": correlation(sample)}
        )
    paired = frame.dropna(subset=["forecast_mw", "actual_mw"])
    mean_f, mean_a = float(paired.forecast_mw.mean()), float(paired.actual_mw.mean())
    return {
        "delivery_from": "2026-01-02",
        "delivery_to": "2026-02-01",
        "decision_from": "2026-01-01",
        "decision_to": "2026-01-31",
        "cutoff_time": "09:30",
        "timezone": "UTC",
        "inputs": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in paths.items()
        },
        **summary(frame),
        "horizon_hours": [
            float(frame.horizon_hours.min()),
            float(frame.horizon_hours.max()),
        ],
        "mean_forecast_mw": mean_f,
        "mean_actual_mw": mean_a,
        "correlation": correlation(frame),
        "ratio_of_means_actual_over_forecast": mean_a / mean_f if mean_f else None,
        "bias_by_hour": breakdowns(frame)["hour"],
        "shift_common_count": len(common),
        "shifts": shifts,
        "definitions": {
            "error": "forecast minus actual, MW",
            "mae": "mean absolute paired error, MW",
            "rmse": "square root of mean squared paired error, MW",
            "bias": "mean paired error, MW",
            "mape": "mean absolute error / absolute actual times 100; zero actual excluded only here",
            "p90": "90th percentile absolute paired error, linear interpolation",
            "horizon": "target startTime minus selected publishTime, hours",
            "shift": "forecast at T compared with original actual at T+k; positive k uses later actual; all k use common subset",
            "ratio_of_means": "mean actual / mean forecast on unshifted full-scope pairs",
        },
    }


def main() -> None:
    result = analyze()
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs/regression-baseline.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    shifts = result["shifts"]
    zero = next(s for s in shifts if s["shift_hours"] == 0)["metrics"]["mae_mw"]
    best = min(shifts, key=lambda s: s["metrics"]["mae_mw"])
    improvement = (zero - best["metrics"]["mae_mw"]) / zero * 100 if zero else 0
    table = "\n".join(
        f"| {s['shift_hours']:+} | {s['metrics']['mae_mw']:.6f} | {s['metrics']['rmse_mw']:.6f} | {s['metrics']['bias_mw']:.6f} | {s['correlation']:.6f} |"
        for s in shifts
    )
    hourly_table = "\n".join(
        f"| {g['label']} | {g['metrics']['bias_mw']:.6f} | {g['coverage']['paired']} |"
        for g in result["bias_by_hour"]
    )
    report = f"""# Wind forecast analysis

Decision dates 1–31 January 2026; delivery 2 January–1 February 2026 inclusive.
Cutoff D-1 09:30 UTC, assumed decision timing rather than verified gate closure.
WINDFOR T is assumed to describe [T,T+1h); actuals require both distinct half-hours.
Forecasts are selected independently per hour using only eligible publications.
No source series was shifted, scaled, clipped or zero-filled for production.

## Corrected full-scope baseline

```json
{json.dumps({k: result[k] for k in ("coverage", "metrics", "horizon_hours", "mean_forecast_mw", "mean_actual_mw", "correlation", "ratio_of_means_actual_over_forecast")}, indent=2)}
```

Positive signed bias means forecast wind exceeds observed wind. The ratio is
mean actual / mean forecast, not a mean of pointwise ratios. Correlation measures
co-movement, not agreement in level. The JSON baseline records source CSV hashes,
metric definitions, full precision values and bias for every UTC delivery hour.

## Signed bias by UTC delivery hour

| UTC hour | Bias MW (forecast − actual) | Paired hours |
| --- | ---: | ---: |
{hourly_table}

## Alignment diagnostic

For k=-3..+3, compare forecast at T with original actual at T+k hours; positive k
uses later actuals. No wrapping, extrapolation or extra data. All shifts use the
same **{result["shift_common_count"]}** valid target hours. The unshifted full-scope
result above is separate from this common-subset comparison.

| Shift k, hours | MAE MW | RMSE MW | Bias MW | Correlation |
| --- | ---: | ---: | ---: | ---: |
{table}

Best common-subset MAE is at k={best["shift_hours"]:+}; relative reduction from
common-subset k=0 is {improvement:.3f}% ({zero:.6f} to {best["metrics"]["mae_mw"]:.6f} MW).
This quantifies the alignment sensitivity rather than proving a causal mechanism.
Small changes do not resolve a persistent level bias. Timing, dataset definitions
and generation coverage/scope differences remain hypotheses. **The cause remains
unknown.** There is no supporting evidence here for a causal curtailment claim.
No diagnostic shift is applied to the application.

MAE, RMSE, bias and P90 use paired observations only. P90 uses explicit linear
interpolation. MAPE excludes zero actuals only from its own denominator and reports
eligible/excluded counts; empty metrics are null. Horizon buckets are [0,12),
[12,24), [24,36), [36,48), [48,72), [72,+infinity) hours. UTC hour/day breakdowns
use the same definitions. P90 is historical magnitude, not a calibrated one-sided
procurement guarantee; demand, prices and risk preferences are outside scope.

Reproduce offline from the root:
`backend/.venv/bin/python scripts/analyze_wind.py`.
"""
    (ROOT / "docs/analysis.md").write_text(report)
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("coverage", "metrics", "horizon_hours", "shift_common_count")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
