"""
Aegis MOS — Shared test fixtures.

Provides common pytest fixtures for async testing, HTTP client,
and simulator instances used across the test suite.
"""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import app
from simulator.clock import SelfCorrectingClock
from simulator.physics import PhysicsEngine
from simulator.state import SpacecraftState


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_client():
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def initial_state() -> SpacecraftState:
    """Return a fresh SpacecraftState with default initial values."""
    return SpacecraftState.initial()


@pytest.fixture
def physics_engine() -> PhysicsEngine:
    """Return a fresh PhysicsEngine instance."""
    return PhysicsEngine()


@pytest.fixture
def clock() -> SelfCorrectingClock:
    """Return a fresh SelfCorrectingClock at 1Hz."""
    return SelfCorrectingClock(hz=1.0)
