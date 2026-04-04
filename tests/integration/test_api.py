from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.main import app
from src.application.schemas.outputs import JobSubmittedResponse


SAMPLE_REQUEST = {
    "teachers": [
        {
            "id": "T1",
            "name": "Prof A",
            "teacher_type": "REGULAR",
            "campus_ids": ["C1"],
            "availability_slots": [],
            "max_hours_per_day": 6,
        }
    ],
    "subjects": [
        {
            "id": "S1",
            "name": "Calculo",
            "group_id": "G1",
            "required_sessions": 1,
            "campus_id": "C1",
            "student_count": 20,
        }
    ],
    "rooms": [
        {
            "id": "R1",
            "name": "Aula 101",
            "campus_id": "C1",
            "capacity": 40,
        }
    ],
    "timeslots": [
        {
            "id": "TS1",
            "day": 0,
            "slot_index": 0,
            "start_time": "07:00",
            "end_time": "09:00",
        }
    ],
    "penalty_weights": {"penalizacion1": 2.0, "penalizacion2": 1.0},
    "solver": "pulp_cbc",
    "time_limit_seconds": 60,
}


@pytest.fixture
def mock_use_case() -> AsyncMock:
    mock = AsyncMock()
    mock.execute.return_value = JobSubmittedResponse(
        job_id="test-job-123",
        ws_url="ws://testserver/ws/test-job-123",
    )
    return mock


@pytest.mark.asyncio
async def test_health_check() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_generate_schedule_returns_202(mock_use_case: AsyncMock) -> None:
    with patch(
        "src.api.routers.schedules.get_generate_use_case",
        return_value=lambda: mock_use_case,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post("/api/v1/schedules/generate", json=SAMPLE_REQUEST)

    assert response.status_code in (200, 202)


@pytest.mark.asyncio
async def test_invalid_body_returns_422() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/schedules/generate",
            json={"teachers": [], "subjects": [], "rooms": [], "timeslots": []},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_negative_penalty_rejected() -> None:
    bad_request = dict(SAMPLE_REQUEST)
    bad_request["penalty_weights"] = {"penalizacion1": -5.0, "penalizacion2": 1.0}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/api/v1/schedules/generate", json=bad_request)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_procom_teacher_requires_two_campuses() -> None:
    bad_request = dict(SAMPLE_REQUEST)
    bad_request["teachers"] = [
        {
            "id": "T1",
            "name": "PROCOM Teacher",
            "teacher_type": "PROCOM",
            "campus_ids": ["C1"],  # Only 1 campus — should fail
            "availability_slots": [],
            "max_hours_per_day": 6,
        }
    ]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/api/v1/schedules/generate", json=bad_request)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_config_penalties() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/config/penalties")
    assert response.status_code == 200
    data = response.json()
    assert "penalizacion1" in data
    assert "penalizacion2" in data
