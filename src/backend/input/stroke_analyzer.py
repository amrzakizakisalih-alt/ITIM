"""
StrokeAnalyzer – Behavioral stroke analysis to detect
frustration, hesitation, and blocking patterns without OCR.
"""

import time
from typing import Dict, Any, Optional
from collections import deque


class StrokeAnalyzer:
    """
    Analyzes strokes in real time to detect behavioral
    indicators of difficulty.
    """

    def __init__(self, window_seconds: int = 15):
        self.window_seconds = window_seconds
        self.strokes = deque()  # (timestamp, stroke_dict)
        self.last_intervention_time = 0.0
        self.intervention_cooldown = 20  # seconds between two stroke alerts

    def analyze(self, stroke: dict) -> Optional[Dict[str, Any]]:
        """
        Adds a stroke to the history and returns a frustration dict
        if a pattern is detected, otherwise None.
        """
        now = time.time()
        self.strokes.append((now, stroke))

        # Clean up old history
        while self.strokes and self.strokes[0][0] < now - self.window_seconds:
            self.strokes.popleft()

        eraser_count = 0
        short_pen_count = 0
        pen_count = 0

        for ts, s in self.strokes:
            if s.get('tool') == 'eraser':
                eraser_count += 1
            else:
                pen_count += 1
                points = s.get('points', [])
                if len(points) < 8:
                    short_pen_count += 1

        return self._detect_pattern(eraser_count, short_pen_count, pen_count)

    def _detect_pattern(
        self, eraser_count: int, short_pen_count: int, pen_count: int
    ) -> Optional[Dict[str, Any]]:
        """
        Detects frustration patterns and returns an appropriate message.
        """
        # Global cooldown
        now = time.time()
        if now - self.last_intervention_time < self.intervention_cooldown:
            return None

        # Pattern 1: many erasures = high frustration
        if eraser_count >= 6:
            self.last_intervention_time = now
            return {
                "type": "frustration",
                "level": "high",
                "reason": "many_erasers",
                "message": (
                    "I see you've erased several times. "
                    "Let me give you a hint: try breaking the problem into smaller steps."
                ),
            }

        # Pattern 2: very short strokes = hesitation
        if short_pen_count >= 8:
            self.last_intervention_time = now
            return {
                "type": "hesitation",
                "level": "medium",
                "reason": "many_short_strokes",
                "message": (
                    "You seem to be hesitating. Take your time, and remember: "
                    "every mistake is a step toward understanding."
                ),
            }

        # Pattern 3: erasures + rewriting = blocking
        if eraser_count >= 3 and pen_count >= 3 and short_pen_count >= 4:
            self.last_intervention_time = now
            return {
                "type": "rewrite",
                "level": "medium",
                "reason": "rewrite_after_erase",
                "message": (
                    "I noticed you're rewriting the same part. "
                    "Would you like a hint to get unstuck?"
                ),
            }

        return None

    def reset(self):
        """Resets the stroke history."""
        self.strokes.clear()
