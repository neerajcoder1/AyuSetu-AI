"""
services/audit Entry Point
==========================
Microservice root for Audit Service (Port 8109).
"""

from ayusetu.audit.app import audit_app

app = audit_app
