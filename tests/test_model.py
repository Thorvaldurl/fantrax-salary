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
        projection_fallback=False,
        rate_shrinkage=False,
        # The original script repriced every player, owned or not. Freezing
        # existing contracts is a later, deliberate divergence like the three
        # above, so the oracle runs without it -- and this also keeps the
        # reference tests offline, since rosters are a live lookup.
        freeze_rostered=False,
    )


@pytest.fixture(scope="module")
def current_cfg():
    """What a run actually uses today."""
    return config_module.load()


@pytest.fixture(scope="module")
def expected():
    result = reference_implementation.run(
        template_path=REPO / "data" / "template" / "blank_2026-27.csv",
        gw_path=REPO / "data" / "current" / "gw1.csv",
        seasons_dir=REPO / "data" / "seasons",
    )
    # One known, deliberate divergence from the original script: it floors with
    # `df.loc[df[col] < floor, col] = floor`, and a NaN comparison is always
    # False, so a player with no data in any season keeps a NaN salary instead
    # of being floored. model.py fixes this on purpose (see write_upload_csv's
    # docstring -- a blank salary would upload as a real, silent mis-price) and
    # reference_implementation.py is deliberately left unpatched to stay a
    # faithful port of the original, so the fix belongs here instead. This was
    # never exercised before the template was refreshed to a live export
    # containing players brand new to the pool, with no history in any of the
    # (separately still-stale) committed season files.
    # Patch it the way model.py does, at the *target*, then let the original
    # script's own damping and rounding run on from there. Flooring the final
    # salary instead would snap these players straight to 2,500 and skip the
    # half-step every other player gets -- which is a different number whenever
    # their current salary is above the floor, and the reason this patch has to
    # mirror the pipeline rather than just clamp both ends of it.
    result["TargetSalary"] = result["TargetSalary"].where(result["TargetSalary"].notna(), 2500)
    unpriced = result["Salary"].isna()
    salary = result["Old Salary"] + (result["TargetSalary"] - result["Old Salary"]) / 2
    result.loc[unpriced, "Salary"] = salary[unpriced].round(-2)
    result["Salary"] = result["Salary"].where(result["Salary"] >= 2500, 2500)
    return result


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
    """The committed data validates cleanly, once genuinely-unpriceable newcomers
    are set aside.

    Not the same claim as "no ERROR fires". The template is a live export and
    will periodically contain players brand new enough to the pool that they
    have no season history *and* no ADP -- zero signal of any kind. Flagging
    those with a hard ERROR (requiring a conscious `--force`) is
    `check_coverage` doing exactly its documented job, not a defect; the real
    regression this test guards against is anyone *else* unexpectedly losing
    coverage. See `test_current_model_prices_every_player` for the guarantee
    that actually matters for a real run: every player, these included, still
    ends up priced once `model.compute` applies the ADP fallback.
    """
    template = sources.load_template(cfg)
    frame = sources.from_csv(cfg)
    findings = validate.run_all(template, frame, cfg)

    scoreable = frame[[f"{s.key}_FPts" for s in cfg.seasons]].notna().any(axis=1)
    orphans = frame.loc[~scoreable]
    assert orphans["ADP"].isna().all(), (
        "an orphaned player has an ADP and should have been rescued by the "
        "ADP fallback -- this is a real coverage regression, not the known "
        "zero-signal-newcomer case"
    )

    remaining = [p for p in findings.problems if "no stats in any season" not in p]
    assert not remaining, findings.report()


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

    The same figures are mirrored into "2627", the in-progress slot, so that
    what happens to that column is decided purely by what the slot is declared
    to hold: a projection must come back untouched, year-to-date actuals must
    be shrunk exactly like any other real season.
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
    frame["2627_FPts"] = frame["2526_FPts"]
    frame["2627_FP/G"] = frame["2526_FP/G"]
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


def test_shrinkage_does_not_touch_a_projection_slot():
    """FPts/FP-G on a projection is not a real games-played count.

    Pinned against the legacy seasons, which are the ones still declaring the
    current slot as `PROJECTION_...`. Shrinking a forecast's implied sample
    size is the mistake this exclusion exists to prevent.
    """
    projection_cfg = config_module.load(seasons=list(config_module.LEGACY_SEASONS))
    assert projection_cfg.seasons[0].is_projection
    frame = _rate_shrinkage_frame()
    shrunk = model.shrink_rates(frame, projection_cfg)
    pd.testing.assert_series_equal(
        shrunk["2627_FP/G"], frame["2627_FP/G"], check_names=False
    )


