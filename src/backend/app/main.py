"""
main – FastAPI entry point for the ITIM backend.

Handles only orchestration: app creation,
CORS configuration, singleton instantiation, and registration
of WebSocket routes / handlers.
"""

import os
# Force CPU if the CUDA driver is incompatible (avoids NVML warnings)
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.connection_manager import ConnectionManager
from core.llm_client import LLMClient
from domain.math.math_expert import MathExpert
from domain.exercises.exercise_library import ExerciseLibrary
from app.api_routes import create_api_routes
from app.ws_handlers import register_websocket_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Global singletons ───────────────────────────────────────────────────────

manager = ConnectionManager()
llm_client = LLMClient()
math_expert = MathExpert(llm_client=llm_client)
exercise_library = ExerciseLibrary()

# ── FastAPI application ─────────────────────────────────────────────────────

app = FastAPI()

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,https://localhost:5173,http://localhost:3000,https://localhost:3000,https://172.21.162.148:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

_dist_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")

# ── Routes ──────────────────────────────────────────────────────────────────

api_router = create_api_routes(
    llm_client=llm_client,
    math_expert=math_expert,
    exercise_library=exercise_library,
    dist_dir=_dist_dir,
)
app.include_router(api_router)

register_websocket_handlers(
    app=app,
    manager=manager,
    llm_client=llm_client,
    math_expert=math_expert,
    exercise_library=exercise_library,
)

# ── Static files (frontend build) ───────────────────────────────────────────

if os.path.isdir(_dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist_dir, "assets")), name="assets")

# ── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
