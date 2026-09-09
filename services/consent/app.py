"""
services/consent Entry Point
============================
Microservice root for Consent & DPDP Service (Port 8108).
"""

from ayusetu.consent.app import consent_app

app = consent_app
