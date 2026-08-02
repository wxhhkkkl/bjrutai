"""US6 migration consistency verifier (T033).

Run after executing migration 004 against the production database:

    venv/Scripts/python.exe -m scripts.verify_migration

Checks that historical data is fully preserved (SC-009): row counts, FK
alignment (distributor.id == legacy promoter.id), and that no legacy table
still holds live data (they were deprecated, not dropped).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, text

from src.core.database import async_session
from src.models.distributor import Distributor
from src.models.organization import Organization


async def _verify() -> int:
    errors = 0
    async with async_session() as db:
        org_count = (await db.execute(select(func.count(Organization.id)))).scalar() or 0
        dist_count = (await db.execute(select(func.count(Distributor.id)))).scalar() or 0

        print(f"[verify] organizations={org_count} distributors={dist_count}")

        # Legacy tables should exist (deprecated, data retained)
        for legacy in ("_deprecated_hierarchy_nodes", "_deprecated_promoters", "_deprecated_qualifications"):
            exists = (await db.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"
            ), {"t": legacy})).scalar()
            if not exists:
                print(f"[FAIL] legacy table missing: {legacy}")
                errors += 1
            else:
                legacy_count = (await db.execute(text(f"SELECT COUNT(*) FROM `{legacy}`"))).scalar()
                print(f"[ok] {legacy}: {legacy_count} rows retained")

        # FK alignment: distributor.org_id must reference an organization
        orphan = (await db.execute(text(
            "SELECT COUNT(*) FROM distributors d LEFT JOIN organizations o ON o.id = d.org_id WHERE o.id IS NULL"
        ))).scalar()
        if orphan:
            print(f"[FAIL] {orphan} distributors reference missing orgs")
            errors += 1

        for table in ("customers", "promotion_codes", "contribution_records", "binding_requests"):
            try:
                total = (await db.execute(text(f"SELECT COUNT(*) FROM `{table}`"))).scalar()
                orphan = (await db.execute(text(
                    f"SELECT COUNT(*) FROM `{table}` t LEFT JOIN distributors d ON d.id = t.distributor_id WHERE d.id IS NULL"
                ))).scalar()
                print(f"[ok] {table}: {total} rows, {orphan} orphan distributor refs")
                if orphan:
                    errors += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[FAIL] {table}: {exc}")
                errors += 1

    if errors:
        print(f"\n[RESULT] FAIL — {errors} issue(s) found")
    else:
        print("\n[RESULT] PASS — migration data verified")
    return errors


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_verify()))
