"""The original script's arithmetic, still guarded.

`reference_implementation.run` is the original script. The pipeline must
reproduce it exactly *with the scoring changes switched off* — that is what
keeps every later change deliberate rather than accidental. The changes
themselves are tested separately, against what they are supposed to fix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fantrax_salary import config as config_module  # noqa: E402
from fantrax_salary import model, sources, validate  # noqa: E402

import reference_implementation  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def cfg():
    """The original model: original weights, no newcomer handling of any kind."""
    return config_module.load(
        seasons=list(config_module.LEGACY_SEASONS),
        blank_zero_seasons=False,
        adp_fallback=False,
        rate_shrinkage=False,
    )


@pytest.fixture(scope="module")
def current_cfg():
    """What a run actually uses today."""
    return config_module.load()


@pytest.fixture(scope="module")
def expected():
    return reference_implementation.run(
        template_path=REPO / "data" / "template" / "blank_2026-27.csv",
        gw_path=REPO / "data" / "current" / "gw1.csv",
        seasons_dir=REPO / "data" / "seasons",
    )


@pytest.fixture(scope="module")
def actual(cfg):
    return model.compute(sources.from_csv(cfg), cfg)


def test_same_number_of_players(actual, expected):
    assert len(actual.frame) == len(expected)


def test_player_order_preserved(actual, expected):
    """Row order matters: the upload CSV is written positionally."""
    pd.testing.assert_series_equal(
        actual.frame["ID"].reset_index(drop=True),
        expected["ID"].reset_index(drop=True),
    )


@pytest.mark.parametrize("column", ["WeightedScore", "TargetSalary", "Salary"])
def test_columns_match_reference(actual, expected, column):
    pd.testing.assert_series_equal(
        actual.frame[column].reset_index(drop=True),
        expected[column].reset_index(drop=True),
        check_names=False,
        rtol=1e-12,
        atol=1e-9,
    )


def test_final_salaries_are_exactly_equal(actual, expected):
    """No tolerance at all on the number that actually gets uploaded."""
    assert actual.frame["Salary"].tolist() == expected["Salary"].tolist()


def test_normalise_matches_sklearn():
    """The hand-rolled scaler replaces MinMaxScaler exactly, NaNs included."""
    from sklearn.preprocessing import MinMaxScaler

    frame = pd.DataFrame(
        {
            "a": [1.0, 2.0, 3.0, None, 5.0],
            "b": [-4.0, 0.0, None, 2.5, 9.0],
            "flat": [7.0, 7.0, 7.0, 7.0, 7.0],
        }
    )
    ours = model.normalise(frame, ["a", "b", "flat"])
    theirs = pd.DataFrame(
        MinMaxScaler().fit_transform(frame[["a", "b", "flat"]]),
        columns=["a", "b", "flat"],
    )
    pd.testing.assert_frame_equal(ours, theirs, rtol=1e-12)


def test_upload_csv_preserves_template_shape(actual, cfg, tmp_path):
    template = sources.load_template(cfg)
    destination = tmp_path / "upload.csv"
    model.write_upload_csv(template, actual, destination)

    written = pd.read_csv(destination, header=None)
    assert written.shape == template.shape
    # Everything except the salary column must survive untouched.
    for column in (0, 1, 2, 3, 4):
        pd.testing.assert_series_equal(written[column], template[column], check_dtype=False)
    assert written[5].notna().all()


def test_validation_passes_on_the_committed_data(cfg):
    template = sources.load_template(cfg)
    frame = sources.from_csv(cfg)
    findings = validate.run_all(template, frame, cfg)
    assert findings.ok, findings.report()


def test_missing_season_is_a_hard_error(cfg, tmp_path):
    broken = config_module.load(seasons_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        sources.from_csv(broken)


def test_unknown_source_rejected(cfg):
    with pytest.raises(ValueError, match="unknown source"):
        sources.load(config_module.load(source="nonsense"))


VETERANS = 60


def _newcomer_frame():
    """A pool big enough to fit an ADP curve on, plus the four cases under test.

    Rows 0..VETERANS-1 are veterans with a full record. Then:
      VETERANS+0  a newcomer, drafted mid-way
      VETERANS+1  a newcomer taken early
      VETERANS+2  a newcomer past the end of the draft
      VETERANS+3  a newcomer nobody drafted at all (no ADP)

    The newcomers carry Fantrax's literal 0.0 for the seasons they were not in
    the league, which is the thing being fixed.
    """
    rows = []
    for i in range(VETERANS):
        # A plausible spread: output falls off as draft position rises.
        rate = 7.5 - 5.0 * (i / VETERANS)
        rows.append(
            {
                "ID": f"*v{i}*",
                "Name": f"Veteran {i}",
                "Position": ["G", "D", "M", "F"][i % 4],
                "Old Salary": 3000.0 + 100.0 * i,
                "2627_FPts": rate * 33,
                "2627_FP/G": rate,
                "2526_FPts": rate * 34,
                "2526_FP/G": rate + 0.1,
                "2425_FPts": rate * 32,
                "2425_FP/G": rate - 0.1,
                "2324_FPts": rate * 30,
                "2324_FP/G": rate - 0.2,
                "ADP": 5.0 + 4.5 * i,
            }
        )

    blank = {
        "2526_FPts": 0.0, "2526_FP/G": 0.0,
        "2425_FPts": 0.0, "2425_FP/G": 0.0,
        "2324_FPts": 0.0, "2324_FP/G": 0.0,
    }
    newcomers = [
        ("Newcomer", "D", 120.0, 3.5, 150.0),
        ("Early pick", "F", 130.0, 4.0, 40.0),
        ("Late pick", "G", 60.0, 2.0, 285.0),
        ("Undrafted", "M", 50.0, 1.8, None),
    ]
    for index, (name, position, fpts, fpg, adp) in enumerate(newcomers):
        rows.append(
            {
                "ID": f"*n{index}*", "Name": name, "Position": position,
                "Old Salary": 2000.0,
                "2627_FPts": fpts, "2627_FP/G": fpg,
                "ADP": adp if adp is not None else float("nan"),
                **blank,
            }
        )
    return pd.DataFrame(rows)


VETERAN_ROW = 0
NEWCOMER_ROW = VETERANS
EARLY_PICK_ROW = VETERANS + 1
LATE_PICK_ROW = VETERANS + 2


def test_zero_season_becomes_missing(cfg):
    """"0 points in 0 games" is absence of data, not evidence of being bad."""
    frame = _newcomer_frame()
    blanked = model.blank_zero_seasons(frame, cfg)

    assert blanked.loc[VETERAN_ROW, "2526_FPts"] > 0  # the veteran is untouched
    assert pd.isna(blanked.loc[NEWCOMER_ROW, "2526_FPts"])  # the 0.0 is now blank
    assert pd.isna(blanked.loc[NEWCOMER_ROW, "2526_FP/G"])


def test_blanking_zeros_lifts_a_newcomer_above_a_genuine_zero(cfg):
    """The point of the change: the newcomer is no longer averaged against 0."""
    frame = _newcomer_frame()
    off = model.weighted_score(model.normalise(frame, cfg.stat_columns), cfg)
    on = model.weighted_score(
        model.normalise(model.blank_zero_seasons(frame, cfg), cfg.stat_columns), cfg
    )
    assert on[NEWCOMER_ROW] > off[NEWCOMER_ROW]
    # And the veteran, who has a full record, is unaffected by the change.
    assert on[VETERAN_ROW] == pytest.approx(off[VETERAN_ROW])


def test_adp_only_fills_players_without_a_record(current_cfg):
    frame = model.blank_zero_seasons(_newcomer_frame(), current_cfg)
    filled = model.adp_season(frame, current_cfg)

    assert pd.isna(filled.loc[VETERAN_ROW, "adp_FPts"]), "history must beat ADP"
    assert not pd.isna(filled.loc[NEWCOMER_ROW, "adp_FPts"])
    assert not pd.isna(filled.loc[EARLY_PICK_ROW, "adp_FPts"])


def test_adp_ignores_picks_past_the_end_of_the_draft(current_cfg):
    """ADP 285 is 'undrafted', which is not an opinion worth pricing on."""
    frame = model.blank_zero_seasons(_newcomer_frame(), current_cfg)
    filled = model.adp_season(frame, current_cfg)
    assert pd.isna(filled.loc[LATE_PICK_ROW, "adp_FPts"])


def test_adp_ranks_an_early_pick_above_a_later_one(current_cfg):
    frame = model.blank_zero_seasons(_newcomer_frame(), current_cfg)
    filled = model.adp_season(frame, current_cfg)
    assert filled.loc[EARLY_PICK_ROW, "adp_FP/G"] > filled.loc[NEWCOMER_ROW, "adp_FP/G"]


def test_adp_fallback_can_be_switched_off(cfg, current_cfg):
    """With the flag off the ADP columns are ignored even when populated."""
    frame = model.adp_season(model.blank_zero_seasons(_newcomer_frame(), current_cfg), current_cfg)
    assert frame["adp_FPts"].notna().any(), "fixture should have something to ignore"

    scaled = model.normalise(frame, cfg.stat_columns)
    off = model.weighted_score(scaled, cfg)
    on = model.weighted_score(scaled.assign(**{
        "adp_FPts": frame["adp_FPts"], "adp_FP/G": frame["adp_FP/G"],
    }), current_cfg)
    assert off[NEWCOMER_ROW] != on[NEWCOMER_ROW]
    assert off[VETERAN_ROW] == pytest.approx(on[VETERAN_ROW])


def test_adp_needs_no_adp_column(current_cfg):
    """CSV exports without an ADP column must still run."""
    frame = _newcomer_frame().drop(columns=["ADP"])
    filled = model.adp_season(frame, current_cfg)
    assert filled["adp_FPts"].isna().all()


def _rate_shrinkage_frame():
    """One position (D), enough "regular" players to build a stable prior,
    plus the specific small-sample cases under test.

    Row order:
      0..9    regular defenders, 15 games, FP/G clustered around 5.0
      10      REGULAR_ANCHOR — 15 games, FP/G 9.0 (the pool's genuine best;
              must NOT move, or the scale's own anchor would be corrupted)
      11      HOT_STREAK — 1 game, FP/G 10.0 (a fluke; should be pulled down)
      12      COLD_STREAK — 1 game, FP/G -2.0 (bad luck, not badness; should
              be pulled UP toward the prior, not left looking like a bust)
      13      MID_SAMPLE — 5 games, FP/G 5.0 (near the prior already; should
              barely move)

    All at "2526" (a completed season) with matching, made-up numbers at
    "2627" (the projection slot) that imply a tiny, meaningless games count —
    this is what must NOT be shrunk, since it isn't a real observation.
    """
    regulars = [
        {"Name": f"Regular{i}", "Position": "D", "Old Salary": 5000,
         "2526_FPts": 5.0 * 15 + i, "2526_FP/G": 5.0 + i / 15}
        for i in range(10)
    ]
    specials = [
        {"Name": "RegularAnchor", "Position": "D", "Old Salary": 9000,
         "2526_FPts": 9.0 * 15, "2526_FP/G": 9.0},
        {"Name": "HotStreak", "Position": "D", "Old Salary": 3000,
         "2526_FPts": 10.0, "2526_FP/G": 10.0},
        {"Name": "ColdStreak", "Position": "D", "Old Salary": 3000,
         "2526_FPts": -2.0, "2526_FP/G": -2.0},
        {"Name": "MidSample", "Position": "D", "Old Salary": 4000,
         "2526_FPts": 25.0, "2526_FP/G": 5.0},
    ]
    frame = pd.DataFrame(regulars + specials)
    frame.insert(0, "ID", [f"*r{i}*" for i in range(len(frame))])
    # 2627 (projection): a tiny made-up ratio, so its implied "games played"
    # (2) would trigger heavy shrinkage if the season-0 exclusion is broken.
    frame["2627_FPts"] = 6.0
    frame["2627_FP/G"] = 3.0
    for key in ("2425", "2324"):
        frame[f"{key}_FPts"] = float("nan")
        frame[f"{key}_FP/G"] = float("nan")
    frame["ADP"] = float("nan")
    return frame


REGULAR_ANCHOR = 10
HOT_STREAK = 11
COLD_STREAK = 12
MID_SAMPLE = 13


def test_shrinkage_leaves_established_players_alone(current_cfg):
    """The point of the min_games cutoff: a real full-season rate is not noise."""
    frame = _rate_shrinkage_frame()
    shrunk = model.shrink_rates(frame, current_cfg)
    assert shrunk.loc[REGULAR_ANCHOR, "2526_FP/G"] == pytest.approx(9.0)


def test_shrinkage_pulls_a_small_sample_hot_streak_down(current_cfg):
    frame = _rate_shrinkage_frame()
    shrunk = model.shrink_rates(frame, current_cfg)
    rate = shrunk.loc[HOT_STREAK, "2526_FP/G"]
    assert rate < 10.0
    assert rate > 5.0  # still pulled toward, not all the way to, the prior


def test_shrinkage_pulls_a_small_sample_cold_streak_up(current_cfg):
    """A bad one-game sample is bad luck, not proof of being a bad player."""
    frame = _rate_shrinkage_frame()
    shrunk = model.shrink_rates(frame, current_cfg)
    assert shrunk.loc[COLD_STREAK, "2526_FP/G"] > -2.0


def test_shrinkage_does_not_touch_the_projection_season(current_cfg):
    """FPts/FP-G on the projection slot is not a real games-played count."""
    frame = _rate_shrinkage_frame()
    shrunk = model.shrink_rates(frame, current_cfg)
    pd.testing.assert_series_equal(
        shrunk["2627_FP/G"], frame["2627_FP/G"], check_names=False
    )


def test_shrinkage_can_be_switched_off(cfg):
    frame = _rate_shrinkage_frame()
    shrunk = model.shrink_rates(frame, cfg)
    pd.testing.assert_series_equal(
        shrunk["2526_FP/G"], frame["2526_FP/G"], check_names=False
    )


def test_current_model_prices_every_player(current_cfg):
    """The live configuration must still produce a complete upload."""
    result = model.compute(sources.from_csv(current_cfg), current_cfg)
    assert result.frame["Salary"].notna().all()
    assert (result.frame["Salary"] >= current_cfg.salary_floor).all()


def test_current_model_lifts_newcomers_off_the_floor(cfg, current_cfg):
    """Regression guard for the behaviour this change exists to produce."""
    frame = sources.from_csv(current_cfg)
    before = model.compute(frame, cfg).frame
    after = model.compute(frame, current_cfg).frame

    newcomers = frame["2526_FPts"].fillna(0) <= 0
    assert newcomers.sum() > 100, "the committed data should contain many newcomers"
    # Newcomers as a group must be scored higher relative to the pool than they
    # were when their absence was read as a zero.
    assert (
        after.loc[newcomers, "WeightedScore"].mean() / after["WeightedScore"].mean()
        > before.loc[newcomers, "WeightedScore"].mean() / before["WeightedScore"].mean()
    )


def _projection_shaped_frame(games_implied, rows=60):
    """A current-season frame whose FPts/FP-per-G implies `games_implied` games."""
    per_game = [3.0 + (i % 5) * 0.4 for i in range(rows)]
    return pd.DataFrame({
        "Name": [f"P{i}" for i in range(rows)],
        "2627_FPts": [p * games_implied for p in per_game],
        "2627_FP/G": per_game,
    })


def test_projection_used_mid_season_is_flagged(current_cfg):
    """A full-season projection at gameweek 3 implies ~33 games. Catch it."""
    cfg3 = config_module.load(gameweek=3)
    findings = validate.check_current_season_is_results(_projection_shaped_frame(33), cfg3)
    assert findings.warnings
    assert "projection" in findings.warnings[0].lower()
    assert findings.ok, "this is a warning, not a hard failure"


def test_real_year_to_date_is_not_flagged():
    cfg3 = config_module.load(gameweek=3)
    findings = validate.check_current_season_is_results(_projection_shaped_frame(3), cfg3)
    assert not findings.warnings


def test_projection_is_fine_at_gameweek_zero():
    """Before a ball is kicked the projection is the only thing that exists."""
    cfg0 = config_module.load(gameweek=0)
    findings = validate.check_current_season_is_results(_projection_shaped_frame(33), cfg0)
    assert not findings.warnings


def test_upload_refuses_to_write_blank_salaries(actual, cfg, tmp_path):
    """A player the model could not price must never reach the upload file."""
    broken = model.ModelResult(
        frame=actual.frame.assign(Salary=actual.frame["Salary"].mask(lambda s: s.index < 3)),
        max_score=actual.max_score,
        mean_score=actual.mean_score,
        salary_multiplier=actual.salary_multiplier,
    )
    template = sources.load_template(cfg)
    with pytest.raises(ValueError, match="no salary"):
        model.write_upload_csv(template, broken, tmp_path / "upload.csv")
    assert not (tmp_path / "upload.csv").exists()
