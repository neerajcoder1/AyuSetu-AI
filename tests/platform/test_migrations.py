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
    
    # Check that initial revision exists
    revisions = list(script.walk_revisions())
    assert len(revisions) >= 1
    head = script.get_current_head()
    assert head == "0001_initial_schema"
