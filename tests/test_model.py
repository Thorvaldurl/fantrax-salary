"""The refactor must not move a single salary.

`reference_implementation.run` is the original script's arithmetic. If these
tests pass, the restructured pipeline is a pure refactor.
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
