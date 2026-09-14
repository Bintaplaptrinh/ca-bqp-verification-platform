"""FastAPI Application Entry Point for CA/BQP Verification Platform.

Standard: Quality-first 2026 Production Architecture.
Provides REST endpoints, OpenAPI docs, and CORS middleware for frontend communication.
"""

import sys
from pathlib import Path

# Add src to sys.path so cabqp package can be imported easily when running from root or apps/backend
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import primary cases routers
from cabqp.api.cases import router as api_cases_router
from cabqp.modules.cases.router import router as module_cases_router

app = FastAPI(
    title="CA/BQP Verification Platform API",
    description="Hệ thống tra cứu, xác minh đối tượng và hỗ trợ nghiệp vụ an sinh BCA/BQP (Tiêu chuẩn Quality-first 2026)",
    version="2026.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for Frontend (Vite on localhost:3000, localhost:5173, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount module router providing /api/v1/cases/verify, /api/v1/cases/upload, /api/v1/cases
app.include_router(module_cases_router, prefix="/api/v1")
app.include_router(module_cases_router, prefix="/api")

# Mount primary router from api/cases at /api/v1 (providing /api/v1/verification/cases)
app.include_router(api_cases_router, prefix="/api/v1")
app.include_router(api_cases_router, prefix="/api")


@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
def health_check():
    """Health check endpoint for container orchestration and uptime monitoring."""
    return {
        "status": "ok",
        "service": "ca-bqp-backend",
        "version": "2026.1.0",
        "quality_standard": "Quality-first 2026",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
