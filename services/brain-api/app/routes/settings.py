"""Settings route for profile-scoped Brain API configuration."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_profile_context
from zsper.brain.api import ApiProfileContext, build_settings_report


router = APIRouter()


@router.get("/api/settings")
def read_settings(
    context: ApiProfileContext = Depends(get_profile_context),
) -> dict[str, object]:
    return build_settings_report(context)
