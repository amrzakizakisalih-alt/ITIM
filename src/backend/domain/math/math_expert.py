"""
MathExpert – Domain Model (Math Expert).

Represents the reference knowledge base of the tutoring system.
It uses SymPy to manipulate LaTeX expressions, solve problems step by step,
and integrates *Buggy Rules* to identify recurrent error patterns in the
learner.

v2 new features:
  • Buggy rules based on SymPy AST (no more regex on raw LaTeX).
  • Commutativity handling in AST comparison.
  • Scoring / weighting of error rules.
  • Real logging (no more print).
  • Async LLM fallback when no local rule matches.
  • Extensible rule loading (dict/JSON).
"""

import json
import logging
import os
from typing import Callable, Dict, Any, List, Optional

import sympy as sp
from latex2sympy2 import latex2sympy

from core.llm_client import LLMClient
from domain.exercises.buggy_rule_learner import BuggyRuleLearner, BuggyRule
from core.json_utils import extract_json

logger = logging.getLogger(__name__)

# ── Structural detection helpers ─────────────────────────────────────────


def _check_square_binomial_error(expr: sp.Expr) -> bool:
    """Detects (a+b)² → a² + b² (missing double product).

    NOTE: This heuristic is disabled because without the original problem
    (the expression to expand), we cannot distinguish an error from a
    valid expression like x² + y².
    """
    return False


def _check_distributivity_error(expr: sp.Expr) -> bool:
    """Detects a(b+c) → ab + c (partial distribution)."""
    if not isinstance(expr, sp.Add):
        return False
    mul_terms = [t for t in expr.args if isinstance(t, sp.Mul)]
    other_terms = [t for t in expr.args if not isinstance(t, sp.Mul)]
    if not mul_terms or not other_terms:
        return False
    for mul_term in mul_terms:
        # The Mul must contain a numeric coefficient and an Add
        has_coeff = any(arg.is_Number for arg in mul_term.args)
        inner_add = next(
            (arg for arg in mul_term.args if isinstance(arg, sp.Add)), None
        )
        if not has_coeff or inner_add is None:
            continue
        # Checks that a term of the Add was not distributed
        for child in inner_add.args:
            found = False
            for other in other_terms:
                if sp.simplify(other - child) == 0:
                    found = True
                    break
            if found:
                return True
    return False


def _check_sign_error(expr: sp.Expr) -> bool:
    """Detects -(a+b) → -a + b (incorrect distribution of the minus sign)."""
    if not isinstance(expr, sp.Add):
        return False
    # Looks for a term of the form -(a+b) incorrectly distributed as -a + b.
    # The error sign appears when a Mul(-1, Add(...)) is present
    # but the children of the Add were not negated.
    for term in expr.args:
        if isinstance(term, sp.Mul) and any(arg == -1 for arg in term.args):
            # Checks that the Mul contains an Add (like -(a+b))
            inner_add = next(
                (arg for arg in term.args if isinstance(arg, sp.Add)), None
            )
            if inner_add is not None:
                # Checks that the expression contains a positive term
                # corresponding to one of the Add's children without negation
                for child in inner_add.args:
                    for other in expr.args:
                        if other is term:
                            continue
                        if sp.simplify(other - child) == 0:
                            return True
    return False


def _check_incomplete_expansion(expr: sp.Expr) -> bool:
    """Detects incomplete expansions of notable products.

    NOTE: Disabled because without the original problem we cannot know
    whether the student was supposed to expand an expression or not.
    """
    return False


# ── MathExpert ───────────────────────────────────────────────────────────────


