"""Positional balance and scoring tweaks, done honestly from season totals.

Season-total category counts (from getPlayerStats, scoringCategoryType=5 per
position group) are exact for FLAT-rate categories -- points-per-unit, order
doesn't matter. They are WRONG for banded categories (Goals, Assists Total,
goalkeeper Goals Against), which reset their tier every match; summing a whole
season into one "game" and running it through the band table over- or
under-counts depending on how the player's output was distributed across
games. Validated: reconstructing full FPts this way has 14% median error,
up to +225 pts for a single goalkeeper. That is a real bug in the previous
attempt, not a rounding nuance -- it is not used here.

So the split:
  - "Current" balance uses Fantrax's OWN reported FPts/FP/G. No reconstruction,
    no risk from the banding issue.
  - A scoring TWEAK's effect is computed as a delta: this engine scores only
    the tweak's flat-rate categories, under current rules and under the
    proposed rules, and the difference is added to the reported FPts. That
    delta is exact regardless of the banding issue, because the banded
    categories are identical on both sides and cancel out.
  - Tweaks that touch a banded category (forward goal/assist rates) are
    reported qualitatively only -- simulating them accurately needs per-game
    logs, which is a separate, throttled data source. Not guessed at here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from scoring import ScoringSystem, parse_spec  # noqa: E402

SEASON_FILE = HERE / 'data' / 'season_2526_categories.json'
LEAGUE_INFO = HERE / 'data' / 'leagueinfo.json'
TEMPLATE = REPO_ROOT / 'data' / 'template' / 'blank_2026-27.csv'

MAX_ACTIVE = {'G': 1, 'D': 5, 'M': 5, 'F': 3}
TYPICAL = {'G': 1, 'D': 4, 'M': 4, 'F': 2}
TEAMS = 10
ACTIVE = 11
MIN_GAMES = 10

NON_STAT = {'Rk', 'Sta', 'Opp', 'Sal', 'FPts', 'FP/G', '%D', 'ADP', 'Ros', '+/-'}

# Categories whose spec is a band table anywhere -- these cannot be
# reconstructed from a season total. Established from the live scoring config,
# not assumed.
def banded_categories(system):
    out = set()
    for group, cats in system.parsed.items():
        for category, by_pos in cats.items():
            if any(kind == 'range' for kind, _ in by_pos.values()):
                out.add(category)
    return out


def load_players():
    """One row per player, at their PRIMARY position.

    A dual-eligible player (e.g. Matheus Nunes, listed "D,M") is returned by
    BOTH the D and the M queries -- Fantrax scores them under each position's
    own rules for that query, so the two copies do not even agree on FPts
    (Matheus Nunes: 247.47 as a D, 222.47 as a M, because defender clean
    sheets pay 4 and midfielder ones pay 1). Counting both would double the
    player and blur the position comparison. The template's Position column
    lists eligible positions with the primary one first, which is the same
    convention `sources.py` and `scoring.py` already use, so it is used here
    too: whichever query matches that primary position wins; the other copy
    is discarded.
    """
    template = pd.read_csv(TEMPLATE, header=None)
    primary = {
        row[0].strip('*'): row[4].split(',')[0].strip().upper()
        for row in template.itertuples(index=False)
    }

    with open(SEASON_FILE) as fh:
        raw = json.load(fh)

    by_id = {}
    for position, payload in raw.items():
        headers = payload['headers']
        for row in payload['rows']:
            if row['id'] not in primary:
                continue  # not in the current 709-player pool (e.g. left the league)
            if primary[row['id']] != position:
                continue  # a copy of this player scored under a non-primary position
            cells = dict(zip(headers, row['cells']))

            def num(key):
                value = cells.get(key)
                try:
                    return float(str(value).replace(',', ''))
                except (TypeError, ValueError):
                    return 0.0

            gp = num('GP')
            if gp < MIN_GAMES:
                continue
            stats = {k: num(k) for k in headers if k not in NON_STAT and k != 'GP'}
            by_id[row['id']] = {
                'ID': row['id'], 'Name': row['name'], 'Pos': position, 'GP': gp,
                'reported_FPts': num('FPts'), 'reported_FPG': num('FP/G'),
                'stats': stats,
            }
    return list(by_id.values())


def flat_only_score(position, stats, system, exclude):
    """Sum only the categories that are safe to compute from a season total."""
    total = 0.0
    for category, count in stats.items():
        if not count or category in exclude:
            continue
        group = system.group_for(position)
        pos = position.split(',')[0].strip().upper()
        by_pos = system.parsed[group].get(category)
        if by_pos is None:
            continue
        kind, value = by_pos.get(pos) or by_pos.get('Default')
        if kind == 'flat':
            total += count * value
    return total


def current_frame(players):
    """Positional balance under the scoring as it stands, straight from Fantrax."""
    rows = [{'ID': p['ID'], 'Name': p['Name'], 'Pos': p['Pos'], 'GP': p['GP'],
             'FPts': p['reported_FPts'], 'FPG': p['reported_FPG']} for p in players]
    return pd.DataFrame(rows)


def tweaked_frame(players, base_system, tweaked_system, banned):
    """Reported FPts plus the exact delta from a flat-category-only tweak."""
    rows = []
    for p in players:
        before = flat_only_score(p['Pos'], p['stats'], base_system, banned)
        after = flat_only_score(p['Pos'], p['stats'], tweaked_system, banned)
        fpts = p['reported_FPts'] + (after - before)
        rows.append({'ID': p['ID'], 'Name': p['Name'], 'Pos': p['Pos'], 'GP': p['GP'],
                     'FPts': fpts, 'FPG': fpts / p['GP'], 'Delta/G': (after - before) / p['GP']})
    return pd.DataFrame(rows)


def best_eleven(frame):
    pool = frame.sort_values('FPG', ascending=False)
    picked, counts = [], defaultdict(int)
    for _, row in pool.iterrows():
        position = row.Pos
        if position not in MAX_ACTIVE or counts[position] >= MAX_ACTIVE[position]:
            continue
        picked.append(row)
        counts[position] += 1
        if len(picked) == ACTIVE:
            break
    return pd.DataFrame(picked), dict(counts)


def evaluate(frame):
    out = {}
    for position in ['G', 'D', 'M', 'F']:
        ranked = frame[frame.Pos == position].sort_values('FPG', ascending=False)
        if ranked.empty:
            continue
        index = min(TEAMS * TYPICAL[position], len(ranked)) - 1
        out[position] = {
            'n': len(ranked), 'mean': ranked.FPG.mean(),
            'starter': ranked.FPG.head(TEAMS * TYPICAL[position]).mean(),
            'marginal': ranked.FPG.iloc[index],
        }
    table = pd.DataFrame(out).T
    _, shape = best_eleven(frame)
    return table, shape


def line(label, table, shape):
    means = '  '.join(f'{p} {table.loc[p, "starter"]:5.2f}' for p in ['G', 'D', 'M', 'F'] if p in table.index)
    spread = table['marginal'].max() - table['marginal'].min()
    shape_s = '/'.join(f'{shape.get(p, 0)}{p}' for p in ['G', 'D', 'M', 'F'])
    return f'{label:<30} starters[{means}]  marginal spread {spread:5.2f}   best XI {shape_s}'


def scaled(system, categories, factor, group='NON_GOALIE'):
    changes = {}
    for category in categories:
        by_pos = system.raw[group].get(category, {})
        for position, spec in by_pos.items():
            if spec.startswith('points'):
                value = float(spec[len('points'):])
                key = category if position == 'Default' else f'{category}@{position}'
                changes[key] = f'points{round(value * factor, 4)}'
    return system.replace({group: changes})


VOLUME_DEFENSIVE = ['CLR', 'BR', 'DW', 'AER', 'Int', 'BS', 'TkW+BS', 'BC', 'CoSF', 'AC', 'SFTP']


if __name__ == '__main__':
    system = ScoringSystem.from_league_info(LEAGUE_INFO)
    banned = banded_categories(system)
    print(f'categories excluded as banded (need per-game data): {sorted(banned)}\n')

    players = load_players()
    print(f'{len(players)} players with {MIN_GAMES}+ games in 2025-26\n')

    base = current_frame(players)
    table, shape = evaluate(base)
    print('--- CURRENT SCORING (Fantrax reported FPts, ground truth) ---')
    print(table.round(2).to_string())
    print(line('  current', table, shape))

    print('\n--- where the points come from (mean/game, biggest drivers of the D/F gap) ---')
    totals = defaultdict(lambda: defaultdict(float))
    games = defaultdict(float)
    for p in players:
        games[p['Pos']] += p['GP']
        group = system.group_for(p['Pos'])
        pos = p['Pos'].split(',')[0].strip().upper()
        for category, count in p['stats'].items():
            if not count:
                continue
            by_pos = system.parsed[group].get(category)
            if by_pos is None:
                continue
            kind, value = by_pos.get(pos) or by_pos.get('Default')
            pts = count * value if kind == 'flat' else None  # banded omitted from this table
            if pts is not None:
                totals[p['Pos']][category] += pts
    split = pd.DataFrame(totals).fillna(0.0)
    for position in split.columns:
        split[position] /= games[position]
    split = split.reindex(columns=[c for c in ['G', 'D', 'M', 'F'] if c in split.columns])
    split['spread'] = split.max(axis=1) - split.min(axis=1)
    print(split.sort_values('spread', ascending=False).head(12).round(2).to_string())

    print('\n\n--- FLAT-CATEGORY TWEAKS (exact deltas, banded categories untouched) ---')
    print(line('  baseline', table, shape))

    variants = {
        'A: defensive volume x0.85': lambda s: scaled(s, VOLUME_DEFENSIVE, 0.85),
        'B: defensive volume x0.70': lambda s: scaled(s, VOLUME_DEFENSIVE, 0.70),
        'C: defender CS 4 -> 2': lambda s: s.replace({'NON_GOALIE': {'CS@D': 'points2'}}),
        'D: defender CS 4 -> 3': lambda s: s.replace({'NON_GOALIE': {'CS@D': 'points3'}}),
        'E: A + C': lambda s: scaled(s, VOLUME_DEFENSIVE, 0.85).replace({'NON_GOALIE': {'CS@D': 'points2'}}),
        'F: B + C': lambda s: scaled(s, VOLUME_DEFENSIVE, 0.70).replace({'NON_GOALIE': {'CS@D': 'points2'}}),
        'G: B + D': lambda s: scaled(s, VOLUME_DEFENSIVE, 0.70).replace({'NON_GOALIE': {'CS@D': 'points3'}}),
    }
    for name, build in variants.items():
        tweaked_system = build(system)
        frame = tweaked_frame(players, system, tweaked_system, banned)
        t, s = evaluate(frame)
        print(line('  ' + name, t, s))

    print('\n(rows below are all players with 10+ games; Delta/G shows the per-game swing '
          'for the largest tweak, B+C, sorted worst for defenders)')
    tweaked_system = variants['F: B + C'](system)
    frame = tweaked_frame(players, system, tweaked_system, banned)
    d = frame[frame.Pos == 'D'].nsmallest(8, 'Delta/G')[['Name', 'GP', 'FPG', 'Delta/G']]
    print(d.to_string(index=False))
