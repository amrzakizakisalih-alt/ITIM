"""
ActR – Main Cognitive Architecture.

Orchestrates the ITS triad:
  • MathExpert        (symbolic resolution & buggy rules)
  • StudentModel      (declarative memory, knowledge tracing & behavioral indicators)

Provides a unified view of cognitive load and error patterns.
"""

from typing import Dict, Any, Optional
from domain.math.math_expert import MathExpert
from domain.cognitive.student_model import StudentModel


class ActR:
    """
    Simplified ACT-R cognitive engine for ITIM.
    """

    def __init__(self, math_expert: MathExpert):
        if math_expert is None:
            raise ValueError("ActR requires a MathExpert instance")
        self.mathExpert = math_expert
        self.studentModel = StudentModel()

        # Decision parameters
        self.intervention_cooldown = 20.0  # seconds between two interventions
        self.last_intervention_time = 0.0

    # ── Update cycle ────────────────────────────────────────────────────────

    def update(self, message: dict):
        """
        Called on every incoming message (stroke, user_message, etc.).
        Updates all sub-models.
        """
        # Behavioral logging in StudentModel
        msg_type = message.get("type", "unknown")
        tool = message.get("tool", "pen")
        self.studentModel.record_action(
            action_type=tool if msg_type == "stroke" else msg_type,
            metadata=message,
        )

    async def process_math(self, latex_str: str) -> Dict[str, Any]:
        """
        Complete mathematical pipeline: AST + buggy rule diagnostic.
        Only triggers buggy rule detection on text that clearly looks
        like a mathematical expression (presence of LaTeX symbols or
        mathematical operators).
        """
        # Quick heuristic: ignore pure conversational text
        looks_like_math = bool(
            latex_str
            and any(c in latex_str for c in r"\=+-*/^_{}[]$")
            and len(latex_str) < 500
        )

        ast = self.mathExpert.getAST(latex_str)

        if not looks_like_math:
            return {
                "ast": ast,
                "buggy_rule": None,
                "buggy_description": None,
                "buggy_source": None,
            }

        buggy = await self.mathExpert.detect_buggy_rule_async(latex_str)
        return {
            "ast": ast,
            "buggy_rule": buggy["name"] if buggy else None,
            "buggy_description": buggy["description"] if buggy else None,
            "buggy_source": buggy.get("source") if buggy else None,
        }

    async def evaluate_answer(self, user_latex: str, correct_latex: str) -> Dict[str, Any]:
        """
        Evaluates the learner's answer against the reference solution.
        Updates the StudentModel accordingly.
        """
        result = await self.mathExpert.compare_steps_async(user_latex, correct_latex)
        match = result.get("match", False)

        # Update knowledge tracing (generic "algebra" chunk for the example)
        self.studentModel.update_competence("algebra", success=match, amount=1.5)

        # If a buggy rule is detected, create a specific chunk
        if result.get("buggy_rule"):
            self.studentModel.update_competence(
                f"buggy_{result['buggy_rule']}", success=False, amount=0.5
            )

        return result

    # ── Cognitive monitoring ────────────────────────────────────────────────

    def monitorCognitiveLoad(self) -> Dict[str, Any]:
        """
        Evaluates the learner's overall cognitive load by combining:
          • inactivity & frustration (StudentModel)
          • chunk activation levels (StudentModel)
          • perceived mathematical difficulty (MathExpert)

        Returns a dict with 'level', 'should_intervene', 'hint_type'.
        """
        load = {
            "level": "low",
            "should_intervene": False,
            "hint_type": None,
            "details": {},
        }

        # 1. Behavioral evaluation (StudentModel)
        cog_state = self.studentModel.assess_cognitive_load()
        load["details"]["student_model"] = cog_state

        # 2. Check behavioral thresholds
        engine_intervention = self.studentModel.check_intervention()
        load["details"]["engine_intervention"] = engine_intervention

        # 3. Global decision
        level = cog_state["level"]
        if engine_intervention:
            level = "high"
            load["should_intervene"] = True
            load["hint_type"] = "direct_help"
        elif level == "high":
            load["should_intervene"] = True
            load["hint_type"] = "simplify_or_oral"
        elif level == "medium":
            load["should_intervene"] = True
            load["hint_type"] = "subtle_hint"

        load["level"] = level
        return load

    def get_student_profile(self) -> Dict[str, Any]:
        """Returns a summary of the learner's profile."""
        return {
            "chunks": {
                name: {
                    "activation": chunk.current_activation(),
                    "successes": chunk.success_count,
                    "failures": chunk.failure_count,
                }
                for name, chunk in self.studentModel.chunks.items()
            },
            "cognitive_load": self.studentModel.assess_cognitive_load(),
        }
