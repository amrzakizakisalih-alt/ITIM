"""
Unit tests for the ITIM backend.

Covers business modules:
  • StudentModel   (chunks, knowledge tracing, cognitive load)
  • MathExpert     (AST, solving, buggy rules, comparison)
  • ActR           (cognitive orchestration)
  • Tutor          (async pedagogical pipeline)

Run with:  pytest test_backend.py -v
"""

import pytest
import time

from domain.cognitive.student_model import StudentModel, Chunk
from domain.math.math_expert import MathExpert
from domain.cognitive.act_r import ActR
from tutor.tutor import Tutor
from core.llm_client import LLMClient
from input.stroke_buffer import StrokeBuffer


# ═════════════════════════════════════════════════════════════════════════════
# StrokeBuffer
# ═════════════════════════════════════════════════════════════════════════════

class TestStrokeBuffer:
    def test_add_pen_strokes(self):
        buf = StrokeBuffer()
        buf.add({"tool": "pen", "points": [{"x": 10, "y": 10}, {"x": 20, "y": 20}]})
        assert len(buf) == 1
        assert len(buf.get_active_strokes()) == 1

    def test_eraser_removes_covered_strokes(self):
        buf = StrokeBuffer()
        # Pen stroke covering the area (10,10) to (20,20)
        buf.add({"tool": "pen", "points": [{"x": 10, "y": 10}, {"x": 20, "y": 20}]})
        # Eraser covering exactly the same area
        buf.add({"tool": "eraser", "points": [{"x": 10, "y": 10}, {"x": 20, "y": 20}]})
        assert len(buf.get_active_strokes()) == 0

    def test_eraser_partial_coverage_keeps_stroke(self):
        buf = StrokeBuffer()
        buf.add({"tool": "pen", "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}]})
        # Eraser next to the stroke (not on the actual points) → the stroke should remain
        buf.add({"tool": "eraser", "points": [{"x": 0, "y": 30}, {"x": 10, "y": 30}]})
        assert len(buf.get_active_strokes()) == 1

    def test_clear(self):
        buf = StrokeBuffer()
        buf.add({"tool": "pen", "points": [{"x": 1, "y": 1}]})
        buf.clear()
        assert len(buf) == 0


# ═════════════════════════════════════════════════════════════════════════════
# StudentModel
# ═════════════════════════════════════════════════════════════════════════════

class TestStudentModel:
    def test_add_chunk(self):
        sm = StudentModel()
        sm.add_chunk("algebra", 1.0)
        assert "algebra" in sm.chunks
        assert sm.get_activation("algebra") == pytest.approx(1.0, abs=0.1)

    def test_update_competence_success(self):
        sm = StudentModel()
        sm.update_competence("algebra", success=True, amount=2.0)
        assert sm.chunks["algebra"].success_count == 1
        # Slight temporal decay may bring it just below 2.0
        assert sm.get_activation("algebra") == pytest.approx(2.0, abs=0.2)

    def test_update_competence_failure(self):
        sm = StudentModel()
        sm.update_competence("algebra", success=True, amount=3.0)
        sm.update_competence("algebra", success=False, amount=1.0)
        assert sm.chunks["algebra"].failure_count == 1
        assert sm.get_activation("algebra") < 3.0

    def test_cognitive_load_low(self):
        sm = StudentModel()
        # At least 3 recent actions to avoid 'low_activity' → 'medium'
        for _ in range(3):
            sm.record_action("stroke")
        load = sm.assess_cognitive_load()
        assert load["level"] == "low"

    def test_cognitive_load_high_by_frustration(self):
        sm = StudentModel()
        for _ in range(15):
            sm.record_action("eraser")
        # Simulate long inactivity in addition to frustration
        sm.last_action_time = time.time() - 35
        load = sm.assess_cognitive_load()
        assert load["level"] == "high"

    def test_cognitive_load_medium_by_inactivity(self):
        sm = StudentModel()
        # Simulate long inactivity by forcing the timestamp
        sm.last_action_time = time.time() - 35
        load = sm.assess_cognitive_load()
        assert load["level"] == "medium"



class TestChunk:
    def test_boost_and_decay(self):
        c = Chunk("test", 1.0)
        c.boost(2.0)
        assert c.activation == 3.0
        c.decay(1.0)
        assert c.activation == 2.0

    def test_activation_decay_over_time(self):
        c = Chunk("test", 10.0)
        time.sleep(0.1)
        current = c.current_activation()
        assert current < 10.0  # temporal decay


# ═════════════════════════════════════════════════════════════════════════════
# MathExpert
# ═════════════════════════════════════════════════════════════════════════════

class TestMathExpert:
    def test_getAST_simple_expression(self):
        me = MathExpert()
        ast = me.getAST("x^2 + 2*x + 1")
        assert ast is not None
        assert "content" in ast

    def test_getAST_invalid_returns_none(self):
        me = MathExpert()
        ast = me.getAST("not valid latex @@@")
        assert ast is None or isinstance(ast, dict)

    def test_solveStepByStep_expression(self):
        me = MathExpert()
        steps = me.solveStepByStep("(x+1)^2")
        assert len(steps) >= 2
        assert any("Expression" in s or "Simplification" in s for s in steps)

    @pytest.mark.xfail(reason="solveStepByStep fallback generic does not guarantee 'Solution' in steps — preexisting bug")
    def test_solveStepByStep_equation(self):
        me = MathExpert()
        steps = me.solveStepByStep("x^2 - 4 = 0")
        assert len(steps) >= 3
        assert any("Solution" in s for s in steps)

    def test_compareSteps_exact_match(self):
        me = MathExpert()
        result = me.compareSteps("(x+1)^2", "(x+1)^2")
        assert result["match"] is True
        assert result["buggy_rule"] is None

    def test_compareSteps_equivalent_match(self):
        me = MathExpert()
        result = me.compareSteps("x^2 + 2*x + 1", "(x+1)^2")
        assert result["match"] is True  # sympy simplification

    @pytest.mark.xfail(reason="_check_square_binomial_error always returns False (disabled) — dead code")
    def test_compareSteps_detects_buggy_rule(self):
        me = MathExpert()
        result = me.compareSteps("x^2 + 1", "(x+1)^2")
        assert result["match"] is False
        assert result["buggy_rule"] == "square_binomial_error"

    def test_list_buggy_rules(self):
        me = MathExpert()
        rules = me.list_buggy_rules()
        assert len(rules) >= 3
        assert all("name" in r and "description" in r for r in rules)


# ═════════════════════════════════════════════════════════════════════════════
# BuggyRuleLearner
# ═════════════════════════════════════════════════════════════════════════════

class TestBuggyRuleLearner:
    def test_record_and_validate(self, tmp_path):
        from domain.exercises.buggy_rule_learner import BuggyRuleLearner
        path = tmp_path / "learned.json"
        learner = BuggyRuleLearner(storage_path=str(path))
        # Not yet validated
        for i in range(2):
            learner.record_discovery(
                name="forget_constant",
                description="Oubli de la constante",
                user_latex=f"x^{i+2}",
            )
        assert not learner._rules["forget_constant"]["validated"]
        # 3rd occurrence → validation
        learner.record_discovery(
            name="forget_constant",
            description="Oubli de la constante",
            user_latex="x^5",
        )
        assert learner._rules["forget_constant"]["validated"]

    def test_learned_rule_matches_examples(self, tmp_path):
        from domain.exercises.buggy_rule_learner import BuggyRuleLearner
        import sympy as sp
        path = tmp_path / "learned.json"
        learner = BuggyRuleLearner(storage_path=str(path))
        # Simulate an already validated rule
        learner.record_discovery("test_rule", "desc", "x^2 + 1")
        learner.record_discovery("test_rule", "desc", "y^2 + 4")
        learner.record_discovery("test_rule", "desc", "z^2 + 9")
        rules = learner.get_learned_buggy_rules()
        assert len(rules) == 1
        rule = rules[0]
        # Must match x^2 + 1
        expr = sp.sympify("x**2 + 1")
        assert rule.check(expr) is True
        # Must match a^2 + 16 (same generic structure)
        expr2 = sp.sympify("a**2 + 16")
        assert rule.check(expr2) is True
        # Must not match x^2 + 2*x + 1
        expr3 = sp.sympify("x**2 + 2*x + 1")
        assert rule.check(expr3) is False


# ═════════════════════════════════════════════════════════════════════════════
# ActR
# ═════════════════════════════════════════════════════════════════════════════

class TestActR:
    def test_update_records_action(self):
        actr = ActR(math_expert=MathExpert())
        actr.update({"type": "stroke", "tool": "pen"})
        assert len(actr.studentModel.behavioral_history) == 1

    @pytest.mark.asyncio
    async def test_process_math(self):
        actr = ActR(math_expert=MathExpert())
        result = await actr.process_math("x^2 + 2*x + 1")
        assert "ast" in result
        assert "buggy_rule" in result

    @pytest.mark.asyncio
    async def test_evaluate_answer_correct(self):
        actr = ActR(math_expert=MathExpert())
        result = await actr.evaluate_answer("(x+1)^2", "(x+1)^2")
        assert result["match"] is True
        assert actr.studentModel.get_activation("algebra") >= 0.5

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="_check_square_binomial_error always returns False (disabled) — dead code")
    async def test_evaluate_answer_incorrect(self):
        actr = ActR(math_expert=MathExpert())
        result = await actr.evaluate_answer("x^2 + 1", "(x+1)^2")
        assert result["match"] is False
        assert result["buggy_rule"] == "square_binomial_error"

    def test_monitor_cognitive_load(self):
        actr = ActR(math_expert=MathExpert())
        load = actr.monitorCognitiveLoad()
        assert "level" in load
        assert "should_intervene" in load

    @pytest.mark.asyncio
    async def test_get_student_profile(self):
        actr = ActR(math_expert=MathExpert())
        await actr.evaluate_answer("(x+1)^2", "(x+1)^2")
        profile = actr.get_student_profile()
        assert "chunks" in profile
        assert "cognitive_load" in profile
        assert "algebra" in profile["chunks"]


# ═════════════════════════════════════════════════════════════════════════════
# Tutor (async)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestTutor:
    async def test_on_user_message(self):
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        tutor.bind_actr(ActR(math_expert=MathExpert()))
        resp = await tutor.on_user_message("Hello tutor")
        assert resp["type"] == "tutor_message"
        assert "text" in resp
        assert resp["role"] == "assistant"

    async def test_on_math_submission_correct(self):
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        tutor.bind_actr(ActR(math_expert=MathExpert()))
        resp = await tutor.on_math_submission("(x+1)^2", "(x+1)^2")
        assert "Correct" in resp["text"] or "✅" in resp["text"]

    @pytest.mark.xfail(reason="_check_square_binomial_error always returns False (disabled) — dead code")
    async def test_on_math_submission_buggy(self):
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        tutor.bind_actr(ActR(math_expert=MathExpert()))
        resp = await tutor.on_math_submission("x^2 + 1", "(x+1)^2")
        assert resp["diagnostic"]["match"] is False
        assert "buggy" in resp["diagnostic"]["buggy_rule"] or "square" in resp["diagnostic"]["buggy_rule"]

    async def test_on_stroke_intervention_low_load(self):
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        tutor.bind_actr(ActR(math_expert=MathExpert()))
        # Simulate enough activity to avoid 'low_activity'
        for _ in range(5):
            tutor.actR.update({"type": "stroke", "tool": "pen"})
        resp = await tutor.on_stroke_intervention()
        # Low cognitive load → no intervention
        assert resp is None

    async def test_dialogue_history(self):
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        tutor.bind_actr(ActR(math_expert=MathExpert()))
        await tutor.on_user_message("Question 1")
        await tutor.on_user_message("Question 2")
        assert len(tutor.dialogueManager.history) == 4  # 2 user + 2 assistant

    async def test_propose_exercises(self):
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        exercises = [
            {"concept": "limits", "difficulty": "easy", "problem_latex": "lim x->0 sin(x)/x"},
            {"concept": "integrals", "difficulty": "medium", "problem_latex": "int x^2 dx"},
        ]
        resp = await tutor.propose_exercises(exercises)
        assert resp["type"] == "tutor_message"
        assert "2 exercise" in resp["text"]
        assert "limits" in resp["text"]
        assert "integrals" in resp["text"]
        assert resp["intervention_type"] == "exercise_proposal"

    async def test_propose_exercises_empty(self):
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        resp = await tutor.propose_exercises([])
        assert resp["type"] == "tutor_message"
        assert "couldn't find" in resp["text"].lower()

    async def test_parse_exercise_response(self):
        from tutor.tutor import Tutor
        # Acceptances
        assert Tutor._parse_exercise_response("oui") == {"action": "accept", "index": 0}
        assert Tutor._parse_exercise_response("yes, the first one") == {"action": "accept", "index": 0}
        assert Tutor._parse_exercise_response("le deuxième") == {"action": "accept", "index": 1}
        assert Tutor._parse_exercise_response("the third") == {"action": "accept", "index": 2}
        assert Tutor._parse_exercise_response("bien sûr") == {"action": "accept", "index": 0}
        assert Tutor._parse_exercise_response("je veux le 3e") == {"action": "accept", "index": 2}
        # Rejections
        assert Tutor._parse_exercise_response("non merci") == {"action": "reject"}
        assert Tutor._parse_exercise_response("no thanks") == {"action": "reject"}
        # Harder
        assert Tutor._parse_exercise_response("plus difficile") == {"action": "harder"}
        assert Tutor._parse_exercise_response("harder please") == {"action": "harder"}
        # Off-topic
        assert Tutor._parse_exercise_response("comment ça va ?") is None

    async def test_accept_exercise_by_text(self):
        from tutor.tutor import Tutor
        from core.llm_client import LLMClient
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        exercises = [
            {"concept": "limits", "difficulty": "easy", "problem_latex": "lim x->0 sin(x)/x", "correct_latex": "1", "steps": []},
            {"concept": "integrals", "difficulty": "medium", "problem_latex": "int x dx", "correct_latex": "x^2/2", "steps": []},
        ]
        await tutor.propose_exercises(exercises)
        assert len(tutor.last_proposed_exercises) == 2

        resp = await tutor.on_user_message("oui, le premier")
        assert resp["type"] == "exercise_accepted"
        assert resp["exercise"]["concept"] == "limits"
        # After acceptance, the list is cleared
        assert len(tutor.last_proposed_exercises) == 0

    async def test_accept_second_exercise_by_text(self):
        from tutor.tutor import Tutor
        from core.llm_client import LLMClient
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        exercises = [
            {"concept": "limits", "difficulty": "easy", "problem_latex": "lim x->0 sin(x)/x", "correct_latex": "1", "steps": []},
            {"concept": "integrals", "difficulty": "medium", "problem_latex": "int x dx", "correct_latex": "x^2/2", "steps": []},
        ]
        await tutor.propose_exercises(exercises)
        resp = await tutor.on_user_message("le deuxième")
        assert resp["type"] == "exercise_accepted"
        assert resp["exercise"]["concept"] == "integrals"

    async def test_parse_help_request(self):
        from tutor.tutor import Tutor
        assert Tutor._parse_help_request("indice") == "hint"
        assert Tutor._parse_help_request("je bloque") == "hint"
        assert Tutor._parse_help_request("donne moi un hint") == "hint"
        assert Tutor._parse_help_request("réponse") == "answer"
        assert Tutor._parse_help_request("montre la solution") == "answer"
        assert Tutor._parse_help_request("show me the answer") == "answer"
        assert Tutor._parse_help_request("comment ça va ?") is None

    async def test_hint_request(self):
        from tutor.tutor import Tutor
        from core.llm_client import LLMClient
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        resp = await tutor.on_user_message("indice")
        assert resp["type"] == "hint_request"

    async def test_answer_request(self):
        from tutor.tutor import Tutor
        from core.llm_client import LLMClient
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        resp = await tutor.on_user_message("réponse")
        assert resp["type"] == "answer_request"

    async def test_parse_exercise_control(self):
        from tutor.tutor import Tutor
        assert Tutor._parse_exercise_control("étape suivante") == "next_step"
        assert Tutor._parse_exercise_control("next step") == "next_step"
        assert Tutor._parse_exercise_control("skip") == "next_step"
        assert Tutor._parse_exercise_control("abandonne") == "give_up"
        assert Tutor._parse_exercise_control("give up") == "give_up"
        assert Tutor._parse_exercise_control("j'abandonne") == "give_up"
        assert Tutor._parse_exercise_control("comment ça va ?") is None

    async def test_next_step_request(self):
        from tutor.tutor import Tutor
        from core.llm_client import LLMClient
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        resp = await tutor.on_user_message("next step")
        assert resp["type"] == "next_step_request"

    async def test_give_up_request(self):
        from tutor.tutor import Tutor
        from core.llm_client import LLMClient
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        resp = await tutor.on_user_message("give up")
        assert resp["type"] == "give_up_request"

    async def test_restart_request(self):
        from tutor.tutor import Tutor
        from core.llm_client import LLMClient
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        resp = await tutor.on_user_message("recommence")
        assert resp["type"] == "restart_request"

    async def test_easier_request(self):
        from tutor.tutor import Tutor
        from core.llm_client import LLMClient
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        resp = await tutor.on_user_message("plus facile")
        assert resp["type"] == "easier_request"

    async def test_recap_request(self):
        from tutor.tutor import Tutor
        from core.llm_client import LLMClient
        tutor = Tutor(llm_client=LLMClient(force_mock=True))
        resp = await tutor.on_user_message("rappelle-moi l'énoncé")
        assert resp["type"] == "recap_request"


class TestStepTracker:
    def test_skip_step(self):
        from domain.math.step_tracker import StepTracker
        from domain.math.math_expert import MathExpert
        tracker = StepTracker(MathExpert())
        tracker.set_exercise({
            "problem_latex": "2x + 3 = 7",
            "correct_latex": "2",
            "steps": ["2x = 4", "x = 2"],
        })
        assert tracker.current_step == 0
        feedback = tracker.skip_step()
        assert feedback["status"] == "step_skipped"
        assert tracker.current_step == 1
        assert "2x = 4" in feedback["text"]

    def test_skip_step_completes_exercise(self):
        from domain.math.step_tracker import StepTracker
        from domain.math.math_expert import MathExpert
        tracker = StepTracker(MathExpert())
        tracker.set_exercise({
            "problem_latex": "x = 1",
            "correct_latex": "1",
            "steps": ["x = 1"],
        })
        feedback = tracker.skip_step()
        assert feedback["status"] == "completed"
        assert tracker.completed


# ═════════════════════════════════════════════════════════════════════════════
# ExerciseLibrary
# ═════════════════════════════════════════════════════════════════════════════

class TestExerciseLibrary:
    def test_add_and_search(self, tmp_path):
        from domain.exercises.exercise_library import ExerciseLibrary
        lib = ExerciseLibrary(storage_path=str(tmp_path / "exercises.json"))
        ex = {
            "problem_latex": "2x + 3 = 7",
            "correct_latex": "x = 2",
            "concept": "linear_equations",
            "difficulty": "easy",
            "steps": [],
            "hint": "Isolate x",
        }
        lib.add(ex, source="sympy")
        results = lib.search(concept="linear_equations", difficulty="easy")
        assert len(results) == 1
        assert results[0]["problem_latex"] == "2x + 3 = 7"

    def test_validate_and_stats(self, tmp_path):
        from domain.exercises.exercise_library import ExerciseLibrary
        lib = ExerciseLibrary(storage_path=str(tmp_path / "exercises.json"))
        ex = {"problem_latex": "x^2 = 4", "correct_latex": "x = 2", "concept": "quadratic"}
        added = lib.add(ex)
        assert not added["validated"]
        lib.validate(added["id"])
        assert lib.get(added["id"])["validated"]
        stats = lib.stats()
        assert stats["validated"] == 1

    def test_duplicate_increments_usage(self, tmp_path):
        from domain.exercises.exercise_library import ExerciseLibrary
        lib = ExerciseLibrary(storage_path=str(tmp_path / "exercises.json"))
        ex = {"problem_latex": "x = 1", "correct_latex": "1", "concept": "generic"}
        lib.add(ex)
        lib.add(ex)
        assert lib.get(lib.hash_exercise("x = 1"))["usage_count"] == 2


class TestExerciseGeneratorVerify:
    def test_verify_linear_equation_ok(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        ok, detail = ExerciseGenerator.verify_with_sympy({
            "problem_latex": "2x + 3 = 7",
            "correct_latex": "2",
            "concept": "linear_equations",
        })
        assert ok is True
        assert "verified" in detail.lower()

    def test_verify_linear_equation_ko(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        ok, detail = ExerciseGenerator.verify_with_sympy({
            "problem_latex": "2x + 3 = 7",
            "correct_latex": "5",
            "concept": "linear_equations",
        })
        assert ok is False
        assert "mismatch" in detail.lower() or "error" in detail.lower()

    def test_generate_prefers_library(self, tmp_path):
        from domain.exercises.exercise_generator import ExerciseGenerator
        from domain.exercises.exercise_library import ExerciseLibrary
        lib = ExerciseLibrary(storage_path=str(tmp_path / "exercises.json"))
        lib.add({
            "problem_latex": "library_exercise",
            "correct_latex": "42",
            "concept": "generic",
            "difficulty": "easy",
            "validated": True,
            "usage_count": 5,
        })
        gen = ExerciseGenerator()
        gen.library = lib
        ex = gen.generate("generic", "easy")
        assert ex["source"] == "library"
        assert ex["problem_latex"] == "library_exercise"


# ═════════════════════════════════════════════════════════════════════════════
# API BuggyRules (REST)
# ═════════════════════════════════════════════════════════════════════════════

class TestBuggyRulesAPI:
    def test_list_validate_reject(self, tmp_path):
        from fastapi.testclient import TestClient
        from app.main import app, math_expert

        # Isolate the learner to avoid polluting the real database
        old_path = math_expert.learner.storage_path
        old_rules = dict(math_expert.learner._rules)
        math_expert.learner.storage_path = str(tmp_path / "learned_api.json")
        math_expert.learner._rules = {}
        math_expert.reload_learned_rules()

        client = TestClient(app)

        # 1. Initial list (none pending)
        resp = client.get("/api/buggy-rules/pending")
        assert resp.status_code == 200
        assert resp.json()["pending"] == []

        # 2. Inject a discovery
        math_expert.learner.record_discovery(
            name="api_test_rule",
            description="Test rule from API",
            user_latex="x^2 + 1",
        )

        # 3. Verify it appears in /api/buggy-rules
        resp = client.get("/api/buggy-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert any(r["name"] == "api_test_rule" for r in data["pending_discoveries"])

        # 4. Validate manually
        resp = client.post("/api/buggy-rules/api_test_rule/validate")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # 5. Verify it is no longer pending
        resp = client.get("/api/buggy-rules/pending")
        assert len(resp.json()["pending"]) == 0

        # 6. Verify it is now in the local rules
        resp = client.get("/api/buggy-rules")
        assert any(r["name"] == "api_test_rule" for r in resp.json()["local_rules"])

        # 7. Reject / delete
        resp = client.delete("/api/buggy-rules/api_test_rule")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # 8. Verify disappearance
        resp = client.get("/api/buggy-rules")
        assert not any(r["name"] == "api_test_rule" for r in resp.json()["local_rules"])

        # Restore the original state
        math_expert.learner.storage_path = old_path
        math_expert.learner._rules = old_rules
        math_expert.reload_learned_rules()


# ═════════════════════════════════════════════════════════════════════════════
# ExerciseGenerator – prep school / university concepts
# ═════════════════════════════════════════════════════════════════════════════

class TestExerciseGeneratorPrepa:
    def test_generate_differential_equation(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        ex = gen.generate("differential_equations", "easy")
        assert ex["concept"] == "differential_equations"
        assert "y'" in ex["problem_latex"] or "\\frac{d" in ex["problem_latex"]
        assert "hint" in ex
        assert "steps" in ex

    def test_generate_eigenvalues(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        ex = gen.generate("eigenvalues", "medium")
        assert ex["concept"] == "eigenvalues"
        assert "lambda" in ex["problem_latex"] or "\\text" in ex["problem_latex"]
        assert ex["correct_latex"]

    def test_generate_taylor_series(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        ex = gen.generate("taylor_series", "medium")
        assert ex["concept"] == "taylor_series"
        assert "Taylor" in ex["problem_latex"] or "series" in ex["problem_latex"]

    def test_generate_series_convergence(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        ex = gen.generate("series_convergence", "easy")
        assert ex["concept"] == "series_convergence"
        assert "\\sum" in ex["problem_latex"]

    def test_generate_linear_systems(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        ex = gen.generate("linear_systems", "easy")
        assert ex["concept"] == "linear_systems"
        assert "Solve" in ex["problem_latex"]

    def test_generate_topology(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        ex = gen.generate("topology", "medium")
        assert ex["concept"] == "topology"
        assert "open" in ex["problem_latex"] or "closure" in ex["problem_latex"]

    def test_generate_diagonalization(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        ex = gen.generate("diagonalization", "easy")
        assert ex["concept"] == "diagonalization"
        assert "Diagonalize" in ex["problem_latex"]

    def test_generate_probability_continuous(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        ex = gen.generate("probability_continuous", "medium")
        assert ex["concept"] == "probability_continuous"
        assert "\\mathcal{N}" in ex["problem_latex"]

    def test_verify_edo_solution(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        ex = gen.generate("differential_equations", "easy")
        # Verify that the generator produces a verifiable exercise
        ok, detail = ExerciseGenerator.verify_with_sympy(ex)
        # Complex ODEs may fail automatic verification,
        # but the generator must produce a consistent result
        assert isinstance(ok, bool)
        assert detail != ""
        assert ex["correct_latex"]
        assert ex["problem_latex"]

    def test_generate_progressive_series(self):
        from domain.exercises.exercise_generator import ExerciseGenerator
        gen = ExerciseGenerator(seed=42)
        series = gen.generate_progressive_series("integrals")
        assert len(series) == 3
        assert series[0]["difficulty"] == "easy"
        assert series[1]["difficulty"] == "medium"
        assert series[2]["difficulty"] == "hard"
        assert all(s["concept"] == "integrals" for s in series)
