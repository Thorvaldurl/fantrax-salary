"""Configuration for the salary update.

Every tunable number the model uses lives here, in one place, with a name.
Nothing in `model.py` contains a magic number.

Precedence, lowest to highest:  dataclass defaults  <  JSON config file  <  CLI flags
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fantrax league IDs. A Fantrax league gets a NEW id every season; the
# `leagueHistoryId` is what ties them together across years.
CURRENT_LEAGUE_ID = "0pit050kmss1l8bh"  # 2026-27
LEAGUE_HISTORY_ID = "7yc861vomdpxpueg"

# Version string the internal Fantrax RPC checks. When it drifts too far behind
# the live site the API answers STALE_CLIENT and nothing works. See README.
DEFAULT_API_VERSION = "185.2.5"


@dataclass(frozen=True)
class SeasonWeight:
    """One input season and how much it counts toward the score.

    `key`      column prefix used internally
    `weight`   contribution to the weighted score
    `csv`      filename under data/seasons (or data/current) for CSV mode
    `api_code` Fantrax `seasonOrProjection` code for API mode
    """

    key: str
    weight: float
    csv: str
    api_code: str
    label: str


# NOTE: the ordering here is newest-first and is load-bearing only for display.
# `key` values are kept identical to the original script so that column names,
# and therefore the produced numbers, are unchanged.
#
# On the weights: the current-season slot used to carry 0.70, which meant three
# quarters of every salary came from Fantrax's *preseason projection* rather
# than from anything that happened. That projection also carries a bias of its
# own -- moving weight onto real results drops goalkeepers by around 2,500
# (Petrovic 10,500 -> 8,000, Martinez 9,500 -> 6,800) and lifts attackers
# (Haaland 10,800 -> 11,900), i.e. it was stacking a second positional bias on
# top of the one already in the scoring system. See docs/scoring-review.md.
#
# It is not dropped to zero, because the promoted clubs have no Premier League
# record at all and the projection is the only thing standing between their
# squads and the floor: at 0.00 the number of floored players rises to 335,
# against 264 here and 295 under the old weighting.
#
# The two oldest seasons were 0.04 and 0.01, which moved a score by well under
# 1% -- decoration rather than signal. They now do something.
DEFAULT_SEASONS: List[SeasonWeight] = [
    SeasonWeight("2627", 0.20, "../current/gw1.csv", "PROJECTION_0_926_SEASON", "2026-27 (projected)"),
    SeasonWeight("2526", 0.60, "2526.csv", "SEASON_925_YEAR_TO_DATE", "2025-26"),
    SeasonWeight("2425", 0.15, "2425.csv", "SEASON_924_YEAR_TO_DATE", "2024-25"),
    SeasonWeight("2324", 0.05, "2324.csv", "SEASON_923_YEAR_TO_DATE", "2023-24"),
]

# The original script's weighting, kept so the reference-implementation test can
# pin the legacy arithmetic exactly. Not used by a normal run.
LEGACY_SEASONS: List[SeasonWeight] = [
    replace(DEFAULT_SEASONS[0], weight=0.70),
    replace(DEFAULT_SEASONS[1], weight=0.25),
    replace(DEFAULT_SEASONS[2], weight=0.04),
    replace(DEFAULT_SEASONS[3], weight=0.01),
]


@dataclass(frozen=True)
class Config:
    # --- paths -------------------------------------------------------------
    repo_root: Path = REPO_ROOT
    template: Path = REPO_ROOT / "data" / "template" / "blank_2026-27.csv"
    seasons_dir: Path = REPO_ROOT / "data" / "seasons"
    output_dir: Path = REPO_ROOT / "output"

    # --- data source -------------------------------------------------------
    source: str = "csv"  # "csv" | "api"
    league_id: str = CURRENT_LEAGUE_ID
    api_version: str = DEFAULT_API_VERSION

    # --- model -------------------------------------------------------------
    seasons: List[SeasonWeight] = field(default_factory=lambda: list(DEFAULT_SEASONS))

    salary_floor: int = 2500  # nothing may be priced below this
    salary_target_min: int = 4000  # salary assigned to a league-average score
    salary_target_max: int = 15000  # salary assigned to the best score in the pool
    damping: float = 0.5  # fraction of (target - current) applied per run
    rounding: int = -2  # round to nearest 100

    # --- players with no history ------------------------------------------
    # A Fantrax export gives a player who was not in the league last season a
    # literal 0.0, not a blank. Scored as written, "did not play" is
    # indistinguishable from "played and was useless", and 324 of the 709
    # players in the current pool are in that position.
    blank_zero_seasons: bool = True

    # Draft ADP as a fallback signal for exactly those players. It is the
    # league market's own estimate and is the only independent read available
    # on someone with no Premier League record. See `model.adp_season`.
    adp_fallback: bool = True
    adp_weight: float = 0.25  # weight of the ADP pseudo-season, when it applies
    adp_key: str = "adp"  # column prefix, mirroring a SeasonWeight key

    # Past this pick the draft has stopped expressing an opinion: 10 teams x 25
    # roster spots is 250 picks, and everyone after that shares an ADP near the
    # bottom of the list. In the 2025-26 backtest 62% of newcomers with an ADP
    # over 250 never played a minute, so reading value into those numbers
    # promotes third-choice keepers off the floor for no reason.
    adp_max_pick: float = 250.0

    # The ADP curve has to be fitted on players who have a record, and those
    # players are established squad members: a veteran drafted 200th still
    # plays, a newcomer drafted 200th often does not. The fitted curve
    # therefore sits above the newcomer reality and is pulled back toward it.
    # 0.7 is the middle of the flat region of the backtest (0.6-0.8 are within
    # 0.01 RMSE of each other); re-check it if the league size changes.
    adp_shrinkage: float = 0.7

    # --- small samples -------------------------------------------------------
    # A rate (FP/G) measured over a handful of games is mostly noise. Without
    # this, a good player who was rotated or injured scores identically to a
    # genuinely bad one -- both have a low-games FP/G, and the model has no way
    # to tell "this is who they are" from "small unrepresentative sample". See
    # `model.shrink_rates`.
    rate_shrinkage: bool = True

    # How strongly a season's rate is pulled toward the positional prior:
    # adjusted = (FPts + k*prior) / (GP + k). k is in the same units as games
    # played, so 7 means "trust the player's own rate about as much as 7
    # games' worth of the prior" -- the middle of the 5-10 range that is
    # standard for this kind of shrinkage. A player with a full season (~35
    # games) is barely moved; a 1-2 game sample is pulled hard toward the
    # positional average, in both directions.
    shrinkage_k: float = 7.0

    # How many games counts as "enough of a sample" to help build the prior
    # itself. Low-games players are still shrunk (that's the point) -- this
    # only controls who else in the pool counts as an "established" player
    # when computing what a typical rate looks like at a position.
    shrinkage_min_games: int = 10

    # --- run ---------------------------------------------------------------
    gameweek: int = 1
    dry_run: bool = False

    def season(self, key: str) -> SeasonWeight:
        for s in self.seasons:
            if s.key == key:
                return s
        raise KeyError(f"no season configured with key {key!r}")

    @property
    def stat_columns(self) -> List[str]:
        """The eight normalised columns, in the original script's order."""
        cols = [f"{s.key}_FPts" for s in self.seasons]
        cols += [f"{s.key}_FP/G" for s in self.seasons]
        return cols

    def output_path(self, suffix: str) -> Path:
        return self.output_dir / f"SalGW{self.gameweek}{suffix}"


def _coerce_paths(raw: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(raw)
    for key in ("repo_root", "template", "seasons_dir", "output_dir"):
        if key in out:
            path = Path(out[key]).expanduser()
            out[key] = path if path.is_absolute() else (REPO_ROOT / path)
    if "seasons" in out:
        # From a JSON file these are dicts; from a caller (or a test pinning the
        # legacy weights) they are already SeasonWeight instances.
        out["seasons"] = [
            s if isinstance(s, SeasonWeight) else SeasonWeight(**s) for s in out["seasons"]
        ]
    return out


def load(config_file: Optional[Path] = None, **overrides: Any) -> Config:
    """Build a Config from defaults, an optional JSON file, and CLI overrides."""
    cfg = Config()
    if config_file is not None:
        if not config_file.exists():
            raise FileNotFoundError(f"config file not found: {config_file}")
        raw = json.loads(config_file.read_text(encoding="utf-8"))
        cfg = replace(cfg, **_coerce_paths(raw))
    clean = {k: v for k, v in overrides.items() if v is not None}
    if clean:
        cfg = replace(cfg, **_coerce_paths(clean))
    return cfg
