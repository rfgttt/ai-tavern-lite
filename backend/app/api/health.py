from fastapi import APIRouter
from ..schemas import HealthResponse
from ..core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version="2.2.0-preview.1",
        mock_mode=settings.mock_llm
    )
