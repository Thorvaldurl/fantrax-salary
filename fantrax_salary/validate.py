"""Input checks.

The original script had none, so a wrong, stale or half-downloaded file
produced plausible-looking salaries instead of an error. Everything here exists
because it is a mistake that can actually be made on a Saturday morning.

`Problem`s are fatal. `Warning`s are printed and the run continues.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pandas as pd

from .config import Config

STALE_AFTER_DAYS = 7


@dataclass
class Findings:
    problems: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def report(self) -> str:
        lines = []
        for problem in self.problems:
            lines.append(f"  ERROR   {problem}")
        for warning in self.warnings:
            lines.append(f"  WARN    {warning}")
        return "\n".join(lines)


def check_template(template: pd.DataFrame) -> Findings:
    findings = Findings()

    if template.shape[1] <= 5:
        findings.problems.append(
            f"template has {template.shape[1]} columns, expected at least 6 "
            "(id, rank, name, team, position, salary)"
        )
        return findings

    ids = template.iloc[:, 0]
    duplicates = ids[ids.duplicated()].tolist()
    if duplicates:
        findings.problems.append(f"template has duplicate player ids: {duplicates[:5]}")

    salaries = pd.to_numeric(template.iloc[:, 5], errors="coerce")
    if salaries.isna().any():
        count = int(salaries.isna().sum())
        findings.problems.append(f"{count} template rows have a non-numeric current salary")

    return findings


def check_coverage(frame: pd.DataFrame, config: Config) -> Findings:
    """Every player must be priceable, and each season must actually be present."""
    findings = Findings()

    for season in config.seasons:
        fpts = frame[f"{season.key}_FPts"]
        missing = int(fpts.isna().sum())
        if missing == len(frame):
            findings.problems.append(
                f"{season.label}: no player matched — wrong file, or ids do not line up"
            )
        elif missing:
            share = missing / len(frame)
            # Old seasons legitimately miss players who were not yet in the
            # league; the newest season missing anyone is far more suspicious.
            threshold = 0.05 if season is config.seasons[0] else 0.60
            if share > threshold:
                findings.warnings.append(
                    f"{season.label}: {missing} of {len(frame)} players have no data ({share:.0%})"
                )

    scoreable = frame[[f"{s.key}_FPts" for s in config.seasons]].notna().any(axis=1)
    if not scoreable.all():
        orphans = frame.loc[~scoreable, "Name"].head(5).tolist()
        findings.problems.append(
            f"{int((~scoreable).sum())} players have no stats in any season, e.g. {orphans}"
        )

    return findings


def check_current_season_is_results(frame: pd.DataFrame, config: Config) -> Findings:
    """Catch a preseason projection still being used once the season is played.

    The heaviest input is meant to be the season in progress. Fantrax's Players
    page defaults to "Projected - Season", so an export taken without changing
    that dropdown is a *forecast of the whole season* -- and it looks completely
    normal, which is how it went unnoticed long enough to be worth a check.

    The tell is implied games played, `FPts / FP-per-G`. A full-season
    projection implies about 33 games for a regular starter from day one; real
    year-to-date figures imply roughly the number of gameweeks actually played.

    Measured over the *established* players only, not the whole pool. The pool
    is strongly bimodal -- fringe players are projected a handful of
    appearances, so the overall median sits around 7 and would barely clear the
    threshold, while the top scorers sit at a flat 32. Taking the median of the
    busiest players is what makes the signal unambiguous.

    Skipped at gameweek 0, where a projection is the only thing that exists and
    is legitimately what you want for the draft. It also necessarily stops
    discriminating late in the season, when a full-season projection and the
    actual year-to-date imply a similar number of games -- by which point the
    two have largely converged anyway.
    """
    findings = Findings()
    if config.gameweek < 1:
        return findings

    season = config.seasons[0]
    fpts = pd.to_numeric(frame.get(f"{season.key}_FPts"), errors="coerce")
    per_game = pd.to_numeric(frame.get(f"{season.key}_FP/G"), errors="coerce")
    if fpts is None or per_game is None:
        return findings

    playable = per_game.notna() & (per_game.abs() > 0.01) & fpts.notna()
    if playable.sum() < 30:
        return findings

    regulars = fpts[playable].nlargest(min(200, int(playable.sum())))
    implied = (fpts[regulars.index] / per_game[regulars.index]).median()
    # Generous: only complain when the file implies far more football than has
    # actually been played, so an ordinary lag never trips it.
    if implied > config.gameweek + 3:
        hint = 'set Stats to the "- YTD" option (not "Projected - Season") before exporting'
        if season.api_code.startswith("PROJECTION_"):
            hint += f", and for --source api change {season.key}'s api_code off {season.api_code}"
        findings.warnings.append(
            f"{season.label}: implies ~{implied:.0f} games played, but it is gameweek "
            f"{config.gameweek}. This looks like Fantrax's season projection rather than "
            f"results to date. On the Players page {hint}."
        )
    return findings


def check_freshness(config: Config) -> Findings:
    """Warn when a stats file is older than the template it will be joined to.

    This is the check that catches the failure the repo actually shipped: an
    output regenerated from inputs that had moved on underneath it.
    """
    findings = Findings()
    if config.source != "csv":
        return findings

    template_age = config.template.stat().st_mtime
    now = time.time()

    for season in config.seasons:
        path = (config.seasons_dir / season.csv).resolve()
        if not path.exists():
            continue
        age_days = (now - path.stat().st_mtime) / 86400
        if season is config.seasons[0] and age_days > STALE_AFTER_DAYS:
            findings.warnings.append(
                f"{season.label} ({path.name}) is {age_days:.0f} days old — "
                "re-export it before running, or the salaries will lag reality"
            )
        if path.stat().st_mtime < template_age - 86400:
            findings.warnings.append(
                f"{season.label} ({path.name}) is older than the template — "
                "check you downloaded both in the same session"
            )
    return findings


def run_all(template: pd.DataFrame, frame: pd.DataFrame, config: Config) -> Findings:
    combined = Findings()
    for findings in (
        check_template(template),
        check_coverage(frame, config),
        check_current_season_is_results(frame, config),
        check_freshness(config),
    ):
        combined.problems.extend(findings.problems)
        combined.warnings.extend(findings.warnings)
    return combined
