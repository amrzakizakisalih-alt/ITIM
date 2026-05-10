"""
ws_handlers – Main WebSocket handler.
"""

import json
import asyncio
import base64
import io
import os
import re
import time
import logging
from typing import List, Optional
from PIL import Image

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from core.connection_manager import ConnectionManager
from core.llm_client import LLMClient
from domain.math.math_expert import MathExpert
from domain.exercises.exercise_library import ExerciseLibrary
from app.session import SessionState, session_states
from app.intervention import intervention_loop

logger = logging.getLogger(__name__)

MAX_WS_PAYLOAD_BYTES = 15 * 1024 * 1024
MAX_STROKE_POINTS = 10_000
MAX_OCR_IMAGE_MB = 10


def _decode_base64_image(data_url: str) -> Optional[Image.Image]:
    try:
        if "," in data_url:
            data_url = data_url.split(",")[1]
        img_bytes = base64.b64decode(data_url)
        return Image.open(io.BytesIO(img_bytes))
    except Exception as e:
        logger.error("[OCR Decode] Failed to decode image: %s", e)
        return None


def _parse_latex_lines(raw_latex: str) -> List[str]:
    """
    Parse a multi-line OCR result into a list of LaTeX expressions.
    Handles newlines, backslashes, and $$...$$ delimiters.
    """
    if not raw_latex:
        return []

    # Remove global markdown delimiters if they exist
    text = raw_latex.strip()
    if text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()

    # Split by newlines or backslash-backslash (LaTeX line break)
    lines = re.split(r"\r?\n|\\\\", text)
    candidates: List[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Remove inline $$...$$
        line = re.sub(r"\$\$(.*?)\$\$", r"\1", line)
        line = line.strip("$")
        line = line.strip()
        if line and line.upper() != "NONE":
            candidates.append(line)
    return candidates


async def _heartbeat_loop(websocket: WebSocket):
    try:
        while True:
            await asyncio.sleep(25)
            if websocket.client_state.name != "CONNECTED":
                break
            await websocket.send_json({"type": "ping", "timestamp": asyncio.get_event_loop().time()})
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.debug("Heartbeat error: %s", exc)


async def _stroke_debounce(websocket: WebSocket, state: SessionState):
    """
    Wait 3s after the last stroke then propose an OCR check-in
    if content has been written.
    """
    await asyncio.sleep(3.0)
    if websocket.client_state.name != "CONNECTED":
        return

    now = time.time()
    # Cooldown between check-ins (20s)
    if now - state.last_stroke_checkin_time < 20:
        return

    strokes = state.stroke_buffer.get_active_strokes()
    if not strokes:
        return

    img = state.math_processor.render_strokes_cropped(strokes)
    if not img:
        return

    try:
        vision = state.math_processor.vision
        if not vision or not vision.has_vision:
            logger.debug("[Stroke debounce] No vision backend, skipping check-in")
            return

        latex = await asyncio.wait_for(
            vision.image_to_latex(img), timeout=10.0
        )
        if latex:
            # Parse multi-line expressions
            candidates = _parse_latex_lines(latex)
            latest = candidates[-1] if candidates else latex
            if latest not in state.last_latex_results:
                state.last_latex_results.append(latest)
                if len(state.last_latex_results) > 5:
                    state.last_latex_results.pop(0)
                state.last_stroke_checkin_time = now
                state.tutor.last_seen_latex = latest
                await websocket.send_json({
                    "type": "tutor_message",
                    "text": f"📐 I see: **{latest}**. Let me know if you want me to check this step.",
                    "role": "assistant",
                    "intervention_type": "stroke_checkin",
                })
            else:
                logger.debug("[Stroke debounce] Duplicate LaTeX ignored: %s", latest)
    except asyncio.TimeoutError:
        logger.debug("[Stroke debounce] OCR timeout")
    except Exception as e:
        logger.warning("[Stroke debounce] OCR error: %s", e)


async def _remove_finished_exercise_and_propose_next(websocket: WebSocket, state: SessionState):
    """
    Remove the completed exercise from the feed_ai queue and propose the remaining exercises.
    """
    await asyncio.sleep(2.0)
    if websocket.client_state.name != "CONNECTED":
        return

    current_ex = state.step_tracker.exercise
    if current_ex and state.exercise_queue:
        before = len(state.exercise_queue)
        state.exercise_queue = [
            ex for ex in state.exercise_queue
            if ex.get("problem_latex") != current_ex.get("problem_latex")
        ]
        if len(state.exercise_queue) < before:
            logger.info("[EXAM] Exercise removed from queue, %d remaining", len(state.exercise_queue))

    if state.exercise_queue:
        await websocket.send_json({
            "type": "tutor_message",
            "text": "Here are the remaining exercises. Pick the next one you'd like to tackle!",
            "role": "assistant",
            "intervention_type": "exercise_proposal",
        })
        await websocket.send_json({
            "type": "exercises_proposed",
            "exercises": state.exercise_queue,
            "source": "feed_ai",
        })
    else:
        await websocket.send_json({
            "type": "tutor_message",
            "text": "🎉 You've completed all the exercises! Great job!",
            "role": "assistant",
            "intervention_type": "exam_completed",
        })

    state.step_tracker.reset()


def register_websocket_handlers(
    app: FastAPI,
    manager: ConnectionManager,
    llm_client: LLMClient,
    math_expert: MathExpert,
    exercise_library: ExerciseLibrary,
):
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)

        ws_id = id(websocket)
        raw_user_id = websocket.query_params.get("user_id", "default")
        user_id = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_user_id)[:64] or "default"
        state = SessionState(
            user_id=user_id,
            llm_client=llm_client,
            math_expert=math_expert,
            exercise_library=exercise_library,
        )
        session_states[ws_id] = state

        welcome = state.profile_manager.load_or_create(state.actr.studentModel)
        await websocket.send_json({
            "type": "tutor_message",
            "text": welcome["message"],
            "role": "assistant",
            "intervention_type": "welcome",
        })

        intervention_task = asyncio.create_task(intervention_loop(websocket, state))
        heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket))

        try:
            while True:
                data = await websocket.receive_text()
                logger.info("[WS] Raw message received: %s bytes from %s", len(data), websocket.client.host if websocket.client else "unknown")
                if len(data) > MAX_WS_PAYLOAD_BYTES:
                    logger.warning("[WS] Payload too large: %s bytes", len(data))
                    await websocket.send_json({
                        "type": "error",
                        "error": "payload_too_large",
                        "message": f"Payload exceeds {MAX_WS_PAYLOAD_BYTES // (1024*1024)} MB limit.",
                    })
                    continue

                message = json.loads(data)

                # ── STROKE ────────────────────────────────────────────────
                if message.get("type") == "stroke":
                    points = message.get("points", []) or []
                    if len(points) > MAX_STROKE_POINTS:
                        logger.warning("[WS] Stroke too large: %s points", len(points))
                        await websocket.send_json({
                            "type": "error",
                            "error": "stroke_too_large",
                            "message": f"Stroke exceeds {MAX_STROKE_POINTS} points limit.",
                        })
                        continue
                    stroke = {
                        "points": points,
                        "tool": message.get("tool", "pen"),
                        "width": message.get("width", 2),
                        "color": message.get("color", "#000000"),
                        "timestamp": time.time(),
                    }
                    logger.info("[STROKE] tool=%s | %s points", stroke["tool"], len(stroke["points"]))
                    state.actr.update(message)
                    state.stroke_buffer.add(stroke)
                    await manager.broadcast(data, exclude=websocket)

                    frustration = state.stroke_analyzer.analyze(stroke)
                    if frustration:
                        logger.info("[STROKE ANALYZER] %s", frustration["reason"])
                        await websocket.send_json({
                            "type": "tutor_message",
                            "text": frustration["message"],
                            "role": "assistant",
                            "intervention_type": frustration["type"],
                        })

                    # Trigger an OCR check-in after 3s of silence
                    if state.stroke_debounce_task:
                        state.stroke_debounce_task.cancel()
                    state.stroke_debounce_task = asyncio.create_task(
                        _stroke_debounce(websocket, state)
                    )

                    gesture = state.gesture_recognizer.feed_stroke(stroke)
                    if gesture:
                        logger.info("[GESTURE] Detected: %s", gesture)
                        resp = state.gesture_recognizer.get_response(gesture)
                        if gesture == "check":
                            resp["text"] = "✅ I'll check your answer! Click 🧮 Check when you're ready."
                        elif gesture == "question":
                            resp["text"] = "❓ Need a hint? Here's a clue: " + (
                                state.step_tracker.exercise.get("hint", "Think step by step.")
                                if state.step_tracker.exercise else "Think step by step."
                            )
                        await websocket.send_json({
                            "type": "gesture_response",
                            "gesture": gesture,
                            "text": resp["text"],
                            "role": "assistant",
                        })

                    # Deferred auto-OCR — simplified: 1 image, 1 vision call
                    if state.ocr_task:
                        state.ocr_task.cancel()

                    async def _delayed_ocr():
                        latex = None
                        try:
                            await asyncio.sleep(0.8)

                            strokes = state.stroke_buffer.get_active_strokes()
                            if not strokes:
                                return

                            img = state.math_processor.render_strokes_cropped(strokes)
                            if img is None:
                                return

                            vision = state.math_processor.vision
                            if vision and vision.has_vision:
                                latex = await asyncio.wait_for(
                                    vision.image_to_latex(img), timeout=30.0
                                )
                                if latex:
                                    logger.info("[LaTeX vision] %s", latex)
                                    # Parse multi-line expressions
                                    candidates = _parse_latex_lines(latex)
                                    latest = candidates[-1] if candidates else latex
                                    await websocket.send_json({"type": "latex_update", "latex": latest})
                                else:
                                    logger.info("[Auto OCR] No LaTeX recognized from strokes")
                                    await websocket.send_json({
                                        "type": "tutor_message",
                                        "text": "📝 I see your writing, but I couldn't clearly recognize the math. Try writing a bit larger or clearer!",
                                        "role": "assistant",
                                        "intervention_type": "ocr_failed",
                                    })
                            else:
                                logger.warning("[Auto OCR] No vision backend available")
                                await websocket.send_json({
                                    "type": "tutor_message",
                                    "text": "📝 I received your writing, but OCR is not available right now. You can still type your answer in the chat!",
                                    "role": "assistant",
                                    "intervention_type": "ocr_unavailable",
                                })

                            # StepTracker — test each detected expression
                            if state.step_tracker.active and latex:
                                candidates = _parse_latex_lines(latex)
                                feedback = await state.step_tracker.check_steps(candidates)
                                if feedback:
                                    logger.info("[STEP TRACKER] %s", feedback["status"])
                                    await websocket.send_json(feedback)
                                    if feedback["status"] == "completed":
                                        concept = state.step_tracker.exercise.get("concept", "algebra")
                                        state.actr.studentModel.update_competence(concept, success=True, amount=2.0)
                                        # Sequential exam mode: move to the next exercise
                                        if state.exercise_queue:
                                            asyncio.create_task(_remove_finished_exercise_and_propose_next(websocket, state))

                        except asyncio.CancelledError:
                            logger.debug("[Auto OCR] Task cancelled")
                            raise
                        except asyncio.TimeoutError:
                            logger.warning("[Auto OCR] Vision timeout")
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": "⏱️ I'm taking too long to read your handwriting. You can type your answer in the chat if it's easier!",
                                "role": "assistant",
                                "intervention_type": "ocr_timeout",
                            })
                        except Exception as e:
                            logger.exception("[Auto OCR ERROR] %s", e)
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": f"⚠️ I had trouble reading your writing. ({type(e).__name__}: {e})",
                                "role": "assistant",
                                "intervention_type": "ocr_error",
                            })

                    state.ocr_task = asyncio.create_task(_delayed_ocr())

                # ── USER CHAT MESSAGE ─────────────────────────────────────
                elif message.get("type") == "user_message":
                    user_text = message.get("text", "")
                    logger.info("[CHAT] %s", user_text)
                    response = await state.tutor.on_user_message(user_text)
                    resp_type = response.get("type")

                    if resp_type == "exercise_accepted":
                        ex = response["exercise"]
                        state.step_tracker.set_exercise(ex)
                        state.tutor.set_current_exercise(ex)
                        await websocket.send_json(response)
                        await websocket.send_json({
                            "type": "tutor_message",
                            "text": response["text"],
                            "role": "assistant",
                            "intervention_type": "exercise_started",
                            "progress": state.step_tracker.get_progress(),
                        })

                    elif resp_type == "exercise_rejected":
                        concepts = list({ex.get("concept", "generic") for ex in state.detected_exercises})
                        if not concepts:
                            concepts = ["generic"]
                        new_exercises = state.exercise_gen.generate_for_concepts(concepts)
                        state.detected_exercises = new_exercises
                        await websocket.send_json(response)
                        await websocket.send_json({
                            "type": "exercises_detected",
                            "exercises": new_exercises,
                        })
                        tutor_resp = await state.tutor.propose_exercises(new_exercises)
                        await websocket.send_json(tutor_resp)

                    elif resp_type == "exercise_harder":
                        diff_map = {"easy": "medium", "medium": "hard", "hard": "hard"}
                        harder_exercises = []
                        for ex in state.detected_exercises:
                            concept = ex.get("concept", "generic")
                            new_diff = diff_map.get(ex.get("difficulty", "easy"), "hard")
                            harder_ex = state.exercise_gen.generate(concept, new_diff)
                            harder_exercises.append(harder_ex)
                        state.detected_exercises = harder_exercises
                        await websocket.send_json(response)
                        await websocket.send_json({
                            "type": "exercises_detected",
                            "exercises": harder_exercises,
                        })
                        tutor_resp = await state.tutor.propose_exercises(harder_exercises)
                        await websocket.send_json(tutor_resp)

                    elif resp_type == "hint_request":
                        ex = state.step_tracker.exercise or (
                            state.detected_exercises[0] if state.detected_exercises else None
                        )
                        if ex:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": f"💡 **Hint:** {ex.get('hint', 'Think step by step.')}",
                                "role": "assistant",
                                "intervention_type": "hint",
                            })
                        else:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": "I don't have an active exercise to give a hint for. Try starting one first!",
                                "role": "assistant",
                            })

                    elif resp_type == "answer_request":
                        ex = state.step_tracker.exercise or (
                            state.detected_exercises[0] if state.detected_exercises else None
                        )
                        if ex:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": (
                                    f"✅ **Answer:** {ex['correct_latex']}\n\n"
                                    f"💡 *Hint:* {ex.get('hint', '')}"
                                ),
                                "role": "assistant",
                                "intervention_type": "answer_shown",
                            })
                        else:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": "I don't have an active exercise to show the answer for. Try starting one first!",
                                "role": "assistant",
                            })

                    elif resp_type == "next_step_request":
                        if state.step_tracker.active:
                            feedback = state.step_tracker.skip_step()
                            await websocket.send_json(feedback)
                            if feedback and feedback.get("status") == "completed" and state.exercise_queue:
                                asyncio.create_task(_remove_finished_exercise_and_propose_next(websocket, state))
                        else:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": "No active exercise to skip. Start an exercise first!",
                                "role": "assistant",
                            })

                    elif resp_type == "give_up_request":
                        state.step_tracker.reset()
                        # Sequential exam mode: move to the next one
                        if state.exercise_queue:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": "No worries! Moving on to the next exercise. 🔄",
                                "role": "assistant",
                            })
                            asyncio.create_task(_remove_finished_exercise_and_propose_next(websocket, state))
                        else:
                            concepts = list({ex.get("concept", "generic") for ex in state.detected_exercises})
                            if not concepts:
                                concepts = ["generic"]
                            new_exercises = state.exercise_gen.generate_for_concepts(concepts)
                            state.detected_exercises = new_exercises
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": "No worries! Let's try something else. 🔄",
                                "role": "assistant",
                            })
                            await websocket.send_json({
                                "type": "exercises_detected",
                                "exercises": new_exercises,
                            })
                            tutor_resp = await state.tutor.propose_exercises(new_exercises)
                            await websocket.send_json(tutor_resp)

                    elif resp_type == "restart_request":
                        if state.step_tracker.exercise:
                            state.step_tracker.set_exercise(state.step_tracker.exercise)
                            state.tutor.set_current_exercise(state.step_tracker.exercise)
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": (
                                    f"🔄 Restarting!\n\n"
                                    f"Problem: ${state.step_tracker.exercise['problem_latex']}$\n\n"
                                    f"Show me step 1."
                                ),
                                "role": "assistant",
                                "intervention_type": "exercise_restarted",
                                "progress": state.step_tracker.get_progress(),
                            })
                        else:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": "No active exercise to restart. Start one first!",
                                "role": "assistant",
                            })

                    elif resp_type == "easier_request":
                        diff_map = {"hard": "medium", "medium": "easy", "easy": "easy"}
                        easier_exercises = []
                        for ex in state.detected_exercises:
                            concept = ex.get("concept", "generic")
                            new_diff = diff_map.get(ex.get("difficulty", "easy"), "easy")
                            easier_ex = state.exercise_gen.generate(concept, new_diff)
                            easier_exercises.append(easier_ex)
                        state.detected_exercises = easier_exercises
                        await websocket.send_json({
                            "type": "tutor_message",
                            "text": "Let's take it down a notch. 🎯 Here are easier versions.",
                            "role": "assistant",
                        })
                        await websocket.send_json({
                            "type": "exercises_detected",
                            "exercises": easier_exercises,
                        })
                        tutor_resp = await state.tutor.propose_exercises(easier_exercises)
                        await websocket.send_json(tutor_resp)

                    elif resp_type == "recap_request":
                        ex = state.step_tracker.exercise or (
                            state.detected_exercises[0] if state.detected_exercises else None
                        )
                        if ex:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": (
                                    f"📋 **Recap:**\n\n"
                                    f"Problem: {ex['problem_latex']}\n\n"
                                    f"Difficulty: {ex.get('difficulty', 'unknown')}\n"
                                    f"Concept: {ex.get('concept', 'unknown').replace('_', ' ')}"
                                ),
                                "role": "assistant",
                                "intervention_type": "recap",
                            })
                        else:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": "No active exercise to recap. Start one first!",
                                "role": "assistant",
                            })

                    else:
                        await websocket.send_json(response)

                # ── MATH SUBMIT ───────────────────────────────────────────
                elif message.get("type") == "math_submit":
                    user_latex = message.get("user_latex", "")
                    correct_latex = message.get("correct_latex", "")

                    # If correct_latex is not provided, derive it from the active exercise
                    if not correct_latex and state.step_tracker.active:
                        step_idx = state.step_tracker.current_step
                        if step_idx < len(state.step_tracker.expected_steps):
                            correct_latex = state.step_tracker.expected_steps[step_idx]
                        else:
                            correct_latex = state.step_tracker.exercise.get("correct_latex", "") if state.step_tracker.exercise else ""
                        logger.info("[MATH SUBMIT] Derived correct_latex from active exercise: %s", correct_latex)

                    logger.info("[MATH SUBMIT] user=%s | correct=%s", user_latex, correct_latex)
                    response = await state.tutor.on_math_submission(user_latex, correct_latex)
                    await websocket.send_json(response)

                # ── OCR CAPTURE ───────────────────────────────────────────
                elif message.get("type") == "ocr_capture":
                    image_data = message.get("image_data", "")
                    if len(image_data) > MAX_OCR_IMAGE_MB * 1024 * 1024:
                        logger.warning("[WS] OCR image too large: %s bytes", len(image_data))
                        await websocket.send_json({
                            "type": "error",
                            "error": "ocr_image_too_large",
                            "message": f"OCR image exceeds {MAX_OCR_IMAGE_MB} MB limit.",
                        })
                        continue
                    # Inject the response into the most recent OCR request
                    if state.ocr_requests:
                        latest_req_id = max(state.ocr_requests.keys())
                        latest_future = state.ocr_requests[latest_req_id]
                        if not latest_future.done():
                            latest_future.set_result(image_data)

                # ── DOCUMENT IMPORTED ─────────────────────────────────────
                elif message.get("type") == "document_imported":
                    doc_text = message.get("text", "")
                    doc_name = message.get("name", "document")
                    feed_only = message.get("feed_only", False)
                    image_data = message.get("image_data", "")
                    logger.info("[DOC IMPORT] '%s' | text=%s chars | image=%s | feed_only=%s",
                                doc_name, len(doc_text), bool(image_data), feed_only)

                    # If no text but an image → vision OCR
                    if not doc_text.strip() and image_data:
                        img = _decode_base64_image(image_data)
                        if img:
                            vision = state.math_processor.vision
                            if vision and vision.has_vision:
                                try:
                                    ocr_text = await asyncio.wait_for(
                                        vision.ocr_document(img), timeout=30.0
                                    )
                                    if ocr_text:
                                        doc_text = ocr_text
                                        logger.info("[DOC OCR] Extracted %s chars from image", len(doc_text))
                                        await websocket.send_json({
                                            "type": "tutor_message",
                                            "text": f"📄 '{doc_name}' scanned — I extracted {len(doc_text)} characters from the image.",
                                            "role": "assistant",
                                            "intervention_type": "document_ocr",
                                        })
                                except asyncio.TimeoutError:
                                    logger.warning("[DOC OCR] Vision timeout")
                                except Exception as e:
                                    logger.error("[DOC OCR] Vision error: %s", e)
                            else:
                                logger.warning("[DOC OCR] No vision backend available")
                        else:
                            logger.warning("[DOC OCR] Failed to decode image")

                    state.document_text = doc_text
                    state.detected_exercises = []

                    if doc_text.strip():
                        result = await state.doc_processor.process_document_async(
                            doc_text, state.actr.studentModel
                        )
                        logger.info("[DOC CONCEPTS] %s", [c["name"] for c in result["concepts"]])

                        # 1. Try to extract the REAL exercises from the document
                        extracted = await state.exercise_gen.extract_exercises_from_document(
                            doc_text, llm_client=llm_client
                        )
                        logger.info("[DOC IMPORT] Extracted %d exercises from '%s'", len(extracted), doc_name)

                        # 2. Fallback: generate inspired exercises if nothing was extracted
                        if extracted:
                            exercises = extracted
                            focus_msg = (
                                f"📄 I found **{len(exercises)} exercise(s)** in your document.\n\n"
                                "These are the original exercises from your file — "
                                "pick one to start solving it!"
                            )
                        else:
                            exercises, _ = await state.exercise_gen.generate_from_document(
                                doc_text, llm_client=llm_client
                            )
                            logger.info("[DOC IMPORT] Generated %d exercises for '%s'", len(exercises), doc_name)
                            focus_msg = state.doc_processor.generate_focus_message(result["concepts"])
                            if exercises:
                                focus_msg += (
                                    "\n\n🎯 I've generated custom exercises based on your document. "
                                    "Pick one to start!"
                                )

                        state.last_exercises = exercises
                        state.detected_exercises = exercises

                        if feed_only:
                            # Feed AI mode: store all exercises and propose them
                            # the user chooses which one to do; at the end of each exercise we
                            # remove it from the list and propose the remaining ones.
                            focus_msg = state.doc_processor.generate_focus_message(result["concepts"])
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": focus_msg,
                                "role": "assistant",
                                "intervention_type": "document_analysis",
                            })
                            if exercises:
                                state.exercise_queue = list(exercises)
                                await websocket.send_json({
                                    "type": "exercises_proposed",
                                    "exercises": exercises,
                                    "source": "feed_ai",
                                })
                            else:
                                await websocket.send_json({
                                    "type": "tutor_message",
                                    "text": "I couldn't find or generate any exercises from this document. Try writing an exercise directly on the page!",
                                    "role": "assistant",
                                    "intervention_type": "document_analysis",
                                })
                        else:
                            await websocket.send_json({
                                "type": "tutor_message",
                                "text": focus_msg,
                                "role": "assistant",
                                "intervention_type": "document_analysis",
                            })
                            if exercises:
                                await websocket.send_json({
                                    "type": "exercises_proposed",
                                    "exercises": exercises,
                                    "source": "document" if extracted else "generated",
                                })
                    else:
                        await websocket.send_json({
                            "type": "tutor_message",
                            "text": f"📄 '{doc_name}' imported, but I couldn't extract readable text. You can still write on it!",
                            "role": "assistant",
                        })

                # ── START EXERCISE ────────────────────────────────────────
                elif message.get("type") == "start_exercise":
                    ex = message.get("exercise")
                    if ex:
                        logger.info("[START EXERCISE] %s", ex.get("concept"))
                        state.step_tracker.set_exercise(ex)
                        state.tutor.set_current_exercise(ex)
                        await websocket.send_json({
                            "type": "tutor_message",
                            "text": f"📝 Let's solve this step by step!\n\nProblem: {ex['problem_latex']}\n\nShow me step 1.",
                            "role": "assistant",
                            "intervention_type": "exercise_started",
                            "progress": state.step_tracker.get_progress(),
                        })

                # ── EXERCISE REQUEST ──────────────────────────────────────
                elif message.get("type") == "exercise_request":
                    concept = message.get("concept", "generic")
                    difficulty = message.get("difficulty", "easy")
                    logger.info("[EXERCISE REQUEST] %s | %s", concept, difficulty)

                    ex = state.exercise_gen.generate(concept, difficulty)
                    await websocket.send_json({"type": "exercise", "exercise": ex})

                # ── TEXT ZONE UPDATE ──────────────────────────────────────
                elif message.get("type") == "text_zone_update":
                    page_id = message.get("page_id", "")
                    zone_id = message.get("zone_id", "")
                    text = message.get("text", "")
                    logger.info("[TEXT ZONE] page=%s zone=%s | %s", page_id, zone_id, text[:60] + ('...' if len(text) > 60 else ''))
                    if text.strip():
                        state.actr.studentModel.record_action("text_input")

                # ── CLEAR ─────────────────────────────────────────────────
                elif message.get("type") == "clear":
                    if state.ocr_task:
                        state.ocr_task.cancel()
                        state.ocr_task = None
                    state.stroke_buffer.clear()
                    state.stroke_analyzer.reset()
                    state.gesture_recognizer.reset_accumulator()
                    state.step_tracker.reset()
                    state.tutor.reset_session()
                    state.actr.studentModel.reset_behavioral_counters()
                    state.last_ocr_time = 0.0
                    state.last_ocr_timestamp = 0.0
                    state.last_latex_results.clear()
                    state.ocr_requests.clear()
                    state.ocr_request_counter = 0
                    logger.info("[CLEAR] Session reset")

        except WebSocketDisconnect:
            pass
        finally:
            if state.ocr_task:
                state.ocr_task.cancel()
            if state.stroke_debounce_task:
                state.stroke_debounce_task.cancel()
            intervention_task.cancel()
            heartbeat_task.cancel()
            state.profile_manager.save(state.actr.studentModel)
            await manager.disconnect(websocket)
            session_states.pop(ws_id, None)
            logger.info("[WS] Client disconnected (user=%s)", state.user_id)
