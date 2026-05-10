"""
api_routes – REST administration endpoints.
"""

import io
import os
import asyncio
from typing import Optional

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse

from domain.math.math_expert import MathExpert
from domain.exercises.exercise_library import ExerciseLibrary
from core.llm_client import LLMClient
from groq import Groq


def create_api_routes(
    llm_client: LLMClient,
    math_expert: MathExpert,
    exercise_library: ExerciseLibrary,
    dist_dir: str,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    def read_root():
        return {
            "status": "ITIM Backend Running",
            "modules": ["ActR", "Tutor", "MathProcessor", "LLM", "DocumentProcessor", "ExerciseGenerator"],
            "llm_available": llm_client.is_available(),
        }

    @router.get("/")
    def serve_index():
        index_path = os.path.join(dist_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(
                index_path,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        return {"status": "ITIM Backend Running — frontend not built"}

    # ── Buggy rules administration API ──────────────────────────────────────────

    @router.get("/api/buggy-rules")
    def list_buggy_rules():
        local = [r.to_dict() for r in math_expert.buggy_rules]
        pending = math_expert.learner.list_pending()
        return {
            "local_rules": local,
            "pending_discoveries": pending,
            "total_local": len(local),
            "total_pending": len(pending),
        }

    @router.get("/api/buggy-rules/pending")
    def list_pending_rules():
        return {"pending": math_expert.learner.list_pending()}

    @router.post("/api/buggy-rules/{name}/validate")
    def validate_rule(name: str):
        ok = math_expert.learner.validate_rule(name)
        if ok:
            math_expert.reload_learned_rules()
            return {"success": True, "name": name, "message": "Rule validated and activated."}
        return {"success": False, "name": name, "message": "Rule not found."}

    @router.delete("/api/buggy-rules/{name}")
    def reject_rule(name: str):
        ok = math_expert.learner.reject_rule(name)
        if ok:
            math_expert.reload_learned_rules()
            return {"success": True, "name": name, "message": "Rule rejected and removed."}
        return {"success": False, "name": name, "message": "Rule not found."}

    # ── Detected exercises administration API ───────────────────────────────────

    @router.get("/api/documents/exercises")
    def list_detected_exercises():
        return {
            "exercises": [],
            "message": "Use WebSocket document_imported to populate detected exercises per session.",
        }

    # ── Exercise library API ────────────────────────────────────────────────────

    @router.get("/api/exercises")
    def list_exercises(
        concept: Optional[str] = None,
        difficulty: Optional[str] = None,
        validated_only: bool = False,
        limit: int = 20,
    ):
        results = exercise_library.search(
            concept=concept,
            difficulty=difficulty,
            validated_only=validated_only,
            limit=limit,
        )
        return {"exercises": results, "total": len(results)}

    @router.get("/api/exercises/pending")
    def list_pending_exercises():
        return {"pending": exercise_library.list_pending()}

    @router.post("/api/exercises/{ex_id}/validate")
    def validate_exercise(ex_id: str):
        ok = exercise_library.validate(ex_id)
        if ok:
            return {"success": True, "id": ex_id, "message": "Exercise validated."}
        return {"success": False, "id": ex_id, "message": "Exercise not found."}

    @router.delete("/api/exercises/{ex_id}")
    def delete_exercise(ex_id: str):
        ok = exercise_library.remove(ex_id)
        if ok:
            return {"success": True, "id": ex_id, "message": "Exercise removed."}
        return {"success": False, "id": ex_id, "message": "Exercise not found."}

    @router.get("/api/exercises/stats")
    def exercise_stats():
        return exercise_library.stats()

    # ── Speech-to-Text (Groq Whisper) ──────────────────────────────────────────

    @router.post("/api/transcribe")
    async def transcribe_audio(file: UploadFile = File(...)):
        content = await file.read()
        client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        transcription = await asyncio.to_thread(
            client.audio.transcriptions.create,
            file=(file.filename or "audio.webm", content),
            model="whisper-large-v3",
            temperature=0,
            response_format="verbose_json",
        )
        return {"text": transcription.text}

    # ── Text-to-Speech (Groq Orpheus) ─────────────────────────────────────────

    @router.post("/api/tts")
    async def text_to_speech(body: dict):
        text = body.get("text", "")
        client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

        def fetch_audio():
            response = client.audio.speech.create(
                model="canopylabs/orpheus-v1-english",
                voice="autumn",
                response_format="wav",
                input=text,
            )
            buf = io.BytesIO()
            for chunk in response.iter_bytes():
                buf.write(chunk)
            buf.seek(0)
            return buf

        buf = await asyncio.to_thread(fetch_audio)
        return StreamingResponse(buf, media_type="audio/wav")

    # ── Catch-all SPA ──────────────────────────────────────────────────────────

    @router.get("/{path:path}")
    async def serve_spa(path: str):
        file_path = os.path.join(dist_dir, path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        index_path = os.path.join(dist_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(
                index_path,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        return {"status": "ITIM Backend Running — frontend not built"}

    return router
