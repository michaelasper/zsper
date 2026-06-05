"""Health route for Brain API runtime checks."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_profile_context, get_service_probes
from zsper.brain.api import ApiProfileContext, ServiceProbes, build_health_report


router = APIRouter()


@router.get("/api/health")
def read_health(
    context: ApiProfileContext = Depends(get_profile_context),
    service_probes: ServiceProbes = Depends(get_service_probes),
) -> dict[str, object]:
    return build_health_report(context, service_probes)
