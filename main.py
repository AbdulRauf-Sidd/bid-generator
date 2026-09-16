from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.routes.jobs import router as jobs_router
from app.routes.bids import router as bids_router
from app.routes.prompts import router as prompts_router
from app.routes.memory import router as memory_router
from app.routes.auth import router as auth_router
from app.routes.profiles import router as profiles_router
from app.routes.projects import router as projects_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Upwork Bid Generator API",
    description=(
        "AI-powered Upwork bid proposals. "
        "Uses Mistral embeddings + pgvector RAG to write proposals informed by your past projects."
    ),
    version="2.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(bids_router, prefix="/api/v1")
app.include_router(prompts_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=settings.DEBUG)
