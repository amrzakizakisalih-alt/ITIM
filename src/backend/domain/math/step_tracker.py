"""
StepTracker – Real-time tracking of solution steps.

When an exercise is active, StepTracker compares the recognized LaTeX
(from the user's strokes) with the current expected step.
It intervenes immediately in case of partial error (buggy rule) or
correct completion of a step.
"""

from typing import Dict, Any, Optional, List
from domain.math.math_expert import MathExpert


class StepTracker:
    """
    Accompanies the student step by step during exercise resolution.
    """

    def __init__(self, math_expert: MathExpert):
        self.math_expert = math_expert
        self.reset()

    def reset(self):
        """Abandons the active exercise."""
        self.active = False
        self.exercise = None
        self.expected_steps: List[str] = []
        self.current_step = 0
        self.completed = False
        self.last_user_latex = ""

    def set_exercise(self, exercise: Dict[str, Any]):
        """
        Activates tracking for a new exercise.

        Parameters
        ----------
        exercise : dict
            Must contain at least 'problem_latex', 'correct_latex',
            and optionally 'steps' (list of LaTeX steps).
        """
        self.reset()
        self.exercise = exercise

        # If steps are provided by the ExerciseGenerator, we use them
        raw_steps = exercise.get("steps", [])

        # Otherwise, we generate steps with MathExpert
        if not raw_steps and exercise.get("problem_latex"):
            generated = self.math_expert.solveStepByStep(exercise["problem_latex"])
            raw_steps = generated if generated else [exercise["correct_latex"]]

        # Cleanup: keep only pure LaTeX parts
        self.expected_steps = self._clean_steps(raw_steps)
        if not self.expected_steps:
            self.expected_steps = [exercise.get("correct_latex", "")]

        self.active = True
        self.current_step = 0

    # ── Real-time verification ──────────────────────────────────────────────

    async def check_steps(self, candidate_latex_list: List[str]) -> Optional[Dict[str, Any]]:
        """
        Tests several LaTeX candidates and returns the first one that matches
        the expected step, or the best available feedback.
        """
        if not self.active or self.completed:
            return None

        if self.current_step >= len(self.expected_steps):
            self.completed = True
            return self._make_response("completed", "🎉 Exercise completed! Well done.")

        expected = self.expected_steps[self.current_step]

        seen = set()
        best_feedback = None
        first_latex = None

        for latex in candidate_latex_list:
            latex = latex.strip()
            if not latex or latex in seen:
                continue
            seen.add(latex)
            if first_latex is None:
                first_latex = latex

            comparison = await self.math_expert.compare_steps_async(latex, expected)

            if comparison["match"]:
                self.current_step += 1
                self.last_user_latex = latex
                if self.current_step >= len(self.expected_steps):
                    self.completed = True
                    return self._make_response(
                        "completed",
                        "🎉 Exercise completed! Well done.",
                        {"total_steps": len(self.expected_steps)},
                    )
                return self._make_response(
                    "correct_step",
                    f"✅ Step {self.current_step} correct! Continue to the next step.",
                    {
                        "step_index": self.current_step,
                        "next_step": self.expected_steps[self.current_step],
                        "total_steps": len(self.expected_steps),
                    },
                )

            if comparison.get("buggy_rule"):
                self.last_user_latex = latex
                return self._make_response(
                    "buggy_detected",
                    f"⚠️ Careful! {comparison.get('hint', 'There is a common mistake here.')}",
                    {
                        "buggy_rule": comparison["buggy_rule"],
                        "expected": expected,
                        "step_index": self.current_step,
                    },
                )

            if best_feedback is None:
                best_feedback = self._make_response(
                    "incorrect",
                    f"❌ Not quite right for step {self.current_step + 1}. "
                    f"Hint: {self.exercise.get('hint', 'Check your calculation carefully.')}",
                    {
                        "expected": expected,
                        "step_index": self.current_step,
                    },
                )

        if best_feedback and first_latex:
            self.last_user_latex = first_latex

        return best_feedback

    def skip_step(self) -> Optional[Dict[str, Any]]:
        """
        Skips the current step without verification (the user asks to see
        the solution and move forward).
        """
        if not self.active or self.completed:
            return None

        if self.current_step >= len(self.expected_steps):
            self.completed = True
            return self._make_response("completed", "🎉 Exercise completed! Well done.")

        skipped = self.expected_steps[self.current_step]
        self.current_step += 1

        if self.current_step >= len(self.expected_steps):
            self.completed = True
            return self._make_response(
                "completed",
                f"✅ Step solution: ${skipped}$\n\n🎉 Exercise completed! Well done.",
                {"total_steps": len(self.expected_steps)},
            )

        return self._make_response(
            "step_skipped",
            f"✅ Step solution: ${skipped}$\n\nNext step: show me ${self.expected_steps[self.current_step]}$",
            {
                "step_index": self.current_step,
                "next_step": self.expected_steps[self.current_step],
                "total_steps": len(self.expected_steps),
            },
        )

    def get_progress(self) -> Dict[str, Any]:
        """Returns the current progress."""
        return {
            "active": self.active,
            "completed": self.completed,
            "current_step": self.current_step,
            "total_steps": len(self.expected_steps),
            "percent": (self.current_step / len(self.expected_steps) * 100) if self.expected_steps else 0,
        }

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _clean_steps(self, raw_steps: List[str]) -> List[str]:
        """Extracts pure LaTeX from a list of textual steps.
        Deduplicates identical consecutive steps."""
        clean = []
        for step in raw_steps:
            # Look for content between $...$ or just take the end after :
            candidate = None
            if "$" in step:
                parts = step.split("$")
                # We take the first part between $ that looks like latex
                for i in range(1, len(parts)):
                    c = parts[i].strip()
                    if c and len(c) > 1:
                        candidate = c
                        break
            else:
                # If no $, we take everything except the numbered prefix
                s = step.strip()
                if "." in s[:5]:
                    s = s.split(".", 1)[1].strip()
                if s:
                    candidate = s

            if candidate:
                # Avoid consecutive duplicates
                if not clean or clean[-1] != candidate:
                    clean.append(candidate)
        return clean

    def _make_response(self, status: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        return {
            "type": "step_feedback",
            "status": status,
            "text": text,
            "role": "assistant",
            "metadata": metadata or {},
        }
