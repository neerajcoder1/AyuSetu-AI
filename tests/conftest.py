"""
Global Pytest Configuration & Test Fixtures
============================================
Ensures test isolation across test suites.
"""

import pytest
from ayusetu.gateway.middleware.rate_limit import RateLimiter
from ayusetu.audit.service import audit_service


@pytest.fixture(autouse=True)
def reset_test_state():
    """Ensure in-memory rate limiter and audit state are cleared between test cases."""
    RateLimiter.clear_in_memory()
    audit_service.clear_for_testing()
    yield
    RateLimiter.clear_in_memory()
    audit_service.clear_for_testing()