def test_shrinkage_does_touch_the_current_season_once_it_is_actuals(current_cfg):
    """The in-season slot is the smallest sample in the model, not an exception.

    Once the current season carries year-to-date results, a two-game rate in it
    is exactly the noise this function exists to damp. Excluding `seasons[0]`
    by position instead of by content is what let a two-game newcomer out-score
    Haaland at gameweek 3.
    """
    assert not current_cfg.seasons[0].is_projection
    frame = _rate_shrinkage_frame()
    shrunk = model.shrink_rates(frame, current_cfg)
    # Same column, same numbers as 2526 — so it must get the same treatment.
    assert shrunk.loc[HOT_STREAK, "2627_FP/G"] < 10.0
    assert shrunk.loc[COLD_STREAK, "2627_FP/G"] > -2.0
    assert shrunk.loc[REGULAR_ANCHOR, "2627_FP/G"] == pytest.approx(9.0)
    pd.testing.assert_series_equal(
        shrunk["2627_FP/G"], shrunk["2526_FP/G"], check_names=False
    )


def _forecast_frame():
    """Veterans with real records and a forecast, plus players with neither.

    The no-record players are given forecasts spanning the range, so a test can
    tell "the forecast was used" from "everyone got the same number".
    """
    rows = []
    for i in range(40):
        rate = 8.0 - 6.0 * (i / 40)
        rows.append(
            {
                "ID": f"*v{i}*", "Name": f"Veteran {i}", "Position": ["G", "D", "M", "F"][i % 4],
                "Old Salary": 4000.0,
                "2627_FPts": rate * 2, "2627_FP/G": rate,
                "2526_FPts": rate * 34, "2526_FP/G": rate,
                "2425_FPts": rate * 32, "2425_FP/G": rate,
                "2324_FPts": rate * 30, "2324_FP/G": rate,
                "ADP": float("nan"), "ProjFPts": rate * 30, "ProjFP/G": rate,
                "Rostered": False,
            }
        )
    for index, (name, forecast) in enumerate(
        [("Highly rated", 230.0), ("Middling", 120.0), ("Poorly rated", 20.0), ("Unknown", float("nan"))]
    ):
        rows.append(
            {
                "ID": f"*n{index}*", "Name": name, "Position": "F", "Old Salary": 2000.0,
                "2627_FPts": float("nan"), "2627_FP/G": float("nan"),
                "2526_FPts": float("nan"), "2526_FP/G": float("nan"),
                "2425_FPts": float("nan"), "2425_FP/G": float("nan"),
                "2324_FPts": float("nan"), "2324_FP/G": float("nan"),
                "ADP": float("nan"), "ProjFPts": forecast, "ProjFP/G": float("nan"),
                "Rostered": False,
            }
        )
    return pd.DataFrame(rows)


HIGH, MID, LOW, UNKNOWN = 40, 41, 42, 43


def test_forecast_only_fills_players_with_no_record(current_cfg):
    """A record beats a forecast — anyone with real football never sees it."""
    filled = model.projection_season(_forecast_frame(), current_cfg)
    key = current_cfg.projection_key
    assert filled[f"{key}_FPts"].iloc[:40].isna().all(), "veterans must not be touched"
    assert filled[f"{key}_FPts"].iloc[HIGH] > 0


def test_forecast_ranks_a_better_rated_player_higher(current_cfg):
    filled = model.projection_season(_forecast_frame(), current_cfg)
    key = current_cfg.projection_key
    assert filled[f"{key}_FPts"].iloc[HIGH] > filled[f"{key}_FPts"].iloc[MID]
    assert filled[f"{key}_FPts"].iloc[MID] >= filled[f"{key}_FPts"].iloc[LOW]


def test_forecast_leaves_a_player_it_has_no_opinion_on_alone(current_cfg):
    """No forecast either — nothing can price them, and the floor is honest."""
    filled = model.projection_season(_forecast_frame(), current_cfg)
    assert pd.isna(filled[f"{current_cfg.projection_key}_FPts"].iloc[UNKNOWN])


