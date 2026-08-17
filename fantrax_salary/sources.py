"""Loading the inputs.

Two interchangeable sources produce the same merged frame:

    csv  Files exported by hand from Fantrax. Reproducible and offline, and
         the only mode whose numbers match historical runs.
    api  Pulled live from Fantrax. No manual downloads, no stale files, and
         every season is scored under the *current* league's scoring rules —
         which the hand-exported CSVs are not (see README).

The two do not produce identical numbers. That is a property of the data, not
a bug: see the "Which source should I use?" section of the README.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from .config import Config

# Columns of the commissioner template, which has no header row.
TEMPLATE_ID = 0
TEMPLATE_NAME = 2
TEMPLATE_TEAM = 3
TEMPLATE_POSITION = 4
TEMPLATE_SALARY = 5


def load_template(config: Config) -> pd.DataFrame:
    """Read the blank commissioner spreadsheet, headerless and verbatim.

    This is both the roster of players to price and the exact layout the
    finished CSV must be uploaded in, so it is never reshaped.
    """
    if not config.template.exists():
        raise FileNotFoundError(
            f"commissioner template not found: {config.template}\n"
            "Download it from Fantrax: League -> Commissioner -> Player Salaries -> Export."
        )
    return pd.read_csv(config.template, header=None)


def base_frame(template: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ID": template.iloc[:, TEMPLATE_ID],
            "Name": template.iloc[:, TEMPLATE_NAME],
            "Team": template.iloc[:, TEMPLATE_TEAM],
            "Position": template.iloc[:, TEMPLATE_POSITION],
            "Old Salary": template.iloc[:, TEMPLATE_SALARY],
        }
    )


def _merge(frame: pd.DataFrame, stats: Dict[str, pd.DataFrame], config: Config) -> pd.DataFrame:
    """Attach each season's FPts and FP/G as its own pair of columns.

    Draft ADP rides along from the current-season export, which is the one
    carrying the upcoming draft's average pick. It is not part of the score
    itself; `model.adp_season` decides whether any given player needs it.
    """
    for season in config.seasons:
        source = stats[season.key]
        missing = {"ID", "FPts", "FP/G"} - set(source.columns)
        if missing:
            raise ValueError(f"season {season.key} is missing columns: {sorted(missing)}")
        frame = frame.merge(
            source[["ID", "FPts", "FP/G"]].rename(
                columns={"FPts": f"{season.key}_FPts", "FP/G": f"{season.key}_FP/G"}
            ),
            on="ID",
            how="left",
        )

    current = stats[config.seasons[0].key]
    if "ADP" in current.columns:
        frame = frame.merge(current[["ID", "ADP"]], on="ID", how="left")
    else:
        frame["ADP"] = pd.NA
    frame["ADP"] = _numeric(frame["ADP"])
    return frame


def _numeric(series: pd.Series) -> pd.Series:
    """Fantrax exports thousands separators inside quoted numbers."""
    if series.dtype.kind in "fi":
        return series
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def from_csv(config: Config) -> pd.DataFrame:
    template = load_template(config)
    stats = {}
    for season in config.seasons:
        path = (config.seasons_dir / season.csv).resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"stats file for {season.label} not found: {path}\n"
                "Export it from Fantrax with 'All players' selected (not just available)."
            )
        stats[season.key] = pd.read_csv(path)
    return _merge(base_frame(template), stats, config)


def from_api(config: Config) -> pd.DataFrame:
    # Imported here so that CSV mode — the default — needs no HTTP stack.
    from .api import FantraxClient

    template = load_template(config)
    client = FantraxClient(config.league_id, config.api_version)
    stats = {season.key: client.player_stats(season.api_code) for season in config.seasons}
    return _merge(base_frame(template), stats, config)


def load(config: Config) -> pd.DataFrame:
    if config.source == "csv":
        return from_csv(config)
    if config.source == "api":
        return from_api(config)
    raise ValueError(f"unknown source: {config.source!r} (expected 'csv' or 'api')")
