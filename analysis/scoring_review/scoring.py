"""A working implementation of the league's Fantrax scoring system.

Rules come straight from getLeagueInfo's `scoringSystem`. Two spec forms:

    "points0.15"                     flat points per unit
    "range0|1|4|1.0$2|2|5|1.0$..."   start|end|pointsPerUnit|interval, banded

Range categories are cumulative per unit: with the default goal bands, a brace
is 4 + 5 = 9, not 2 x 5. Ranges are evaluated per match (the game log is one
row per match), which is what the PER_GAME / PER_SCORING_PERIOD flags mean for
a league whose scoring period is a matchweek.
"""
from __future__ import annotations

import json
from typing import Dict, List, Tuple

Bands = List[Tuple[float, float, float, float]]


def parse_spec(spec: str):
    """Return ('flat', points) or ('range', bands)."""
    if spec.startswith('points'):
        return ('flat', float(spec[len('points'):]))
    if spec.startswith('range'):
        bands: Bands = []
        for chunk in spec[len('range'):].split('$'):
            start, end, points, interval = chunk.split('|')
            bands.append((float(start), float(end), float(points), float(interval)))
        return ('range', bands)
    raise ValueError(f'unknown scoring spec: {spec!r}')


def score_range(count: float, bands: Bands) -> float:
    """Cumulative per-unit scoring across bands."""
    total = 0.0
    for unit in range(1, int(count) + 1):
        for start, end, points, interval in bands:
            if start <= unit <= end:
                total += points
                break
        else:
            # Above every band: the last band's rate carries on.
            total += bands[-1][2]
    return total


class ScoringSystem:
    """Category -> position -> spec, with position fallback to Default."""

    def __init__(self, scoring_categories: Dict[str, Dict[str, Dict[str, str]]]):
        self.raw = scoring_categories
        self.parsed = {
            group: {cat: {pos: parse_spec(spec) for pos, spec in by_pos.items()}
                    for cat, by_pos in cats.items()}
            for group, cats in scoring_categories.items()
        }

    @classmethod
    def from_league_info(cls, path: str) -> 'ScoringSystem':
        with open(path) as fh:
            info = json.load(fh)
        return cls(info['scoringSystem']['scoringCategories'])

    def group_for(self, position: str) -> str:
        return 'GOALIE' if position.strip().upper().startswith('G') else 'NON_GOALIE'

    def _spec(self, group: str, category: str, position: str):
        by_pos = self.parsed[group].get(category)
        if by_pos is None:
            return None
        return by_pos.get(position) or by_pos.get('Default')

    def score_game(self, position: str, stats: Dict[str, float]) -> float:
        """Points for one match, given that match's category counts."""
        group = self.group_for(position)
        # A dual-eligible player (e.g. "M,F") is scored on their first listed
        # position, which is how Fantrax treats the default lineup slot.
        pos = position.split(',')[0].strip().upper()
        total = 0.0
        for category, count in stats.items():
            if not count:
                continue
            spec = self._spec(group, category, pos)
            if spec is None:
                continue
            kind, value = spec
            total += count * value if kind == 'flat' else score_range(count, value)
        return total

    def category_contributions(self, position: str, stats: Dict[str, float]) -> Dict[str, float]:
        """Same as score_game but broken out per category."""
        group = self.group_for(position)
        pos = position.split(',')[0].strip().upper()
        out: Dict[str, float] = {}
        for category, count in stats.items():
            if not count:
                continue
            spec = self._spec(group, category, pos)
            if spec is None:
                continue
            kind, value = spec
            out[category] = count * value if kind == 'flat' else score_range(count, value)
        return out

    def replace(self, changes: Dict[str, Dict[str, str]]) -> 'ScoringSystem':
        """Return a copy with some category specs overridden.

        `changes` is {group: {category: spec}} or {group: {"category@POS": spec}}.
        """
        raw = {g: {c: dict(p) for c, p in cats.items()} for g, cats in self.raw.items()}
        for group, cats in changes.items():
            for key, spec in cats.items():
                category, _, position = key.partition('@')
                raw.setdefault(group, {}).setdefault(category, {})[position or 'Default'] = spec
        return ScoringSystem(raw)
