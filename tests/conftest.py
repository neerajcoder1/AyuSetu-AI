"""
Global Pytest Configuration & Test Fixtures
============================================
Ensures test isolation across test suites.
"""

import pytest
from ayusetu.gateway.middleware.rate_limit import RateLimiter


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Ensure in-memory rate limiter buckets and counters are cleared between test cases."""
    RateLimiter.clear_in_memory()
    yield
    RateLimiter.clear_in_memory()
