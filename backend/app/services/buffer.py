"""Descriptive historical risk context, never a purchasing optimization."""


def explain(result: dict, first: str, last: str, clock: str) -> dict:
    count = result["coverage"]["paired"]
    p90 = result["metrics"]["p90_absolute_error_mw"]
    bias = result["metrics"]["bias_mw"]
    if not count:
        text = (
            "Indicative context unavailable: no paired observations for this selection."
        )
    else:
        direction = (
            "Positive bias means expected wind was higher than observed "
            "in this sample, "
            "potentially increasing additional procurement needs."
            if bias > 0
            else "Negative bias means expected wind was lower than observed "
            "in this sample."
            if bias < 0
            else "Signed bias is zero in this sample."
        )
        text = (
            f"Indicative only: P90 absolute error {p90:,.1f} MW and signed bias "
            f"{bias:+,.1f} MW across {count} paired hours, delivery {first} to {last}, "
            f"D-1 {clock} UTC cutoff. {direction} P90 is a historical error magnitude, "
            "not a calibrated one-sided purchasing guarantee. Do not add bias to P90 "
            "as an optimal buffer. Procurement optimization needs demand, prices "
            "and risk "
            "preferences beyond this wind-only scope."
        )
    return {"p90_mw": p90, "bias_mw": bias, "sample_count": count, "message": text}
