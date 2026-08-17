"""A small Fantrax API client.

Fantrax exposes two very different surfaces, and the difference matters:

`/fxea/general/*`  The documented API (https://www.fantrax.com/developer).
                   Stable, no auth, but it has NO player statistics endpoint —
                   no FPts, no FP/G, no history. It gives league metadata,
                   rosters, player ids and ADP, and that is all.

`/fxpa/req`        The internal RPC the Fantrax web app talks to. Undocumented
                   and unversioned in the public sense: every request carries a
                   client version and the server rejects stale ones outright
                   (`STALE_CLIENT`). This is the only source of the stats the
                   salary model needs, so we use it — carefully, and with a
                   clear error when the version drifts.

Nothing here writes to Fantrax. Salary changes leave via the commissioner CSV
upload; there is no API for them.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from .errors import FantraxError, StaleClientError

ORIGIN = "https://www.fantrax.com"
TIMEOUT = 30


@dataclass(frozen=True)
class Season:
    """One entry from the site's "Season or Projection" dropdown."""

    code: str
    name: str
    timeframe: str

    @property
    def is_projection(self) -> bool:
        """Whether this is Fantrax's forecast rather than results that happened.

        Judged on the code prefix alone. The `timeframeTypeCode` the server
        echoes back cannot be trusted here: while the current season is still
        unplayed, a league reports *every* season — including finished ones
        whose numbers are plainly actuals — as `PROJECTED_SEASON`.
        """
        return self.code.startswith("PROJECTION_")


