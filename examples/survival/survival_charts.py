"""SAShiny chart render callback for the survival example (spec 8.5).

The declarative chart spec draws points, lines, bars, histograms and boxes. A
forest plot also needs confidence-interval bars, a log axis, a reference line
at HR = 1 and the model's term order, so the demo app draws it with this
callback instead:

    modules.program_server("survival", contract, engine,
                           chart_render={"forest_plot": forest_chart})

Without the callback (for example in the command-line runner) the contract's
declarative spec is the fallback: hazard ratios as points.
"""

from __future__ import annotations

from typing import Any

# Candidate axis breaks for a log hazard-ratio axis.
_BREAKS = (0.05, 0.1, 0.2, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 10, 20)


def _forest_frame(value: dict[str, Any]) -> Any:
    """Return the chart value as a data frame: lower-case names, one row per term."""
    import pandas as pd  # noqa: PLC0415 - optional dependency of the chart backends

    names = [str(c["name"]).lower() for c in value.get("columns", [])]
    df = pd.DataFrame(value.get("rows", []), columns=names)
    for col in ("hazard_ratio", "hr_lower", "hr_upper"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["hazard_ratio"] > 0].reset_index(drop=True)
    # First model term on top, as in the SAS graph.
    df["pos"] = list(range(len(df), 0, -1))
    if "hr_ci" not in df:
        df["hr_ci"] = df["hazard_ratio"].map(lambda v: f"{v:.2f}")
    df["hr_ci"] = df["hr_ci"].fillna("").astype(str)
    return df


def forest_chart(value: dict[str, Any], spec: dict[str, Any] | None) -> Any:
    """Draw a plotnine forest plot of the Cox hazard ratios (``work.cox_estimates``)."""
    from plotnine import (  # noqa: PLC0415 - optional dependency
        aes,
        annotate,
        element_blank,
        geom_point,
        geom_segment,
        geom_text,
        geom_vline,
        ggplot,
        labs,
        scale_x_log10,
        scale_y_continuous,
        theme,
        theme_bw,
    )

    df = _forest_frame(value)
    if df.empty:
        return _note_chart(value)
    header = next(
        (
            c.get("label") or "HR (CI)"
            for c in value["columns"]
            if str(c["name"]).lower() == "hr_ci"
        ),
        "HR (CI)",
    )
    lower = df["hr_lower"].fillna(df["hazard_ratio"])
    upper = df["hr_upper"].fillna(df["hazard_ratio"])
    lo = min(float(lower.min()), 1.0) / 1.15
    hi = max(float(upper.max()), 1.0) * 1.15
    text_x = hi * 1.1
    xmax = text_x * (hi / lo) ** 0.5  # room for the HR (CI) column on the log axis
    breaks = [b for b in _BREAKS if lo <= b <= hi]
    df["lower"], df["upper"], df["text_x"] = lower, upper, text_x

    del spec  # the layout is fixed; the declarative spec is the fallback
    return (
        ggplot(df)
        + geom_vline(xintercept=1, linetype="dashed", color="#888888")
        + geom_segment(aes(x="lower", xend="upper", y="pos", yend="pos"), color="#c0504d", size=0.8)
        + geom_point(aes(x="hazard_ratio", y="pos"), shape="s", size=3, color="#1f3c88")
        + geom_text(aes(x="text_x", y="pos", label="hr_ci"), ha="left", size=9)
        + annotate(
            "text", x=text_x, y=len(df) + 0.6, label=header, ha="left", size=9, fontweight="bold"
        )
        + scale_x_log10(breaks=breaks, labels=[f"{b:g}" for b in breaks], limits=(lo, xmax))
        + scale_y_continuous(
            breaks=list(df["pos"]), labels=list(df["term"]), limits=(0.5, len(df) + 0.8)
        )
        + labs(
            x="Hazard ratio (log scale)",
            y="",
            caption="Hazard ratio < 1: lower hazard of progression or death than the reference.",
        )
        + theme_bw()
        + theme(panel_grid_minor=element_blank(), panel_grid_major_y=element_blank())
    )


def _note_chart(value: dict[str, Any]) -> Any:
    """Draw the program's note (for example "Cox model not fitted: ...") when there are no hazard ratios."""
    from plotnine import annotate, ggplot, labs, theme_void  # noqa: PLC0415

    names = [str(c["name"]).lower() for c in value.get("columns", [])]
    notes = [
        str(row[names.index("hr_ci")])
        for row in value.get("rows", [])
        if "hr_ci" in names and row[names.index("hr_ci")]
    ]
    text = notes[0] if notes else "No hazard ratios to plot."
    if not text.lower().startswith("cox model not fitted"):
        text = f"Cox model not fitted: {text}" if notes else text
    return (
        ggplot()
        + annotate("text", x=0, y=0, label=text, size=11)
        + labs(title="Hazard ratios")
        + theme_void()
    )


__all__ = ["forest_chart"]
