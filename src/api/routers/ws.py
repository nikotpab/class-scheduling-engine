from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.infrastructure.persistence.database import AsyncSessionFactory
from src.infrastructure.persistence.schedule_repository import SQLAlchemyScheduleRepository
from src.infrastructure.websockets.connection_manager import manager

router = APIRouter(tags=["WebSockets"])
logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 1.0
_TERMINAL_STATUSES = {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "FAILED"}


@router.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket endpoint for real-time job completion notifications.

    Connect: ws://host/ws/{job_id}

    The client receives JSON messages:
        { "event": "schedule.status", "job_id": "...", "status": "RUNNING" }
        { "event": "schedule.completed", "job_id": "...", "status": "OPTIMAL", "penalty_score": "1.5" }

    The connection is closed server-side when the job reaches a terminal state.
    """
    await manager.connect(job_id, websocket)
    logger.info("WS client connected to job_id=%s", job_id)

    try:
        # Also poll DB in case the task finished before WS connected
        while True:
            async with AsyncSessionFactory() as session:
                repo = SQLAlchemyScheduleRepository(session)
                schedule = await repo.find_by_job_id(job_id)

            if schedule is None:
                await manager.send_personal(
                    websocket,
                    {"event": "error", "job_id": job_id, "detail": "Job not found."},
                )
                break

            await manager.send_personal(
                websocket,
                {
                    "event": "schedule.status",
                    "job_id": job_id,
                    "status": schedule.status.value,
                    "penalty_score": str(schedule.penalty_score),
                },
            )

            if schedule.status.value in _TERMINAL_STATUSES:
                break

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    except WebSocketDisconnect:
        logger.info("WS client disconnected: job_id=%s", job_id)
    finally:
        manager.disconnect(job_id, websocket)
