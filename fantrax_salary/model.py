"""The salary model.

This is a faithful, vectorised port of the original `Sal Updates 1.py`. The
numbers it produces are identical — `tests/test_model.py` asserts that against
the original implementation, row for row.

Deliberately unchanged for now: the scoring itself. Known weaknesses are
catalogued in the project's GitHub issue rather than silently fixed here, so
that this refactor stays reviewable.

The pipeline:

    normalise each stat column to [0, 1]
        -> blend seasons into a single weighted score
        -> map that score onto a salary band
        -> move only part of the way from the current salary (damping)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .config import Config


@dataclass
class ModelResult:
    """Per-player output plus the scale factors used to produce it."""

    frame: pd.DataFrame
    max_score: float
    mean_score: float
    salary_multiplier: float


def normalise(frame: pd.DataFrame, columns: list) -> pd.DataFrame:
    """Scale each column to [0, 1] independently, preserving NaN.

    Equivalent to sklearn's MinMaxScaler (which skips NaN when fitting and
    passes it through when transforming), but without the dependency — the
    only thing scikit-learn was being used for was this three-line formula.
    """
    out = frame.copy()
    for column in columns:
        values = out[column]
        low, high = values.min(), values.max()
        span = high - low
        # A constant column has no spread to scale; sklearn maps it to 0.
        out[column] = (values - low) / span if span else values * 0.0
    return out


def weighted_score(frame: pd.DataFrame, config: Config) -> pd.Series:
    """Blend the seasons into one score per player.

    A season only contributes when the player has *both* FPts and FP/G for it,
    and the weights are renormalised over whatever did contribute — so a player
    missing a season is not penalised as though they had scored zero.
    """
    score = pd.Series(0.0, index=frame.index)
    weight_total = pd.Series(0.0, index=frame.index)

    for season in config.seasons:
        fpts, fpg = frame[f"{season.key}_FPts"], frame[f"{season.key}_FP/G"]
        present = fpts.notna() & fpg.notna()
        score += season.weight * (fpts.fillna(0.0) + fpg.fillna(0.0)).where(present, 0.0)
        weight_total += season.weight * present

    return (score / weight_total.where(weight_total > 0)).astype(float)


def compute(frame: pd.DataFrame, config: Config) -> ModelResult:
    """Run the full model over a merged player frame.

    `frame` must carry `Old Salary` plus the eight stat columns named
    `<season key>_FPts` / `<season key>_FP/G`.
    """
    data = normalise(frame, config.stat_columns)
    data["WeightedScore"] = weighted_score(data, config)

    max_score = data["WeightedScore"].max()
    # Zero and negative scores are excluded so a long tail of unplayed players
    # cannot drag the league-average anchor down.
    mean_score = data.loc[data["WeightedScore"] > 0, "WeightedScore"].mean()

    # Anchor the band: an average score earns `salary_target_min`, the best
    # score in the pool earns `salary_target_max`, and everything between is
    # linear in score/mean.
    span = config.salary_target_max - config.salary_target_min
    multiplier = span / ((max_score / mean_score) - 1)
    target = config.salary_target_min + (data["WeightedScore"] / mean_score - 1) * multiplier
    data["TargetSalary"] = target.where(target >= config.salary_floor, config.salary_floor)

    # Ease toward the target instead of snapping to it, so a single unusual
    # week cannot reprice the league.
    salary = data["Old Salary"] + (data["TargetSalary"] - data["Old Salary"]) * config.damping
    salary = salary.round(config.rounding)
    data["Salary"] = salary.where(salary >= config.salary_floor, config.salary_floor)

    return ModelResult(
        frame=data,
        max_score=float(max_score),
        mean_score=float(mean_score),
        salary_multiplier=float(multiplier),
    )


def write_upload_csv(
    template: pd.DataFrame,
    result: ModelResult,
    destination,
    salary_column: int = 5,
) -> None:
    """Write the commissioner-import CSV.

    Fantrax has no API for writing salaries — a commissioner CSV upload is the
    only route — so the template's exact column layout and lack of a header row
    are preserved byte for byte, with only the salary column replaced.
    """
    salaries = result.frame.set_index("ID")["Salary"].to_dict()
    out = template.copy()
    out[salary_column] = out[0].map(salaries)

    # A blank salary here would be uploaded to Fantrax as a real change. Refuse
    # rather than emit a file that silently mis-prices anyone — this is the last
    # gate before the numbers become live, and --force must not be able to skip it.
    blank = out[salary_column].isna()
    if blank.any():
        names = out.loc[blank, 2].head(5).tolist()
        raise ValueError(
            f"{int(blank.sum())} players would be uploaded with no salary, e.g. {names}. "
            "Refusing to write the upload file."
        )

    out.to_csv(destination, index=False, header=False)


def write_workbook(result: ModelResult, destination) -> None:
    """Write the full working sheet, for eyeballing what the model did."""
    result.frame.to_excel(destination, index=False)
