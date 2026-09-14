"""Health check API router for container lifecycle & Kubernetes probes."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "ca-bqp-backend",
        "version": "2026.1.0",
        "quality_standard": "Quality-first 2026",
    }
