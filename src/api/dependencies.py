from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.generate_schedule import GenerateScheduleUseCase
from src.application.use_cases.get_schedule import GetScheduleUseCase
from src.infrastructure.persistence.database import get_db_session
from src.infrastructure.persistence.schedule_repository import SQLAlchemyScheduleRepository


async def get_repository(
    session: AsyncSession = Depends(get_db_session),
) -> SQLAlchemyScheduleRepository:
    return SQLAlchemyScheduleRepository(session)


async def get_generate_use_case(
    repo: SQLAlchemyScheduleRepository = Depends(get_repository),
) -> GenerateScheduleUseCase:
    return GenerateScheduleUseCase(repository=repo)


async def get_query_use_case(
    repo: SQLAlchemyScheduleRepository = Depends(get_repository),
) -> GetScheduleUseCase:
    return GetScheduleUseCase(repository=repo)
