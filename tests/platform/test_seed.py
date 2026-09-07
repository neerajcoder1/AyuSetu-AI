"""
Test Suite: Database Seed Fixtures
===================================
Validates deterministic seed execution and queryability of seeded fixtures.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ayusetu.common.database import Base
from ayusetu.common.models import Patient, Encounter, Slot, ConsentRecord
from infra.seed import seed_database
from infra.fixtures.seed_data import PATIENT_1_ID, PATIENT_2_ID, PATIENT_3_ID


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_seed_database_execution(memory_db):
    seed_database(session=memory_db)

    # Verify Patients
    patients = memory_db.query(Patient).all()
    assert len(patients) == 3
    p1 = memory_db.query(Patient).filter(Patient.id == PATIENT_1_ID).first()
    assert p1 is not None
    assert p1.is_provisional is True
    assert p1.district == "Patna"

    p2 = memory_db.query(Patient).filter(Patient.id == PATIENT_2_ID).first()
    assert p2 is not None
    assert p2.abha_id == "91-1234-5678-9012"
    assert p2.is_provisional is False

    # Verify Encounters
    encounters = memory_db.query(Encounter).all()
    assert len(encounters) == 3

    # Verify Slots
    slots = memory_db.query(Slot).all()
    assert len(slots) >= 3

    # Verify Consent Records
    consents = memory_db.query(ConsentRecord).all()
    assert len(consents) >= 2
