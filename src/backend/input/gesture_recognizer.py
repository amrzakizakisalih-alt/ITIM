"""
GestureRecognizer – Detection of handwritten communication gestures.

Analyzes strokes to recognize drawn symbols:
  • Check mark (✓)         → "Check my answer"
  • Question mark (?)      → "I need a hint"

Detection relies on simple geometric heuristics
(distances, angles, directions) rather than heavy ML.
"""

import math
import time
from typing import List, Dict, Optional, Tuple


def distance(p1: Dict[str, float], p2: Dict[str, float]) -> float:
    return math.hypot(p1["x"] - p2["x"], p1["y"] - p2["y"])


def centroid(points: List[Dict[str, float]]) -> Tuple[float, float]:
    n = len(points)
    return sum(p["x"] for p in points) / n, sum(p["y"] for p in points) / n


def bounding_box(points: List[Dict[str, float]]) -> Tuple[float, float, float, float]:
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


class GestureRecognizer:
    """
    Recognizes hand-drawn gestures.
    """

    GESTURE_MEANINGS = {
        "check": "Check my answer",
        "question": "I need a hint",
    }

    def __init__(self):
        self._buffer: List[Dict[str, any]] = []
        self._last_gesture: Optional[str] = None
        self._last_gesture_time: float = 0.0
        self.MULTI_STROKE_WINDOW = 0.8   # seconds
        self.DEBOUNCE_TIME = 1.5         # seconds

    def feed_stroke(self, stroke: dict) -> Optional[str]:
        """
        Temporal stroke accumulator.
        Returns a recognized gesture (mono or multi-strokes) or None.
        """
        now = time.time()

        # Clean up strokes that are too old
        self._buffer = [
            item for item in self._buffer
            if now - item["timestamp"] < self.MULTI_STROKE_WINDOW
        ]

        self._buffer.append({"stroke": stroke, "timestamp": now})

        # 1. Try multi-stroke recognition if we have several
        if len(self._buffer) > 1:
            merged_points = []
            for item in self._buffer:
                merged_points.extend(item["stroke"].get("points", []))
            merged_stroke = {"points": merged_points}
            gesture = self.recognize(merged_stroke)
            if gesture and self._not_debounced(gesture, now):
                self._last_gesture = gesture
                self._last_gesture_time = now
                return gesture

        # 2. Mono-stroke fallback
        gesture = self.recognize(stroke)
        if gesture and self._not_debounced(gesture, now):
            self._last_gesture = gesture
            self._last_gesture_time = now
            return gesture

        return None

    def _not_debounced(self, gesture: str, now: float) -> bool:
        """Avoids returning the same gesture too frequently."""
        if gesture == self._last_gesture and (now - self._last_gesture_time) < self.DEBOUNCE_TIME:
            return False
        return True

    def reset_accumulator(self):
        """Empties the accumulated stroke buffer."""
        self._buffer.clear()

    def recognize(self, stroke: dict) -> Optional[str]:
        """
        Analyzes a stroke and returns the recognized gesture or None.
        """
        points = stroke.get("points", [])
        if len(points) < 8:
            return None

        
        if self._is_check(points):
            return "check"
       
        if self._is_question(points):
            return "question"
        return None

    def get_response(self, gesture: str) -> Dict[str, str]:
        """Returns the pedagogical response associated with the gesture."""
        return {
            "type": "gesture_response",
            "gesture": gesture,
            "meaning": self.GESTURE_MEANINGS.get(gesture, ""),
        }

    # ── Individual Detectors ────────────────────────────────────────────────



    def _is_check(self, points: List[Dict[str, float]]) -> bool:
        """
        Detects a check mark (✓):
          - Two main segments forming an acute angle downward
          - The central point (vertex of the V) is lower than both ends
        """
        if len(points) < 10:
            return False

        # Find the lowest point (vertex of the V)
        lowest_idx = min(range(len(points)), key=lambda i: points[i]["y"])
        lowest = points[lowest_idx]

        # There must be points before and after
        if lowest_idx < 3 or lowest_idx > len(points) - 4:
            return False

        left = points[0]
        right = points[-1]

        # The vertex must be below both edges
        if lowest["y"] <= max(left["y"], right["y"]):
            return False

        # The edges must be sufficiently spaced horizontally
        if abs(left["x"] - right["x"]) < 30:
            return False

        # Angle at the vertex: must be acute (< 90°)
        v1 = (left["x"] - lowest["x"], left["y"] - lowest["y"])
        v2 = (right["x"] - lowest["x"], right["y"] - lowest["y"])
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        mag1 = math.hypot(*v1)
        mag2 = math.hypot(*v2)
        if mag1 == 0 or mag2 == 0:
            return False
        angle = math.acos(max(-1, min(1, dot / (mag1 * mag2))))
        return angle < math.radians(100)

   

    def _is_question(self, points: List[Dict[str, float]]) -> bool:
        """
        Detects a simplified question mark:
          - A loop at the top (like a miniature circle)
          - Followed by a vertical stroke downward
        """
        if len(points) < 12:
            return False

        min_x, min_y, max_x, max_y = bounding_box(points)
        h = max_y - min_y
        if h < 50:
            return False

        # Split into two regions: top (loop) and bottom (stroke)
        split_y = min_y + h * 0.55
        top_points = [p for p in points if p["y"] < split_y]
        bottom_points = [p for p in points if p["y"] >= split_y]

        if len(top_points) < 6 or len(bottom_points) < 4:
            return False

        # The top must look like a closed loop
        if distance(top_points[0], top_points[-1]) > 15:
            return False

        # The bottom must be approximately vertical
        dx = bottom_points[-1]["x"] - bottom_points[0]["x"]
        dy = bottom_points[-1]["y"] - bottom_points[0]["y"]
        if abs(dy) < 10:
            return False
        # More vertical than horizontal
        return abs(dy) > abs(dx) * 1.5