def test_forecast_gives_a_good_newcomer_a_score_at_all(current_cfg):
    """The whole point: Barcola should be priced on something, not on nothing.

    Asserted on the score rather than the salary. Whether a score clears the
    floor depends on where it sits against the pool mean, which is a property
    of the pool -- in a fixture of forty near-identical veterans it does not,
    and in the real pool it does. What this function is responsible for is that
    a rated newcomer has a score and an unrated one does not.
    """
    result = model.compute(_forecast_frame(), current_cfg)
    score = result.frame["WeightedScore"]
    assert not pd.isna(score.iloc[HIGH])
    assert score.iloc[HIGH] > score.iloc[LOW]
    assert pd.isna(score.iloc[UNKNOWN]), "no forecast means nothing to price on"


def test_forecast_fallback_can_be_switched_off():
    cfg = config_module.load(projection_fallback=False)
    result = model.compute(_forecast_frame(), cfg)
    score = result.frame["WeightedScore"]
    assert pd.isna(score.iloc[HIGH]) and pd.isna(score.iloc[UNKNOWN])
    assert result.frame["Salary"].iloc[HIGH] == result.frame["Salary"].iloc[UNKNOWN]


def _roster_frame():
    """A pool with a clear spread, half of it owned.

    Deliberately built so the owned players are ones the model wants to move a
    long way: freezing something that was not going to move proves nothing.
    """
    rows = []
    for i in range(40):
        rate = 8.0 - 6.0 * (i / 40)
        rows.append(
            {
                "ID": f"*p{i}*", "Name": f"Player {i}", "Position": ["G", "D", "M", "F"][i % 4],
                # Old salaries run opposite to form, so every player has a
                # large gap between current price and earned price.
                "Old Salary": 2500.0 + 300.0 * i,
                "2627_FPts": rate * 20, "2627_FP/G": rate,
                "2526_FPts": rate * 34, "2526_FP/G": rate,
                "2425_FPts": rate * 32, "2425_FP/G": rate,
                "2324_FPts": rate * 30, "2324_FP/G": rate,
                "ADP": float("nan"),
                "Rostered": i % 2 == 0,
            }
        )
    return pd.DataFrame(rows)


def test_rostered_players_keep_their_salary():
    """An existing contract is a price already agreed, not a live valuation."""
    frame = _roster_frame()
    result = model.compute(frame, config_module.load(freeze_rostered=True))
    owned = result.frame["Rostered"]
    pd.testing.assert_series_equal(
        result.frame.loc[owned, "Salary"],
        result.frame.loc[owned, "Old Salary"],
        check_names=False,
    )


def test_free_agents_are_still_repriced_around_them():
    """Freezing contracts must not freeze the market."""
    frame = _roster_frame()
    result = model.compute(frame, config_module.load(freeze_rostered=True))
    free = ~result.frame["Rostered"]
    moved = result.frame.loc[free, "Salary"] != result.frame.loc[free, "Old Salary"]
    assert moved.any(), "no free agent moved — the freeze is too broad"


def test_freezing_does_not_change_anyone_elses_price():
    """Owned players still anchor the scale; only their own salary is held.

    If freezing removed them from the pool the whole league would reprice
    against a smaller, unrepresentative sample, which is a much larger and far
    less obvious change than the one being asked for.
    """
    frame = _roster_frame()
    frozen = model.compute(frame, config_module.load(freeze_rostered=True))
    live = model.compute(frame, config_module.load(freeze_rostered=False))
    assert frozen.max_score == live.max_score
    assert frozen.mean_score == live.mean_score
    free = ~frame["Rostered"]
    pd.testing.assert_series_equal(
        frozen.frame.loc[free, "Salary"], live.frame.loc[free, "Salary"], check_names=False
    )


def test_freeze_can_be_switched_off():
    frame = _roster_frame()
    result = model.compute(frame, config_module.load(freeze_rostered=False))
    owned = result.frame["Rostered"]
    changed = result.frame.loc[owned, "Salary"] != result.frame.loc[owned, "Old Salary"]
    assert changed.any(), "fixture should have owned players the model wants to move"


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
    # The floor binds on everyone the model actually prices. It does not bind
    # on a frozen contract: a player already rostered below the floor (an old
    # league setting left some at 2,000) keeps what they are on, because
    # `freeze_rostered` means their salary is not ours to move -- in either
    # direction. Raising them would quietly cost their manager cap space.
    priced = ~result.frame["Rostered"].fillna(False).astype(bool)
    assert (result.frame.loc[priced, "Salary"] >= current_cfg.salary_floor).all()
    frozen = result.frame.loc[~priced]
    assert (frozen["Salary"] == frozen["Old Salary"]).all()


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
