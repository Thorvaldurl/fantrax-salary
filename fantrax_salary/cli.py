"""Command line entry point.

    python -m fantrax_salary.cli --gameweek 3
    python -m fantrax_salary.cli --gameweek 3 --source api
    python -m fantrax_salary.cli --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config as config_module
from . import model, report, sources, validate
from .errors import FantraxError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fantrax-salary",
        description="Recalculate Fantrax player salaries and write the commissioner upload CSV.",
    )
    parser.add_argument("--gameweek", type=int, help="gameweek number, used to name the output files")
    parser.add_argument("--source", choices=("csv", "api"), help="where to read player statistics from")
    parser.add_argument("--config", type=Path, help="JSON config file overriding the defaults")
    parser.add_argument("--template", type=Path, help="commissioner spreadsheet to price against")
    parser.add_argument("--output-dir", type=Path, dest="output_dir", help="where to write results")
    parser.add_argument("--league-id", dest="league_id", help="Fantrax league id (api source)")
    parser.add_argument("--api-version", dest="api_version", help="client version sent to the Fantrax RPC")
    parser.add_argument("--dry-run", action="store_true", help="compute and report, but write nothing")
    parser.add_argument("--force", action="store_true", help="run even if validation finds problems")
    parser.add_argument(
        "--discover-api-version",
        action="store_true",
        help="scrape the live site for a working API version, print it, and exit",
    )
    parser.add_argument(
        "--list-seasons",
        action="store_true",
        help="list the seasons the configured league can serve, and exit",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.discover_api_version:
        from .api import discover_api_version

        try:
            print(discover_api_version())
        except FantraxError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0

    cfg = config_module.load(
        config_file=args.config,
        gameweek=args.gameweek,
        source=args.source,
        template=args.template,
        output_dir=args.output_dir,
        league_id=args.league_id,
        api_version=args.api_version,
        dry_run=args.dry_run or None,
    )

    if args.list_seasons:
        from .api import FantraxClient

        client = FantraxClient(cfg.league_id, cfg.api_version)
        try:
            for season in client.seasons():
                kind = "projection" if season.is_projection else "actual"
                print(f"{season.code:<32} {season.name:<12} {kind}")
        except FantraxError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0

    print(f"Source: {cfg.source}   gameweek: {cfg.gameweek}")
    for season in cfg.seasons:
        origin = season.api_code if cfg.source == "api" else season.csv
        print(f"  {season.weight:>5.0%}  {season.label:<22} {origin}")

    try:
        template = sources.load_template(cfg)
        frame = sources.load(cfg)
    except (FileNotFoundError, ValueError, FantraxError) as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1

    findings = validate.run_all(template, frame, cfg)
    if findings.problems or findings.warnings:
        print("\nValidation")
        print(findings.report())
    if not findings.ok and not args.force:
        print("\nRefusing to continue. Re-run with --force to override.", file=sys.stderr)
        return 1

    result = model.compute(frame, cfg)
    summary = report.build(result, cfg)
    print(summary)

    if cfg.dry_run:
        print("\nDry run — nothing written.")
        return 0

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    upload_csv = cfg.output_path(".csv")
    model.write_upload_csv(template, result, upload_csv)
    model.write_workbook(result, cfg.output_path(".xlsx"))
    cfg.output_path(".report.txt").write_text(summary, encoding="utf-8")

    print(f"\nWrote {upload_csv}")
    print(f"      {cfg.output_path('.xlsx')}")
    print(f"      {cfg.output_path('.report.txt')}")
    print("\nUpload the .csv via Fantrax: League -> Commissioner -> Player Salaries -> Import.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
