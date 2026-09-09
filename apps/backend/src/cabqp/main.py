from fastapi import FastAPI

from cabqp.api.health import router as health_router

app = FastAPI(title="ca-bqp-backend")

app.include_router(health_router)
