"""
intervention – Proactive tutor intervention loop.
"""

import asyncio
import logging

from fastapi import WebSocket
from app.session import SessionState

logger = logging.getLogger(__name__)


async def intervention_loop(websocket: WebSocket, state: SessionState):
    try:
        while True:
            await asyncio.sleep(10)
            if websocket.client_state.name != "CONNECTED":
                logger.debug("Intervention loop stopping: websocket closed")
                break
            msg = await state.tutor.on_stroke_intervention(
                step_tracker_active=state.step_tracker.active
            )
            if msg:
                logger.info("[TUTOR INTERVENTION] %s", msg.get("text", "")[:60])
                await websocket.send_json(msg)
    except asyncio.CancelledError:
        logger.debug("Intervention loop cancelled")
    except Exception as exc:
        logger.error("Intervention loop error: %s", exc, exc_info=True)
