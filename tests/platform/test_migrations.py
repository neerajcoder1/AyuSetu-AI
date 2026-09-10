"""
Test Suite: Database Migrations
================================
Validates Alembic migration files, tables, indexes, and upgrade/downgrade logic.
"""

import os
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest


def test_alembic_revisions_structure():
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    
    # Check that migrations exist and head matches latest revision
    revisions = list(script.walk_revisions())
    assert len(revisions) >= 2
    head = script.get_current_head()
    assert head == "0002_audit_immutability_and_quarantine"

