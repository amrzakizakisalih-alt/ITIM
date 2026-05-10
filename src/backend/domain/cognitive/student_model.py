"""
StudentModel – Learner model (ACT-R declarative memory simulation).

Each mathematical skill is a 'chunk' with a dynamic activation
level. The model uses simplified Knowledge Tracing to simulate
learning and forgetting, and analyzes behavioral indicators
to estimate cognitive load.
"""

import time
import math
from typing import Dict, List, Optional


class Chunk:
    """Represents a unit of knowledge in the ACT-R declarative memory."""

    def __init__(self, name: str, initial_activation: float = 0.0):
        self.name = name
        self.activation = initial_activation
        self.last_accessed = time.time()
        self.success_count = 0
        self.failure_count = 0

    def boost(self, amount: float = 1.0):
        """Strengthens activation after a success."""
        self.activation += amount
        self.success_count += 1
        self.last_accessed = time.time()

    def decay(self, amount: float = 0.5):
        """Decreases activation after a failure or through forgetting."""
        self.activation = max(0.0, self.activation - amount)
        self.failure_count += 1
        self.last_accessed = time.time()

    def current_activation(self) -> float:
        """
        Computes the current activation with temporal decay
        (simplified power law of forgetting).
        """
        elapsed = time.time() - self.last_accessed
        decay_factor = math.exp(-0.05 * elapsed)
        return self.activation * decay_factor


class StudentModel:
    """
    Maintains a dynamic state of the user's skills.
    """

    def __init__(self):
        self.chunks: Dict[str, Chunk] = {}
        # Behavioral indicators for cognitive load
        self.behavioral_history: List[dict] = []
        self.eraser_count = 0
        self.idle_time = 0.0
        self.last_action_time = time.time()
        self.session_start_time = time.time()
        self.has_started = False  # True after the first real action

        # Thresholds for proactive intervention detection
        self.inactivity_threshold = 20  # seconds
        self.eraser_threshold = 6
        self.last_intervention_time = 0.0
        self.intervention_cooldown = 15  # seconds between two interventions

    # ── Chunk management ────────────────────────────────────────────────────

    def add_chunk(self, name: str, initial_activation: float = 0.0):
        """Adds a new skill (chunk) to the model."""
        if name not in self.chunks:
            self.chunks[name] = Chunk(name, initial_activation)

    def update_competence(self, name: str, success: bool, amount: float = 1.0):
        """
        Updates a chunk's activation based on the learner's result.
        Simplified Knowledge Tracing.
        """
        if name not in self.chunks:
            self.add_chunk(name, 0.0)
        chunk = self.chunks[name]
        if success:
            chunk.boost(amount)
        else:
            chunk.decay(amount)

    def get_activation(self, name: str) -> float:
        """Returns the current activation level of a chunk."""
        chunk = self.chunks.get(name)
        return chunk.current_activation() if chunk else 0.0

    # ── Behavioral indicators ───────────────────────────────────────────────

    def record_action(self, action_type: str, metadata: dict = None):
        """Records a user action for behavioral analysis."""
        now = time.time()
        self.idle_time = now - self.last_action_time
        self.last_action_time = now

        if not self.has_started and action_type in ("stroke", "user_message", "math_submit"):
            self.has_started = True

        entry = {
            "type": action_type,
            "timestamp": now,
            "idle_time": self.idle_time,
            "metadata": metadata or {},
        }
        self.behavioral_history.append(entry)

        if action_type == "eraser":
            self.eraser_count += 1
        elif action_type == "stroke":
            # a normal stroke slightly reduces the frustration counter
            self.eraser_count = max(0, self.eraser_count - 0.3)

    def is_in_flow(self) -> bool:
        """
        Detects whether the user is in 'writing flow'
        (> 4 strokes in the last 10 seconds).
        In flow, we avoid interrupting.
        """
        now = time.time()
        recent_strokes = [
            a for a in self.behavioral_history[-30:]
            if a["type"] == "stroke" and now - a["timestamp"] < 10
        ]
        return len(recent_strokes) >= 4

    def assess_cognitive_load(self) -> dict:
        """
        Evaluates the current cognitive load from behavioral
        indicators. Returns a dict with 'level' and 'indicators'.
        """
        indicators = {}
        now = time.time()

        # 0. Grace period: no intervention before the user has started
        # or within the first 45 seconds of the session
        if not self.has_started or (now - self.session_start_time < 45):
            return {
                "level": "low",
                "indicators": {"grace_period": True},
                "recommendation": "Continue observing (session just started).",
            }

        # 0b. Writing flow → no intervention
        if self.is_in_flow():
            return {
                "level": "low",
                "indicators": {"flow": True},
                "recommendation": "Continue observing (user in flow).",
            }

        # 1. Idle time
        current_idle = now - self.last_action_time
        indicators["idle_time"] = current_idle
        idle_stress = current_idle > 20

        # 2. Eraser frequency (cross-outs)
        indicators["eraser_count"] = self.eraser_count
        frustration = self.eraser_count > 6

        # 3. Number of recent actions (drop = possible blockage)
        recent_actions = [
            a for a in self.behavioral_history[-20:]
            if now - a["timestamp"] < 60
        ]
        indicators["recent_actions"] = len(recent_actions)
        low_activity = len(recent_actions) < 3

        # Determine the cognitive load level
        if frustration and idle_stress:
            level = "high"
        elif frustration or idle_stress or low_activity:
            level = "medium"
        else:
            level = "low"

        return {
            "level": level,
            "indicators": indicators,
            "recommendation": self._recommendation(level),
        }

    def _recommendation(self, level: str) -> str:
        if level == "high":
            return "Simplify interface or switch to oral mode."
        if level == "medium":
            return "Offer a subtle hint."
        return "Continue observing."

    def check_intervention(self) -> Optional[dict]:
        """
        Checks whether a critical threshold is exceeded.
        Returns an intervention message or None.
        """
        now = time.time()

        # No intervention before the user has started or within the first 45 seconds
        if not self.has_started or (now - self.session_start_time < 45):
            return None

        idle_time = now - self.last_action_time

        # Global cooldown between interventions
        if now - self.last_intervention_time < self.intervention_cooldown:
            return None

        if idle_time > self.inactivity_threshold:
            self.last_intervention_time = now
            return {
                "type": "tutor_message",
                "text": "You seem to be thinking a lot. Do you need some help?",
                "role": "assistant",
            }

        if self.eraser_count >= self.eraser_threshold:
            self.last_intervention_time = now
            self.eraser_count = 0
            return {
                "type": "tutor_message",
                "text": "You seem to be a little bit frustrated. Do you need some help?",
                "role": "assistant",
            }

        return None

    def reset_behavioral_counters(self):
        """Resets the session's behavioral counters."""
        self.last_action_time = time.time()
        self.eraser_count = 0
        self.idle_time = 0.0
        self.behavioral_history.clear()
        self.last_intervention_time = 0.0
        self.session_start_time = time.time()
        self.has_started = False