class MathExpert:
    """
    Math expert based on SymPy.
    """

    COMMUTATIVE_TYPES = {"Add", "Mul"}

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.x = sp.Symbol("x")
        self.y = sp.Symbol("y")
        self.llm = llm_client
        self.learner = BuggyRuleLearner()
        self.buggy_rules: List[BuggyRule] = []
        self._build_buggy_rules()
        self._load_learned_rules()
        self._load_external_rules()

    # ── Error Rules ─────────────────────────────────────────────────────────

    def _build_buggy_rules(self):
        """Builds the base of typical cognitive error rules."""
        self.buggy_rules = [
            BuggyRule(
                "square_binomial_error",
                "(a+b)² becomes a²+b² instead of a²+2ab+b²",
                _check_square_binomial_error,
                weight=1.0,
                tags=["algebra", "expansion"],
            ),
            BuggyRule(
                "distributivity_error",
                "a(b+c) becomes ab+c instead of ab+ac",
                _check_distributivity_error,
                weight=0.9,
                tags=["algebra", "arithmetic"],
            ),
            BuggyRule(
                "sign_error",
                "-(a+b) becomes -a+b instead of -a-b",
                _check_sign_error,
                weight=0.9,
                tags=["algebra", "sign"],
            ),
            BuggyRule(
                "incomplete_expansion",
                "Incomplete expansion of a remarkable product",
                _check_incomplete_expansion,
                weight=0.8,
                tags=["algebra", "expansion"],
            ),
        ]

    def _load_learned_rules(self):
        """Injects rules learned by the learner into the local base."""
        learned = self.learner.get_learned_buggy_rules()
        if learned:
            logger.info("Injecting %d learned buggy rule(s)", len(learned))
            self.buggy_rules.extend(learned)

    def reload_learned_rules(self):
        """Hot-reloads learned rules (without restarting)."""
        # Remove old learned rules to avoid duplicates
        self.buggy_rules = [
            r for r in self.buggy_rules
            if "llm_discovered" not in r.tags
        ]
        self._load_learned_rules()

    def _load_external_rules(self, path: Optional[str] = None):
        """
        Loads additional rules from a JSON file.
        The JSON must contain a list of objects with 'name', 'description',
        and optionally 'weight' / 'tags'.
        Custom checkers must be added manually via `add_rule`.
        """
        config_path = path or os.path.join(os.path.dirname(__file__), "buggy_rules.json")
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                rule = BuggyRule(
                    name=item["name"],
                    description=item["description"],
                    checker=lambda e, pattern=item.get("pattern"): False,  # placeholder
                    weight=item.get("weight", 1.0),
                    tags=item.get("tags", []),
                )
                self.buggy_rules.append(rule)
            logger.info("Loaded %d external buggy rule(s) from %s", len(data), config_path)
        except Exception as exc:
            logger.warning("Failed to load external buggy rules: %s", exc)

    def list_buggy_rules(self) -> List[Dict[str, str]]:
        """Lists all available error rules."""
        return [r.to_dict() for r in self.buggy_rules]

    # ── Parsing & AST ──────────────────────────────────────────────────────

    def getAST(self, latex_str: str) -> Optional[Dict[str, Any]]:
        """
        Converts a LaTeX string into an Abstract Syntax Tree (AST)
        represented as a recursive dictionary.
        """
        try:
            expr = latex2sympy(latex_str)
            if isinstance(expr, list):
                expr = expr[0] if len(expr) > 0 else None
            if isinstance(expr, str):
                return {"type": "LiteralString", "content": expr}
            if expr is None:
                return None
            from domain.math.ast_utils import sympy_to_ast
            return sympy_to_ast(expr)
        except Exception as exc:
            logger.error("AST parsing error for '%s': %s", latex_str, exc)
            return None

    # ── AST Comparison ─────────────────────────────────────────────────────

    def _ast_match(self, a: dict, b: dict) -> bool:
        """Recursive comparison of two ASTs, with commutativity handling."""
        if a.get("type") != b.get("type"):
            return False

        node_type = a.get("type")
        if node_type in self.COMMUTATIVE_TYPES:
            return self._match_commutative_children(
                a.get("children", []), b.get("children", [])
            )

        # Strict (ordered) comparison for non-commutative operations
        a_children = a.get("children", [])
        b_children = b.get("children", [])
        if len(a_children) != len(b_children):
            return False
        return all(self._ast_match(ac, bc) for ac, bc in zip(a_children, b_children))

    def _match_commutative_children(self, a_children: List[dict], b_children: List[dict]) -> bool:
        """Matches two child lists ignoring order (commutative operations)."""
        if len(a_children) != len(b_children):
            return False
        if not a_children:
            return True

        used = set()
        for ac in a_children:
            matched = False
            for idx, bc in enumerate(b_children):
                if idx in used:
                    continue
                if self._ast_match(ac, bc):
                    used.add(idx)
                    matched = True
                    break
            if not matched:
                return False
        return True

    # ── Resolution ─────────────────────────────────────────────────────────

    def solveStepByStep(self, latex_str: str, variable: str = "x") -> List[str]:
        """
        Solves a LaTeX equation or expression step by step.
        Returns a list of strings describing each step.
        """
        steps = []
        try:
            raw = latex2sympy(latex_str)
            var = sp.Symbol(variable)

            # latex2sympy may return a list for equations
            if isinstance(raw, list) and len(raw) > 0:
                expr = raw[0]
            else:
                expr = raw

            # ── Linear equations in one variable ────────────────────────
            if isinstance(expr, sp.Eq):
                lhs, rhs = expr.lhs, expr.rhs
                # Try to solve to detect a linear equation
                try:
                    poly = sp.Poly(lhs - rhs, var)
                    if poly.degree() == 1:
                        a = poly.coeff_monomial(var)
                        b = poly.coeff_monomial(1)
                        if a != 0:
                            sol = -b / a
                            # Use latex_str for the initial equation because
                            # latex2sympy may have solved the equation.
                            steps.append(f"1. Initial equation: ${latex_str}$")
                            steps.append(f"2. Isolate the ${variable}$ term: ${sp.latex(sp.Eq(a*var, -b))}$")
                            steps.append(f"3. Divide by the coefficient: ${sp.latex(sp.Eq(var, sol))}$")
                            return steps
                except Exception:
                    pass

                # Generic fallback for equations
                steps.append(f"1. Initial equation: ${latex_str}$")
                new_eq = sp.Eq(lhs - rhs, 0)
                steps.append(f"2. Rearrangement: ${sp.latex(new_eq)}$")
                simplified = sp.simplify(lhs - rhs)
                steps.append(f"3. Simplification: ${sp.latex(simplified)} = 0$")
                try:
                    solutions = sp.solve(simplified, var)
                    steps.append(f"4. Solution(s): ${sp.latex(solutions)}$")
                except Exception as exc:
                    logger.warning("SymPy could not solve %s: %s", latex_str, exc)
                    steps.append("4. Analytical solution not available for this form.")
                return steps

            # ── Simple expressions ─────────────────────────────────────
            if expr is not None:
                steps.append(f"1. Expression: ${sp.latex(expr)}$")
                simplified = sp.simplify(expr)
                if simplified != expr:
                    steps.append(f"2. Simplification: ${sp.latex(simplified)}$")
                expanded = sp.expand(expr)
                if expanded != expr and expanded != simplified:
                    steps.append(f"3. Développement : ${sp.latex(expanded)}$")
                factored = sp.factor(expr)
                if factored != expr and factored != simplified and factored != expanded:
                    steps.append(f"4. Factorisation : ${sp.latex(factored)}$")
                return steps

            steps.append("Expression vide ou non reconnue.")
            return steps
        except Exception as exc:
            logger.error("solveStepByStep error for '%s': %s", latex_str, exc)
            return [f"Erreur de résolution : {exc}"]

    # ── Comparison & Diagnosis (synchronous) ───────────────────────────────

    def compareSteps(self, user_latex: str, correct_latex: str) -> Dict[str, Any]:
        """
        Compares the user's AST with that of the correct solution.
        Returns a structured diagnosis.
        """
        user_ast = self.getAST(user_latex)
        correct_ast = self.getAST(correct_latex)

        if user_ast is None or correct_ast is None:
            return {
                "match": False,
                "error": "Parsing failed",
                "buggy_rule": None,
                "hint": None,
                "user_ast": user_ast,
                "correct_ast": correct_ast,
            }

        # 1. Structural comparison
        match = self._ast_match(user_ast, correct_ast)

        # 2. Verification by SymPy simplification (mathematical equivalence)
        if not match:
            try:
                user_expr = latex2sympy(user_latex)
                correct_expr = latex2sympy(correct_latex)
                if isinstance(user_expr, sp.Expr) and isinstance(correct_expr, sp.Expr):
                    if sp.simplify(user_expr - correct_expr) == 0:
                        match = True
            except Exception as exc:
                logger.debug("SymPy simplification comparison failed: %s", exc)

        diagnostic: Dict[str, Any] = {
            "match": match,
            "user_ast": user_ast,
            "correct_ast": correct_ast,
            "buggy_rule": None,
            "hint": None,
            "source": "local",
        }

        if not match:
            rule = self.detect_buggy_rule(user_latex)
            if rule:
                diagnostic["buggy_rule"] = rule.name
                diagnostic["hint"] = f"Watch out for the '{rule.name}' bias: {rule.description}"
                diagnostic["confidence"] = rule.weight
            else:
                diagnostic["hint"] = (
                    "Votre réponse semble différente de la solution attendue. "
                    "Re-vérifiez vos calculs étape par étape."
                )

        return diagnostic

    def detect_buggy_rule(self, latex_str: str) -> Optional[BuggyRule]:
        """
        Tests the expression against all buggy rules (synchronous mode).
        Returns the rule with the best score if several match.
        """
        try:
            expr = latex2sympy(latex_str)
            if isinstance(expr, list):
                expr = expr[0] if expr else None
            if expr is None or not isinstance(expr, sp.Expr):
                return None
        except Exception as exc:
            logger.debug("Cannot parse '%s' for buggy detection: %s", latex_str, exc)
            return None

        candidates: List[tuple] = []
        for rule in self.buggy_rules:
            if rule.check(expr):
                candidates.append((rule, rule.weight))

        if not candidates:
            return None

        # Return the rule with the highest weight
        return max(candidates, key=lambda x: x[1])[0]

    # ── LLM Fallback (asynchronous) ────────────────────────────────────────

    async def detect_buggy_rule_async(
        self,
        latex_str: str,
        topic: str = "algebra",
    ) -> Optional[Dict[str, Any]]:
        """
        Asynchronous version with LLM fallback.
        Returns a JSON-friendly dict instead of a BuggyRule object.
        """
        local = self.detect_buggy_rule(latex_str)
        if local:
            return {
                "name": local.name,
                "description": local.description,
                "weight": local.weight,
                "source": "local",
                "confidence": min(0.95, 0.7 + local.weight * 0.25),
            }

        if self.llm and self.llm.is_available():
            return await self._llm_diagnose(latex_str, topic=topic)

        return None

    async def compare_steps_async(
        self,
        user_latex: str,
        correct_latex: str,
        topic: str = "algebra",
    ) -> Dict[str, Any]:
        """
        Asynchronous version of compareSteps with LLM fallback if no local
        rule matches.
        """
        result = self.compareSteps(user_latex, correct_latex)
        if result["match"] or result.get("buggy_rule"):
            return result

        if self.llm and self.llm.is_available():
            llm_diag = await self._llm_diagnose_difference(
                user_latex, correct_latex, topic
            )
            if llm_diag and llm_diag.get("buggy_rule"):
                result["buggy_rule"] = llm_diag["buggy_rule"]
                result["hint"] = llm_diag.get("hint", result["hint"])
                result["source"] = "llm"
                result["confidence"] = llm_diag.get("confidence", 0.6)

        return result

    async def _llm_diagnose(self, latex_str: str, topic: str) -> Optional[Dict[str, Any]]:
        """Asks the LLM to diagnose a single expression."""
        prompt = (
            f"You are a mathematics expert. A student wrote this expression: ${latex_str}$\n"
            f"Topic: {topic}\n"
            "Is this a common student mistake (buggy rule)? "
            "If yes, return ONLY a JSON object with keys: "
            "buggy_rule (short snake_case name), hint (1-sentence explanation), confidence (0.0-1.0). "
            "If no, return ONLY: {}"
        )
        try:
            raw = await self.llm.generate(prompt, temperature=0.3, max_tokens=256)
            result = self._parse_llm_json(raw)
            if result and result.get("buggy_rule"):
                self.learner.record_discovery(
                    name=result["buggy_rule"],
                    description=result.get("hint", ""),
                    user_latex=latex_str,
                )
            return result
        except Exception as exc:
            logger.warning("LLM diagnose failed: %s", exc)
            return None

    async def _llm_diagnose_difference(
        self, user_latex: str, correct_latex: str, topic: str
    ) -> Optional[Dict[str, Any]]:
        """Asks the LLM to diagnose the gap between two answers."""
        prompt = (
            f"You are a mathematics expert.\n"
            f"Student answer: ${user_latex}$\n"
            f"Correct answer: ${correct_latex}$\n"
            f"Topic: {topic}\n"
            "Does the student answer reflect a known common misconception (buggy rule)? "
            "If yes, return ONLY a JSON object with keys: "
            "buggy_rule (short snake_case name), hint (1-sentence explanation), confidence (0.0-1.0). "
            "If no, return ONLY: {}"
        )
        try:
            raw = await self.llm.generate(prompt, temperature=0.3, max_tokens=256)
            result = self._parse_llm_json(raw)
            if result and result.get("buggy_rule"):
                self.learner.record_discovery(
                    name=result["buggy_rule"],
                    description=result.get("hint", ""),
                    user_latex=user_latex,
                )
            return result
        except Exception as exc:
            logger.warning("LLM diagnose difference failed: %s", exc)
            return None

    @staticmethod
    def _parse_llm_json(text: str) -> Optional[Dict[str, Any]]:
        """Extracts a JSON block from the LLM response."""
        data = extract_json(text)
        if isinstance(data, dict) and data.get("buggy_rule"):
            return data
        return None
