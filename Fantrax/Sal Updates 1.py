import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler

# --- Load base data ---
blank = pd.read_csv(
    r"C:\Users\Notandi\Desktop\Python\Fantrax - SalUpdate\FantraxPlayers_0pit050kmss1l8bh.csv",
    header=None
) #dl blank spreadsheet úr commish settings
data = pd.DataFrame()
data['ID'] = blank.iloc[:, 0]
data['Name'] = blank.iloc[:, 2]
data['Team'] = blank.iloc[:, 3]
data['Position'] = blank.iloc[:, 4]
data['Old Salary'] = blank.iloc[:, 5]



# Read CSVs - Downloada alltaf nyjustu gögnum - breyta file nafni i 2526

df2627 = pd.read_csv(r"C:\Users\Notandi\Desktop\Python\Fantrax\Vikur\gw1.csv")  #hér downloadar þú nýjasta players csv með að velja "all players" (ekki bara available)
df2526 = pd.read_csv(r"C:\Users\Notandi\Desktop\Python\Fantrax\2526.csv") #Hér downloadar þú all players fyrir tímabilið 2024-25
df2425 = pd.read_csv(r"C:\Users\Notandi\Desktop\Python\Fantrax\2425.csv") #Hér downloadar þú all players fyrir tímabilið 2023-24
df2324 = pd.read_csv(r"C:\Users\Notandi\Desktop\Python\Fantrax\2324.csv") #Hér downloadar þú all players fyrir tímabilið 2022-23


# --- Merge FPts and FP/G correctly ---
data = data.merge(df2627[['ID', 'FPts']], on='ID', how='left').rename(columns={'FPts': '2627_FPts'})
data = data.merge(df2526[['ID', 'FPts']], on='ID', how='left').rename(columns={'FPts': '2526_FPts'})
data = data.merge(df2425[['ID', 'FPts']], on='ID', how='left').rename(columns={'FPts': '2425_FPts'})
data = data.merge(df2324[['ID', 'FPts']], on='ID', how='left').rename(columns={'FPts': '2324_FPts'})

data = data.merge(df2627[['ID', 'FP/G']], on='ID', how='left').rename(columns={'FP/G': '2627_FP/G'})
data = data.merge(df2526[['ID', 'FP/G']], on='ID', how='left').rename(columns={'FP/G': '2526_FP/G'})
data = data.merge(df2425[['ID', 'FP/G']], on='ID', how='left').rename(columns={'FP/G': '2425_FP/G'})
data = data.merge(df2324[['ID', 'FP/G']], on='ID', how='left').rename(columns={'FP/G': '2324_FP/G'})

# Normalize FPts and FP/G to [0,1]
cols_to_normalize = [
    '2627_FPts', '2627_FP/G',
    '2526_FPts', '2526_FP/G',
    '2425_FPts', '2425_FP/G',
    '2324_FPts', '2324_FP/G'
]

scaler = MinMaxScaler()
data[cols_to_normalize] = scaler.fit_transform(data[cols_to_normalize])

# Weighted score calculation
def weighted_score(row):
    score = 0
    weight_sum = 0
    if not np.isnan(row['2627_FPts']) and not np.isnan(row['2627_FP/G']):
        score += 0.70 * (row['2627_FPts'] + row['2627_FP/G'])
        weight_sum += 0.70
    if not np.isnan(row['2526_FPts']) and not np.isnan(row['2526_FP/G']):
        score += 0.25 * (row['2526_FPts'] + row['2526_FP/G'])
        weight_sum += 0.25
    if not np.isnan(row['2425_FPts']) and not np.isnan(row['2425_FP/G']):
        score += 0.04 * (row['2425_FPts'] + row['2425_FP/G'])
        weight_sum += 0.04
    if not np.isnan(row['2324_FPts']) and not np.isnan(row['2324_FP/G']):
        score += 0.01 * (row['2324_FPts'] + row['2324_FP/G'])
        weight_sum += 0.01
    return score / weight_sum if weight_sum > 0 else np.nan

data['WeightedScore'] = data.apply(weighted_score, axis=1)


# Salary calculation
max_value = data['WeightedScore'].max()
mean_value = data.loc[data['WeightedScore'] > 0, 'WeightedScore'].mean()

salarymult = (15000 - 4000) / ((max_value / mean_value) - 1)
data['TargetSalary'] = 4000 + (data['WeightedScore'] / mean_value - 1) * salarymult

# Floor to 2500
data.loc[data['TargetSalary'] < 2500, 'TargetSalary'] = 2500

# Damp salary change
data['Salary'] = data['Old Salary'] + (data['TargetSalary'] - data['Old Salary']) / 2
data['Salary'] = data['Salary'].round(-2)

# Floor to 2500
data.loc[data['Salary'] < 2500, 'Salary'] = 2500


print("Salary Multiplier:", salarymult)

# Save result
data.to_excel(r"C:\Users\Notandi\Desktop\Python\Fantrax - SalUpdate\SalGW1.xlsx", index=False)

# Print top 20 by salary
print(
    data[['ID', 'Name', 'WeightedScore', 'Old Salary', 'TargetSalary', 'Salary']]
    .sort_values('Salary', ascending=False)
    .head(20)
)

print(f"Highest WeightedScore: {max_value:.4f}")
print(f"Average of non-zero WeightedScore: {mean_value:.4f}")

# Update blank.csv
salary_dict = data.set_index('ID')['Salary'].to_dict()
blank[5] = blank[0].map(salary_dict)
blank.to_csv(
    r"C:\Users\Notandi\Desktop\Python\Fantrax - SalUpdate\SalGW1.csv",
    index=False,
    header=False
)
print("Updated blank.csv with new salary values.")

