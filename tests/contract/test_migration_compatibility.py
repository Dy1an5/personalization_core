from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from personalization_core.infrastructure.persistence.sqlalchemy_models import Base


ROOT = Path(__file__).parents[2]


def test_release_migration_chain_and_head_are_compatible() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    revisions = list(scripts.walk_revisions("base", "0002_privacy_audit"))
    assert [revision.revision for revision in revisions] == [
        "0002_privacy_audit",
        "0001_initial",
    ]
    assert scripts.get_current_head() == "0002_privacy_audit"
    assert scripts.get_revision("0002_privacy_audit").down_revision == "0001_initial"


def test_release_schema_matches_the_two_migration_tables() -> None:
    expected_tables = {
        "subjects",
        "entities",
        "events",
        "evidence",
        "memories",
        "memory_evidence",
        "memory_revisions",
        "feature_observations",
        "feature_states",
        "feature_state_evidence",
        "profile_snapshots",
        "processing_runs",
        "audit_log",
        "purge_audit_log",
    }
    assert set(Base.metadata.tables) == expected_tables