class FantraxClient:
    def __init__(self, league_id: str, api_version: str, session: Optional[requests.Session] = None):
        if not re.fullmatch(r"[A-Za-z0-9]+", league_id):
            raise ValueError(f"invalid league id: {league_id!r}")
        self.league_id = league_id
        self.api_version = api_version
        self.session = session or requests.Session()

    # -- documented API ----------------------------------------------------

    def league_info(self, exclude_players: bool = True) -> Dict[str, Any]:
        response = self.session.get(
            f"{ORIGIN}/fxea/general/getLeagueInfo",
            params={"leagueId": self.league_id, "excludePlayerInfo": str(exclude_players).lower()},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    # -- internal RPC ------------------------------------------------------

    def _rpc(self, method: str, data: Dict[str, Any]) -> Dict[str, Any]:
        body = {
            "msgs": [{"method": method, "data": data}],
            "uiv": 3,
            "refUrl": f"{ORIGIN}/fantasy/league/{self.league_id}/players",
            "dt": 0,
            "at": 0,
            "av": "0.0",
            "tz": "Atlantic/Reykjavik",
            "v": self.api_version,
        }
        response = self.session.post(
            f"{ORIGIN}/fxpa/req",
            params={"leagueId": self.league_id},
            json=body,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()

        if (payload.get("pageError") or {}).get("code") == "STALE_CLIENT":
            raise StaleClientError(
                f"Fantrax rejected API version {self.api_version!r} as stale.\n"
                "Find the current one with:  python -m fantrax_salary.cli --discover-api-version\n"
                "then pass --api-version, or set it in your config file."
            )

        responses = payload.get("responses") or []
        if not responses:
            raise FantraxError(f"empty response for {method}")
        first = responses[0]
        if first.get("status") == "FAILURE":
            raise FantraxError(first.get("msg") or f"{method} failed")
        return first.get("data") or {}

    def seasons(self) -> List[Season]:
        """Probe which historical seasons this league can serve.

        Fantrax does not return the dropdown contents in the stats payload, so
        we walk backwards from the current season year and keep whatever the
        server actually honours. Season ids run 9NN where NN tracks the year
        (926 = 2026-27), which is stable enough to enumerate but is inferred,
        not documented.
        """
        current_year = int(self.league_info().get("seasonYear", 0))
        if not current_year:
            raise FantraxError("could not determine season year for league")

        base = 926 - (2026 - current_year)
        found: List[Season] = []
        for offset in range(0, 6):
            code = f"SEASON_{base - offset}_YEAR_TO_DATE"
            try:
                data = self._stats_page(season_code=code, page_size=1)
            except FantraxError:
                continue
            displayed = data.get("displayedSeasonOrProjection") or {}
            if displayed.get("code"):
                found.append(
                    Season(
                        code=code,
                        name=str(displayed.get("name", code)).split(" - ")[0],
                        timeframe=str(displayed.get("timeframeTypeCode", "")),
                    )
                )
        return found

    def _stats_page(
        self,
        season_code: Optional[str] = None,
        page_size: int = 5000,
        page: int = 1,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "statusOrTeamFilter": "ALL",
            "maxResultsPerPage": page_size,
            "pageNumber": str(page),
            "miscDisplayType": "1",
        }
        if season_code:
            data["seasonOrProjection"] = season_code
        return self._rpc("getPlayerStats", data)

    def player_stats(self, season_code: Optional[str] = None) -> pd.DataFrame:
        """Fetch one season as a DataFrame of ID / Player / FPts / FP/G / ADP.

        Player ids come back bare from the RPC but are wrapped in asterisks in
        every CSV export (`*03aqp*`), so they are normalised to the CSV form —
        that is what the commissioner template uses as its join key.
        """
        data = self._stats_page(season_code=season_code)
        cells = (data.get("tableHeader") or {}).get("cells", [])
        header = [cell.get("key") for cell in cells]
        try:
            fpts_at, fpg_at = header.index("fpts"), header.index("fptsPerGame")
        except ValueError as exc:
            raise FantraxError(f"unexpected stats columns: {header}") from exc
        # ADP has no `key` in the payload, only a display name, so it has to be
        # found by that. Missing entirely is fine — it is an optional signal.
        adp_at = next(
            (i for i, cell in enumerate(cells) if cell.get("shortName") == "ADP"), None
        )

        def number(cell: Any) -> Optional[float]:
            text = (cell or {}).get("content")
            if not isinstance(text, str):
                return None
            try:
                return float(text.replace(",", ""))
            except ValueError:
                return None

        rows = []
        for row in data.get("statsTable") or []:
            scorer = row.get("scorer") or {}
            scorer_id = scorer.get("scorerId")
            if not scorer_id:
                continue
            cells = row.get("cells") or []

            def at(index):
                return number(cells[index]) if index is not None and index < len(cells) else None

            rows.append(
                {
                    "ID": f"*{str(scorer_id).strip('*')}*",
                    "Player": scorer.get("name"),
                    "FPts": at(fpts_at),
                    "FP/G": at(fpg_at),
                    "ADP": at(adp_at),
                }
            )
        if not rows:
            raise FantraxError(f"no rows returned for season {season_code!r}")
        return pd.DataFrame(rows)


def discover_api_version(session: Optional[requests.Session] = None) -> str:
    """Scrape the live site for a working `/fxpa/req` client version.

    The version lives in one of the app's hashed JS chunks, and both the chunk
    names and the version change on every Fantrax deploy — so this reads the
    bundle rather than guessing, then validates each candidate against the real
    endpoint and returns the first the server accepts.
    """
    session = session or requests.Session()
    home = session.get(f"{ORIGIN}/", timeout=TIMEOUT).text
    entry = re.search(r'src="(main-[A-Z0-9]+\.js)"', home)
    if not entry:
        raise FantraxError("could not locate the Fantrax entrypoint bundle")

    bundle = session.get(f"{ORIGIN}/{entry.group(1)}", timeout=TIMEOUT).text
    chunks = sorted(set(re.findall(r"[a-zA-Z0-9_-]{4,}-[A-Z0-9]{8}\.js", bundle)))

    def candidates_in(chunk: str) -> List[str]:
        try:
            text = session.get(f"{ORIGIN}/{chunk}", timeout=TIMEOUT).text
        except requests.RequestException:
            return []
        # Only three-part versions with a three-digit major are plausible; the
        # bundles are full of unrelated library versions like "4.17.12".
        return re.findall(r'"(\d{3}\.\d{1,3}\.\d{1,3})"', text)

    seen: List[str] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for found in pool.map(candidates_in, chunks):
            for version in found:
                if version not in seen:
                    seen.append(version)

    probe_league = "0pit050kmss1l8bh"
    for version in seen:
        try:
            FantraxClient(probe_league, version, session)._stats_page(page_size=1)
            return version
        except StaleClientError:
            continue
        except FantraxError:
            continue
    raise FantraxError(f"no working version found (tried {seen or 'nothing'})")
