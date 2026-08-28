from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.services.maintenance import run_retention_cleanup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Purge expired sessions/cache entries and old terminal job data."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be deleted without committing changes.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    with SessionLocal() as db:
        summary = run_retention_cleanup(db, dry_run=args.dry_run)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
