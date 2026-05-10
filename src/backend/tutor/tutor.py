"""
Tutor – Main Pedagogical Model (LLM-ready version).

Orchestrates the PedagogicalAgent (decisions) and the DialogueManager (context).
Communicates with the ActR to obtain the cognitive and mathematical state of
the learner, then formulates the responses to send to the interface.
"""

from typing import Dict, Any, List, Optional
from domain.cognitive.act_r import ActR
from domain.cognitive.pedagogical_agent import PedagogicalAgent
from domain.cognitive.dialogue_manager import DialogueManager
from core.llm_client import LLMClient


class Tutor:
    """
    ITIM intelligent tutor.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.pedagogicalAgent = PedagogicalAgent(llm_client=llm_client)
        self.dialogueManager = DialogueManager()
        self.actR: Optional[ActR] = None
        self.last_proposed_exercises: List[Dict[str, Any]] = []
        self.current_exercise: Optional[Dict[str, Any]] = None
        self.last_seen_latex: Optional[str] = None

    def bind_actr(self, actr: ActR):
        """Binds the tutor to an ACT-R engine (called on WebSocket connection)."""
        self.actR = actr

    # ── Interaction cycles ──────────────────────────────────────────────────

    @staticmethod
    def _parse_exercise_control(text: str) -> Optional[str]:
        """
        Detects exercise control commands.
        Returns 'next_step', 'give_up', 'restart', 'easier', 'recap', or None.
        """
        t = text.lower().strip()
        if any(x in t for x in ["étape suivante", "next step", "skip", "passer", "je veux la suite"]):
            return "next_step"
        if any(x in t for x in ["abandonne", "give up", "j'abandonne", "laisse tomber", "stop exercice", "arrête"]):
            return "give_up"
        if any(x in t for x in ["recommence", "restart", "from the top", "depuis le début"]):
            return "restart"
        if any(x in t for x in ["facile", "easier", "plus facile", "simpler", "downgrade"]):
            return "easier"
        if any(x in t for x in ["rappelle", "recap", "énoncé", "problem", "quelle est la question", "rappelle-moi"]):
            return "recap"
        return None

    @staticmethod
    def _parse_help_request(text: str) -> Optional[str]:
        """
        Detects whether the user is asking for a hint or the answer.
        Returns 'hint', 'answer', or None.
        """
        t = text.lower().strip()
        hint_words = ["indice", "hint", "aide", "help", "je bloque", "stuck", "don't know", "sais pas", "comprends pas"]
        answer_words = ["réponse", "answer", "solution", "montre", "show me", "donne la solution", "corrige"]
        if any(h in t for h in hint_words):
            return "hint"
        if any(a in t for a in answer_words):
            return "answer"
        return None

    @staticmethod
    def _parse_exercise_response(text: str) -> Optional[Dict[str, Any]]:
        """
        Analyzes user text to see whether they accept / reject / want a harder
        exercise proposal.

        Returns
        -------
        {"action": "accept", "index": int}
        {"action": "reject"}
        {"action": "harder"}
        None  → not a response to an exercise proposal
        """
        t = text.lower().strip()

        # ── Rejection ────────────────────────────────────────────────────
        rejections = ["non", "no", "nope", "non merci", "pas maintenant", "plus tard", "skip"]
        if any(r in t for r in rejections):
            return {"action": "reject"}

        # ── Increase difficulty ──────────────────────────────────────────
        harder_phrases = ["plus difficile", "harder", "augmente", "next level", "more difficult", "niveau sup"]
        if any(h in t for h in harder_phrases):
            return {"action": "harder"}

        # ── Acceptance with number ───────────────────────────────────────
        generic_yes = ["oui", "yes", "ok", "d'accord", "volontiers", "bien sûr", "pourquoi pas", "allons-y"]
        has_yes = any(y in t for y in generic_yes)

        # Explicit numeric references
        if any(x in t for x in ["premier", "first", "1er", "1 ", "#1"]):
            return {"action": "accept", "index": 0}
        if any(x in t for x in ["deuxième", "second", "2e", "2 ", "#2"]):
            return {"action": "accept", "index": 1}
        if any(x in t for x in ["troisième", "third", "3e", "3 ", "#3"]):
            return {"action": "accept", "index": 2}

        # Generic positive response → first exercise by default
        if has_yes:
            return {"action": "accept", "index": 0}

        return None

    async def on_user_message(self, text: str) -> Dict[str, Any]:
        """
        Processes a text message from the learner.
        Returns the tutor's response.
        """
        self.dialogueManager.add_message("user", text)

        # ── Detect response to an exercise proposal ──────────────────────
        if self.last_proposed_exercises:
            resp = self._parse_exercise_response(text)
            if resp:
                action = resp["action"]

                if action == "accept":
                    idx = resp["index"]
                    if 0 <= idx < len(self.last_proposed_exercises):
                        ex = self.last_proposed_exercises[idx]
                        self.last_proposed_exercises = []  # reset after acceptance
                        confirm = (
                            f"📝 Great! Let's work on **{ex.get('concept', 'exercise').replace('_', ' ')}** "
                            f"({ex.get('difficulty', '')}).\n\n"
                            f"Problem: {ex['problem_latex']}\n\n"
                            f"Show me step 1."
                        )
                        self.dialogueManager.add_message("assistant", confirm)
                        return {
                            "type": "exercise_accepted",
                            "exercise": ex,
                            "text": confirm,
                            "role": "assistant",
                        }

                elif action == "reject":
                    self.last_proposed_exercises = []
                    text_resp = "No problem! Let me suggest something else. 🔄"
                    self.dialogueManager.add_message("assistant", text_resp)
                    return {
                        "type": "exercise_rejected",
                        "text": text_resp,
                        "role": "assistant",
                    }

                elif action == "harder":
                    text_resp = "Challenge accepted! 💪 Here are harder versions."
                    self.dialogueManager.add_message("assistant", text_resp)
                    return {
                        "type": "exercise_harder",
                        "text": text_resp,
                        "role": "assistant",
                    }

        # ── Exercise control (next step / give up) ───────────────────────
        control = self._parse_exercise_control(text)
        if control:
            return {
                "type": f"{control}_request",
                "role": "assistant",
            }

        # ── Help request (hint / answer) on active or proposed exercise ──
        help_type = self._parse_help_request(text)
        if help_type:
            return {
                "type": f"{help_type}_request",
                "role": "assistant",
            }

        math_info = {}
        cog_load = {"level": "low", "should_intervene": False}
        profile = {}

        if self.actR:
            math_info = await self.actR.process_math(text)
            cog_load = self.actR.monitorCognitiveLoad()
            profile = self.actR.get_student_profile()

        # Always reply via the conversational LLM to maintain a consistent
        # voice. Diagnostics (buggy rule / cognitive load) are injected into
        # the system context instead of short-circuiting the flow.
        llm = self.pedagogicalAgent.llm
        has_buggy = math_info.get("buggy_rule") is not None
        is_high_load = cog_load.get("level") == "high"

        if llm and llm.is_available():
            context = self.dialogueManager.get_context(n_last=12)

            extra_context = ""

            # Context of the current exercise
            if self.current_exercise:
                ex = self.current_exercise
                extra_context += (
                    f"\n\n[CONTEXT] The student is currently working on this exercise:\n"
                    f"Problem: {ex.get('problem_latex', 'N/A')}\n"
                    f"Concept: {ex.get('concept', 'math')}\n"
                    f"Difficulty: {ex.get('difficulty', 'unknown')}\n"
                    f"Stay focused on this problem. If the student asks something unrelated, gently bring them back to the exercise."
                )

            if self.last_seen_latex:
                extra_context += (
                    f"\n\n[INTERNAL NOTE] The student recently wrote this on the board: `{self.last_seen_latex}`. "
                    f"Refer to it naturally if it helps answer their question."
                )

            if has_buggy:
                extra_context += (
                    f"\n\n[INTERNAL NOTE] The student's last input may contain a common misconception: "
                    f"{math_info['buggy_rule']} ({math_info.get('buggy_description', '')}). "
                    f"If relevant, gently guide them. If their input is actually correct, simply acknowledge it."
                )
            if is_high_load:
                extra_context += (
                    "\n\n[INTERNAL NOTE] The student shows high cognitive load. "
                    "Be supportive, break down explanations, and offer simpler hints."
                )

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are ITIM, a helpful and friendly math tutor. "
                        "Respond to the student clearly and concisely. "
                        "If they greet you, greet them back warmly. "
                        "If they ask a math question, guide them step by step without giving the full answer immediately."
                        + extra_context
                    ),
                },
                *context,
            ]
            response_text = await llm.generate(
                "",
                messages=messages,
            )
        else:
            # Static fallback if no LLM is available
            if has_buggy:
                response_text = (
                    f"I noticed a possible issue: {math_info['buggy_rule']}. "
                    f"{math_info.get('buggy_description', '')}"
                )
            elif is_high_load:
                response_text = (
                    "You seem to be working hard. Let's take a step back. "
                    "Would you like a simpler hint?"
                )
            else:
                response_text = (
                    "I'm here to help! Feel free to write or speak your math problem."
                )

        self.dialogueManager.add_message("assistant", response_text)

        return {
            "type": "tutor_message",
            "text": response_text,
            "role": "assistant",
            "intervention_type": "conversation",
            "action": None,
        }

    async def on_stroke_intervention(self, step_tracker_active: bool = False) -> Optional[Dict[str, Any]]:
        """
        Called periodically by the intervention loop.
        Checks whether a proactive tutor message is needed.
        """
        if not self.actR:
            return None

        cog_load = self.actR.monitorCognitiveLoad()
        if not cog_load.get("should_intervene"):
            return None

        # If no exercise is active and load is only medium,
        # we don't send a specific math hint
        if not step_tracker_active and cog_load.get("level") == "medium":
            return None

        decision = await self.pedagogicalAgent.decide_intervention(
            cognitive_load=cog_load,
            math_diagnostic=None,
            student_profile=self.actR.get_student_profile(),
            exercise_context=self.current_exercise,
        )

        if decision["type"] == "none":
            return None

        self.dialogueManager.add_message("assistant", decision["message"], metadata=decision)

        return {
            "type": "tutor_message",
            "text": decision["message"],
            "role": "assistant",
            "intervention_type": decision["type"],
            "action": decision["action"],
        }

    async def on_math_submission(self, user_latex: str, correct_latex: str) -> Dict[str, Any]:
        """
        Evaluates a mathematical answer from the learner.
        """
        if not self.actR:
            return {
                "type": "tutor_message",
                "text": "[Tutor not initialized]",
                "role": "assistant",
            }

        result = await self.actR.evaluate_answer(user_latex, correct_latex)

        if result["match"]:
            text = "✅ Correct! Well done."
            self.pedagogicalAgent.reset()
        else:
            decision = await self.pedagogicalAgent.decide_intervention(
                cognitive_load=self.actR.monitorCognitiveLoad(),
                math_diagnostic=result,
                student_profile=self.actR.get_student_profile(),
            )
            text = decision["message"] or result.get("hint", "Let's review this step.")

        self.dialogueManager.add_message("assistant", text, metadata=result)

        return {
            "type": "tutor_message",
            "text": text,
            "role": "assistant",
            "diagnostic": result,
        }

    def set_current_exercise(self, exercise: Optional[Dict[str, Any]]):
        """Updates the current exercise for the LLM context."""
        self.current_exercise = exercise

    def reset_session(self):
        """Resets the tutor for a new session."""
        self.pedagogicalAgent.reset()
        self.dialogueManager.reset()
        self.current_exercise = None
        self.last_proposed_exercises.clear()

    async def propose_exercises(self, exercises: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Asks the user whether they want to practice on the exercises
        detected in an imported document.
        """
        if not exercises:
            return {
                "type": "tutor_message",
                "text": "I couldn't find any verifiable exercises in this document.",
                "role": "assistant",
            }

        concepts = [ex.get("concept", "unknown").replace("_", " ") for ex in exercises]
        concepts_str = ", ".join(concepts)
        count = len(exercises)

        text = (
            f"📄 I found **{count} exercise{'s' if count > 1 else ''}** in your document "
            f"covering: *{concepts_str}*.\n\n"
            f"Would you like to practice on one of them? Click an exercise below to start!"
        )

        self.last_proposed_exercises = list(exercises)
        self.dialogueManager.add_message("assistant", text, metadata={"action": "propose_exercises", "exercises": exercises})

        return {
            "type": "tutor_message",
            "text": text,
            "role": "assistant",
            "intervention_type": "exercise_proposal",
            "exercises": exercises,
        }

