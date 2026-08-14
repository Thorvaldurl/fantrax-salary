"""The original `Sal Updates 1.py`, preserved as a test oracle.

The arithmetic below is byte-for-byte the logic that shipped, including its use
of scikit-learn's MinMaxScaler and its row-wise `apply`. The only changes are
that the hardcoded Windows paths became arguments and the printing and file
writing were removed.

Do not "improve" this file. Its entire value is being the thing the refactored
model is checked against — `test_model.py` asserts the two agree on every row.
Scoring changes belong in `fantrax_salary/model.py`, and when one lands, this
file is what proves the change was deliberate rather than accidental.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler


def run(template_path: Path, gw_path: Path, seasons_dir: Path) -> pd.DataFrame:
    blank = pd.read_csv(template_path, header=None)
    data = pd.DataFrame()
    data["ID"] = blank.iloc[:, 0]
    data["Name"] = blank.iloc[:, 2]
    data["Team"] = blank.iloc[:, 3]
    data["Position"] = blank.iloc[:, 4]
    data["Old Salary"] = blank.iloc[:, 5]

    df2627 = pd.read_csv(gw_path)
    df2526 = pd.read_csv(seasons_dir / "2526.csv")
    df2425 = pd.read_csv(seasons_dir / "2425.csv")
    df2324 = pd.read_csv(seasons_dir / "2324.csv")

    data = data.merge(df2627[["ID", "FPts"]], on="ID", how="left").rename(columns={"FPts": "2627_FPts"})
    data = data.merge(df2526[["ID", "FPts"]], on="ID", how="left").rename(columns={"FPts": "2526_FPts"})
    data = data.merge(df2425[["ID", "FPts"]], on="ID", how="left").rename(columns={"FPts": "2425_FPts"})
    data = data.merge(df2324[["ID", "FPts"]], on="ID", how="left").rename(columns={"FPts": "2324_FPts"})

    data = data.merge(df2627[["ID", "FP/G"]], on="ID", how="left").rename(columns={"FP/G": "2627_FP/G"})
    data = data.merge(df2526[["ID", "FP/G"]], on="ID", how="left").rename(columns={"FP/G": "2526_FP/G"})
    data = data.merge(df2425[["ID", "FP/G"]], on="ID", how="left").rename(columns={"FP/G": "2425_FP/G"})
    data = data.merge(df2324[["ID", "FP/G"]], on="ID", how="left").rename(columns={"FP/G": "2324_FP/G"})

    cols_to_normalize = [
        "2627_FPts", "2627_FP/G",
        "2526_FPts", "2526_FP/G",
        "2425_FPts", "2425_FP/G",
        "2324_FPts", "2324_FP/G",
    ]

    scaler = MinMaxScaler()
    data[cols_to_normalize] = scaler.fit_transform(data[cols_to_normalize])

    def weighted_score(row):
        score = 0
        weight_sum = 0
        if not np.isnan(row["2627_FPts"]) and not np.isnan(row["2627_FP/G"]):
            score += 0.70 * (row["2627_FPts"] + row["2627_FP/G"])
            weight_sum += 0.70
        if not np.isnan(row["2526_FPts"]) and not np.isnan(row["2526_FP/G"]):
            score += 0.25 * (row["2526_FPts"] + row["2526_FP/G"])
            weight_sum += 0.25
        if not np.isnan(row["2425_FPts"]) and not np.isnan(row["2425_FP/G"]):
            score += 0.04 * (row["2425_FPts"] + row["2425_FP/G"])
            weight_sum += 0.04
        if not np.isnan(row["2324_FPts"]) and not np.isnan(row["2324_FP/G"]):
            score += 0.01 * (row["2324_FPts"] + row["2324_FP/G"])
            weight_sum += 0.01
        return score / weight_sum if weight_sum > 0 else np.nan

    data["WeightedScore"] = data.apply(weighted_score, axis=1)

    max_value = data["WeightedScore"].max()
    mean_value = data.loc[data["WeightedScore"] > 0, "WeightedScore"].mean()

    salarymult = (15000 - 4000) / ((max_value / mean_value) - 1)
    data["TargetSalary"] = 4000 + (data["WeightedScore"] / mean_value - 1) * salarymult

    data.loc[data["TargetSalary"] < 2500, "TargetSalary"] = 2500

    data["Salary"] = data["Old Salary"] + (data["TargetSalary"] - data["Old Salary"]) / 2
    data["Salary"] = data["Salary"].round(-2)

    data.loc[data["Salary"] < 2500, "Salary"] = 2500

    return data
