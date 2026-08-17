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

import numpy as np
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


def blank_zero_seasons(frame: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Turn "0 points in 0 games" into missing data, which is what it means.

    Fantrax exports every player in the current pool for every season, so a
    player who was not in the league last year comes back as a literal 0.0
    rather than a blank. The score cannot tell that apart from a player who
    turned out and contributed nothing, and the difference is large: 324 of the
    709 players in the current pool have never played a Premier League minute
    under this league's scoring.

    Only the pair being zero counts. A player who genuinely played and finished
    on exactly 0.00 total *and* 0.00 per game has, for pricing purposes, given
    us no more information than the newcomer anyway.
    """
    out = frame.copy()
    for season in config.seasons:
        fpts_column, fpg_column = f"{season.key}_FPts", f"{season.key}_FP/G"
        fpts, fpg = out[fpts_column], out[fpg_column]
        did_not_play = (fpts.fillna(0.0) == 0.0) & (fpg.fillna(0.0) == 0.0)
        out[fpts_column] = fpts.mask(did_not_play)
        out[fpg_column] = fpg.mask(did_not_play)
    return out


def adp_season(frame: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Add an ADP-derived pseudo-season for players with no history at all.

    A player new to the league has no results to price from, but the league's
    own draft has already estimated them: average draft position is the
    market's read on a player, and it is available before a ball is kicked.

    The ADP-to-output relationship is fitted from the pool itself rather than
    hard-coded, so it re-calibrates every season and cannot go stale. Draft
    value decays hyperbolically — the gap between picks 1 and 20 is worth far
    more than the gap between 200 and 220 — so the fit is on log(ADP).

    On the 2025-26 season this recovers newcomer FP/G with RMSE 1.02 against
    1.23 for assuming pool-average and 2.50 for the current behaviour of
    scoring them near the bottom.

    The column is filled only for players with no *completed* season to their
    name — the ones whose price would otherwise rest entirely on a third
    party's preseason forecast. Anyone with an actual Premier League record is
    priced on it and never sees this column, because a record beats a forecast.
    """
    out = frame.copy()
    fpts_column, fpg_column = f"{config.adp_key}_FPts", f"{config.adp_key}_FP/G"
    out[fpts_column] = float("nan")
    out[fpg_column] = float("nan")

    if "ADP" not in out.columns:
        return out

    adp = pd.to_numeric(out["ADP"], errors="coerce")
    # seasons[0] is the in-progress season, which preseason is a projection —
    # having one of those is not a record. History means a completed season.
    completed = config.seasons[1:] or config.seasons
    has_history = pd.concat(
        [out[f"{s.key}_FPts"].notna() for s in completed], axis=1
    ).any(axis=1)

    # Fit on players who have both an ADP and a real record — the newcomers we
    # are about to price are excluded, so nothing is being fitted to itself.
    reference = config.seasons[0].key
    fit_rows = adp.notna() & (adp > 0) & out[f"{reference}_FPts"].notna()
    if fit_rows.sum() < 30:
        return out

    x = np.log(adp[fit_rows])
    coefficients = {
        column: np.polyfit(x, out.loc[fit_rows, column], 1)
        for column in (f"{reference}_FPts", f"{reference}_FP/G")
    }

    target = ~has_history & adp.notna() & (adp > 0) & (adp <= config.adp_max_pick)
    if not target.any():
        return out

    predictor = np.log(adp[target])
    for source_column, destination in (
        (f"{reference}_FPts", fpts_column),
        (f"{reference}_FP/G", fpg_column),
    ):
        predicted = np.polyval(coefficients[source_column], predictor) * config.adp_shrinkage
        # The fit is linear, so clip to the range actually observed rather than
        # letting it run off either end.
        observed = out.loc[fit_rows, source_column]
        out.loc[target, destination] = predicted.clip(observed.min(), observed.max())

    return out


def weighted_score(frame: pd.DataFrame, config: Config) -> pd.Series:
    """Blend the seasons into one score per player.

    A season only contributes when the player has *both* FPts and FP/G for it,
    and the weights are renormalised over whatever did contribute — so a player
    missing a season is not penalised as though they had scored zero.

    The ADP pseudo-season, when enabled, joins the same renormalisation. It is
    only ever populated for players with nothing else, so for everyone with a
    record it contributes nothing and the blend is unchanged.
    """
    score = pd.Series(0.0, index=frame.index)
    weight_total = pd.Series(0.0, index=frame.index)

    inputs = [(f"{s.key}_FPts", f"{s.key}_FP/G", s.weight) for s in config.seasons]
    if config.adp_fallback:
        inputs.append(
            (f"{config.adp_key}_FPts", f"{config.adp_key}_FP/G", config.adp_weight)
        )

    for fpts_column, fpg_column, weight in inputs:
        if fpts_column not in frame.columns:
            continue
        fpts, fpg = frame[fpts_column], frame[fpg_column]
        present = fpts.notna() & fpg.notna()
        score += weight * (fpts.fillna(0.0) + fpg.fillna(0.0)).where(present, 0.0)
        weight_total += weight * present

    return (score / weight_total.where(weight_total > 0)).astype(float)


def compute(frame: pd.DataFrame, config: Config) -> ModelResult:
    """Run the full model over a merged player frame.

    `frame` must carry `Old Salary` plus the eight stat columns named
    `<season key>_FPts` / `<season key>_FP/G`.
    """
    prepared = frame
    if config.blank_zero_seasons:
        prepared = blank_zero_seasons(prepared, config)
    if config.adp_fallback:
        prepared = adp_season(prepared, config)

    # Normalising after the two steps above matters: a column full of
    # newcomers' zeros would otherwise set the bottom of the [0, 1] scale.
    data = normalise(prepared, config.stat_columns)
    if config.adp_fallback:
        # The ADP columns are predictions *of* the reference season, so they
        # have to be put on the reference season's scale. Normalising them over
        # their own range instead would silently promote the best-drafted
        # newcomer to the top of the league.
        reference = config.seasons[0].key
        for suffix in ("FPts", "FP/G"):
            source = prepared[f"{reference}_{suffix}"]
            low, high = source.min(), source.max()
            span = high - low
            column = f"{config.adp_key}_{suffix}"
            data[column] = (prepared[column] - low) / span if span else prepared[column] * 0.0

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
