from __future__ import annotations

from fastapi import APIRouter

from src.application.schemas.inputs import PenaltyWeightsUpdateRequest
from src.application.schemas.outputs import PenaltyWeightsResponse
from src.infrastructure.config.settings import settings

router = APIRouter(prefix="/api/v1/config", tags=["Configuration"])

# In-memory store for runtime-overridden penalty weights.
# In a production system these would be stored in DB/Redis.
_current_weights: dict[str, float] = {
    "penalizacion1": settings.PENALTY1_DEFAULT,
    "penalizacion2": settings.PENALTY2_DEFAULT,
}


@router.get(
    "/penalties",
    response_model=PenaltyWeightsResponse,
    summary="Get current penalty weight configuration",
    description="Returns penalizacion1 (transfer cost) and penalizacion2 (gap/bache cost) from the Esquivel Tovar model.",
)
async def get_penalties() -> PenaltyWeightsResponse:
    return PenaltyWeightsResponse(**_current_weights)


@router.put(
    "/penalties",
    response_model=PenaltyWeightsResponse,
    summary="Update penalty weight configuration",
    description=(
        "Updates the default penalty weights for new schedule generation requests. "
        "Existing jobs in the queue are not affected."
    ),
)
async def update_penalties(body: PenaltyWeightsUpdateRequest) -> PenaltyWeightsResponse:
    _current_weights["penalizacion1"] = body.penalizacion1
    _current_weights["penalizacion2"] = body.penalizacion2
    return PenaltyWeightsResponse(**_current_weights)
