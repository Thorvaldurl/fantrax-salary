"""The run report.

Printed on every run and saved next to the output. Its job is to make the
model's behaviour visible without anyone having to open the spreadsheet — each
section here corresponds to something that was previously invisible and had to
be discovered by analysis after the fact.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from .config import Config
from .model import ModelResult


def _rule(title: str) -> str:
    return f"\n{title}\n{'-' * len(title)}"


def build(result: ModelResult, config: Config) -> str:
    frame = result.frame
    lines: List[str] = []

    lines.append(_rule("Scale"))
    lines.append(f"  highest weighted score   {result.max_score:.4f}")
    lines.append(f"  mean (non-zero) score    {result.mean_score:.4f}")
    lines.append(f"  salary multiplier        {result.salary_multiplier:,.0f}")

    # The whole pool inflating or deflating is the failure mode that is hardest
    # to notice per-player and most damaging to a salary-cap league.
    old_total = frame["Old Salary"].sum()
    new_total = frame["Salary"].sum()
    target_total = frame["TargetSalary"].sum()
    lines.append(_rule("Salary pool"))
    lines.append(f"  current total            {old_total:>12,.0f}")
    lines.append(f"  after this run           {new_total:>12,.0f}  ({new_total / old_total - 1:+.1%})")
    lines.append(f"  at full convergence      {target_total:>12,.0f}  ({target_total / old_total - 1:+.1%})")

    lines.append(_rule("By position"))
    by_position = frame.groupby("Position").agg(
        players=("Salary", "size"),
        mean_salary=("Salary", "mean"),
        max_salary=("Salary", "max"),
    )
    for position, row in by_position.sort_values("mean_salary", ascending=False).iterrows():
        lines.append(
            f"  {str(position):<6} {int(row.players):>4} players   "
            f"mean {row.mean_salary:>8,.0f}   max {row.max_salary:>8,.0f}"
        )

    # Newcomers are the players the model knows least about and, at the week-0
    # run, the ones whose price goes straight into the draft. Worth seeing.
    if config.adp_fallback and f"{config.adp_key}_FPts" in frame.columns:
        priced_on_adp = frame[f"{config.adp_key}_FPts"].notna()
        lines.append(_rule("Priced from draft ADP"))
        lines.append(
            f"  players with no record   {int(priced_on_adp.sum()):>4} "
            f"(ADP inside the first {config.adp_max_pick:,.0f} picks)"
        )
        if priced_on_adp.any():
            shown = frame.loc[priced_on_adp].nlargest(8, "Salary")
            for _, row in shown.iterrows():
                lines.append(
                    f"    {str(row['Name'])[:24]:<24} {str(row['Position']):<4} "
                    f"ADP {row.get('ADP', float('nan')):>6,.1f}   {row['Salary']:>7,.0f}"
                )

    floored = int((frame["Salary"] <= config.salary_floor).sum())
    capped = int((frame["Salary"] >= config.salary_target_max).sum())
    lines.append(_rule("Distribution"))
    lines.append(f"  at the {config.salary_floor:,} floor        {floored:>4} ({floored / len(frame):.0%})")
    lines.append(f"  at the {config.salary_target_max:,} ceiling      {capped:>4}")

    lines.append(_rule("Biggest moves"))
    moves = frame.assign(Change=frame["Salary"] - frame["Old Salary"])
    for label, subset in (
        ("up", moves.nlargest(10, "Change")),
        ("down", moves.nsmallest(10, "Change")),
    ):
        lines.append(f"  {label}:")
        for _, row in subset.iterrows():
            lines.append(
                f"    {str(row['Name'])[:24]:<24} {str(row['Position']):<4} "
                f"{row['Old Salary']:>7,.0f} -> {row['Salary']:>7,.0f}  ({row['Change']:+,.0f})"
            )

    return "\n".join(lines)


def top_salaries(result: ModelResult, count: int = 20) -> pd.DataFrame:
    columns = ["ID", "Name", "Position", "WeightedScore", "Old Salary", "TargetSalary", "Salary"]
    return result.frame[columns].sort_values("Salary", ascending=False).head(count)
