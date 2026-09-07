"""
Database Seeding Script
=======================
Inserts deterministic initial data into PostgreSQL for development and testing.
Usage:
    python infra/seed.py
"""

import sys
import os

# Add repository root and src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from ayusetu.common.database import SyncSessionLocal, sync_engine, Base
from ayusetu.common.models import Patient, Encounter, Slot, ConsentRecord
from infra.fixtures.seed_data import (
    SEED_PATIENTS,
    SEED_ENCOUNTERS,
    SEED_SLOTS,
    SEED_CONSENTS,
)


def seed_database(session=None) -> None:
    """Populate database with deterministic development fixtures."""
    db_created = False
    if session is None:
        # Ensure tables exist
        Base.metadata.create_all(bind=sync_engine)
        session = SyncSessionLocal()
        db_created = True

    try:
        # Seed Patients
        for p_data in SEED_PATIENTS:
            existing = session.query(Patient).filter(Patient.id == p_data["id"]).first()
            if not existing:
                session.add(Patient(**p_data))

        session.commit()

        # Seed Encounters
        for e_data in SEED_ENCOUNTERS:
            existing = session.query(Encounter).filter(Encounter.id == e_data["id"]).first()
            if not existing:
                session.add(Encounter(**e_data))

        session.commit()

        # Seed Slots
        for s_data in SEED_SLOTS:
            existing = session.query(Slot).filter(Slot.id == s_data["id"]).first()
            if not existing:
                session.add(Slot(**s_data))

        session.commit()

        # Seed Consent Records
        for c_data in SEED_CONSENTS:
            existing = session.query(ConsentRecord).filter(ConsentRecord.id == c_data["id"]).first()
            if not existing:
                session.add(ConsentRecord(**c_data))

        session.commit()
        print(f"Successfully seeded database with {len(SEED_PATIENTS)} patients, {len(SEED_ENCOUNTERS)} encounters.")
    except Exception as e:
        session.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        if db_created:
            session.close()


if __name__ == "__main__":
    seed_database()
