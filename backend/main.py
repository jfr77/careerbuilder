"""carreerbuilder backend. Run with:  uvicorn backend.main:app --reload

Loads .env from the project root (DATABASE_URL, ANTHROPIC_API_KEY) before
anything else so backend.db sees the variables.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from . import llm  # noqa: E402
from .db import check_schema  # noqa: E402
from .routers import (chat, documents, events, filters, jobs, pipeline,  # noqa: E402
                      profiles, scrape, templates)


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_schema()  # exits with a pointer to schema.sql if tables are missing
    templates.seed_builtins()  # idempotent: ensures the built-in template library exists
    if not llm.available():
        print("NOTE: ANTHROPIC_API_KEY is not set — the app runs, but LLM features "
              "(chat, scoring, documents, recommendations) will return a clear 503.")
    yield


app = FastAPI(title="carreerbuilder", lifespan=lifespan)

# The Vite dev server proxies /api in production-like setups; CORS kept open
# for localhost dev convenience. No secrets ever leave the backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (profiles, jobs, filters, scrape, pipeline, events, chat, documents, templates):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"ok": True, "llm_available": llm.available()}


if __name__ == "__main__":
    # `python -m backend.main` — same PORT contract as the Makefile.
    import os

    import uvicorn

    uvicorn.run("backend.main:app", port=int(os.environ.get("PORT", "8787")), reload=True)
