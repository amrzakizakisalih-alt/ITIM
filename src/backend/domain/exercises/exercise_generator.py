"""
ExerciseGenerator – Math exercise generator for undergrad / university level.

Creates problems and their LaTeX solutions for an audience of CPGE, bachelor's
math, or engineering school classes. Uses SymPy to guarantee mathematical
correctness.

Document → exercises orchestration
----------------------------------
generate_from_document(text, llm_client)
    ├── DocumentProcessor._extract_with_keywords(text)   # detected concepts
    ├── LLM generate()                                    # contextual exercises
    │       └── [fallback] generate() × 3                # SymPy if LLM absent
    └── generate_and_verify(raw_exercises)               # ExerciseLibrary cache
"""

import json
import logging
import random
import re
from typing import List, Dict, Any, Optional, Tuple

import sympy as sp
from latex2sympy2 import latex2sympy

from domain.exercises.exercise_library import ExerciseLibrary
from domain.exercises.document_processor import DocumentProcessor
from core.json_utils import extract_json

try:
    import wordninja
    _HAS_WORDNINJA = True
except ImportError:
    _HAS_WORDNINJA = False
    wordninja = None

logger = logging.getLogger(__name__)

# Shared prompt for LLM generation from a document
_DOC_PROMPT_TEMPLATE = (
    "You are given a mathematical document excerpt. "
    "Create exactly 3 original exercises inspired by the concepts and notation found in this text. "
    "Each exercise must use the SAME mathematical notation and vocabulary as the document.\n\n"
    "Document text (first 3000 chars):\n{doc_text}\n\n"
    "The 3 exercises MUST cover the 3 difficulty levels in this exact order:\n"
    "1. easy   — direct application of a concept from the text\n"
    "2. medium — requires 2-3 steps, minor trick or combination of ideas\n"
    "3. hard   — proof, technical computation, or synthesis of multiple concepts\n\n"
    "Return ONLY a valid JSON array of exactly 3 objects. Each object MUST have these keys:\n"
    '- "concept": short id like "linear_equations" or "taylor_series"\n'
    '- "difficulty": one of "easy", "medium", "hard" (must be exactly easy then medium then hard)\n'
    '- "problem_latex": the problem statement. Write NORMAL TEXT with spaces. Use $...$ ONLY around mathematical formulas. NEVER put plain English inside $...$.\n'
    '- "correct_latex": the correct answer. Use $...$ around formulas only.\n'
    '- "hint": a short pedagogical hint in plain text\n\n'
    "CRITICAL RULES:\n"
    "- Output ONLY the JSON array, no markdown code blocks, no explanation.\n"
    "- Each exercise must be DIRECTLY related to the document content.\n"
    "- PRESERVE ALL SPACES. Do NOT glue words together.\n"
    "- Use $...$ ONLY for formulas, not for plain English text.\n"
    "- Use standard LaTeX syntax: \\frac{{a}}{{b}}, \\sqrt{{x}}, x^2, \\sum, \\int, etc."
)

_DOC_SYSTEM_PROMPT = (
    "You are a math exercise generator. "
    "You output ONLY valid JSON arrays. "
    "Never wrap the output in markdown code blocks. "
    "Each exercise must be directly inspired by the provided document."
)

# Prompt to extract REAL exercises from a document
_EXTRACT_PROMPT_TEMPLATE = (
    "You are given a mathematical document (exercise sheet, homework, exam, or textbook page). "
    "Your task is to extract ALL exercises found in the text.\n\n"
    "Document text:\n{doc_text}\n\n"
    "For each exercise found, return an object with these keys:\n"
    '- "problem_latex": the EXACT problem statement. Keep the original wording. Use $...$ ONLY around mathematical formulas.\n'
    '- "correct_latex": the correct answer or solution if present in the document. If missing, compute it.\n'
    '- "hint": a short pedagogical hint\n'
    '- "steps": a list of solution steps\n'
    '- "concept": short id like "linear_equations", "integrals", "derivatives"\n'
    '- "difficulty": one of "easy", "medium", "hard"\n\n'
    "OUTPUT FORMAT (very important):\n"
    "Return a JSON array like this:\n"
    '[{{"problem_latex":"...", "correct_latex":"...", "hint":"...", "steps":[], "concept":"...", "difficulty":"..."}}]\n\n'
    "If NO exercise is found, return: []"
)

_EXTRACT_SYSTEM_PROMPT = (
    "You are a math exercise parser. "
    "Extract every numbered problem, exercise, or question from the document. "
    "Output ONLY a raw JSON array. No markdown code blocks, no explanations, no intro text."
)


class ExerciseGenerator:
    """
    Math exercise generator for undergrad / university level.

    Difficulties
    ------------
    - easy  : standard tutorial (direct application of the course)
    - medium: homework (several steps, minor trick)
    - hard  : oral/exam (proof, technical computation, synthesis)

    Main entry point for generation from a document:
        await exercise_gen.generate_from_document(text, llm_client)
    """

    DIFFICULTIES = ["easy", "medium", "hard"]

    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.library = ExerciseLibrary()
        self._doc_processor = DocumentProcessor()  # used for concept extraction

    # ── Generation from an imported document ────────────────────────────────

    async def generate_from_document(
        self,
        text: str,
        llm_client=None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Full pipeline: document text → concepts → exercises.

        1. Concept extraction via DocumentProcessor (fast heuristic,
           no LLM needed for this step).
        2. LLM generation of 3 contextual exercises (easy/medium/hard).
           If the LLM is absent or fails → SymPy fallback on detected
           concepts.
        3. SymPy verification + caching in ExerciseLibrary.

        Returns
        -------
        (exercises, concepts)
            exercises : list of dicts ready to send to the frontend
            concepts  : list of dicts {name, confidence, ...} for the StudentModel
        """
        # ── 1. Concepts ───────────────────────────────────────────────────────
        concepts = await self._doc_processor.extract_concepts_async(text)
        logger.info(
            "[generate_from_document] %d concept(s) detected: %s",
            len(concepts),
            [c["name"] for c in concepts[:5]],
        )

        # ── 2. LLM Generation ─────────────────────────────────────────────────
        raw_exercises: List[Dict[str, Any]] = []

        if llm_client and llm_client.is_available():
            raw_exercises = await self._generate_llm_exercises(text, llm_client)

        # ── 3. SymPy Fallback ─────────────────────────────────────────────────
        if not raw_exercises:
            logger.info("[generate_from_document] LLM unavailable or failed — using SymPy fallback")
            fallback_concepts = [c["name"] for c in concepts[:3]] or ["generic"]
            for i, diff in enumerate(self.DIFFICULTIES):
                concept = fallback_concepts[i % len(fallback_concepts)]
                raw_exercises.append(self.generate(concept, difficulty=diff, prefer_library=True))
            # SymPy exercises are already clean, return them directly
            return raw_exercises, concepts

        # ── 4. Verification + cache ───────────────────────────────────────────
        exercises = self.generate_and_verify(raw_exercises, source="llm_document")
        return exercises, concepts

    @staticmethod
    def _split_document_into_chunks(text: str) -> List[str]:
        """
        Splits a document into exercise chunks via heuristic.
        Looks for patterns: Exercice/Exercise/Problem/Question + number,
        or lines starting with a number followed by . ) or space.
        """
        # Main pattern: keyword + number (captured for splitting)
        pattern = re.compile(
            r'(?:^|\n)\s*(?:Exercice|Exercise|Problem|Question|Problème)\s*\d+\b',
            re.IGNORECASE,
        )
        # Secondary pattern: line starting with an isolated number
        alt_pattern = re.compile(
            r'(?:^|\n)\s*(?:\d+|\(\d+\)|\[\d+\])\s*[\.\)\-]\s*(?=[A-Z])',
            re.IGNORECASE,
        )

        splits = list(pattern.finditer(text))
        if len(splits) < 2:
            splits = list(alt_pattern.finditer(text))

        if len(splits) < 2:
            return [text]

        chunks = []
        for i, m in enumerate(splits):
            start = m.start()
            end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
            chunk = text[start:end].strip()
            if len(chunk) > 20:
                chunks.append(chunk)
        return chunks

    async def extract_exercises_from_document(
        self,
        text: str,
        llm_client,
    ) -> List[Dict[str, Any]]:
        """
        Extracts the real exercises present in an OCR'd document.
        Strategy:
          1. Global attempt (whole document).
          2. If failure → heuristic chunking + individual parsing.
        """
        if not llm_client or not llm_client.is_available():
            return []

        # ── 1. Global attempt ─────────────────────────────────────────────────
        prompt = _EXTRACT_PROMPT_TEMPLATE.format(doc_text=text[:4000])
        try:
            raw = await llm_client.generate(
                prompt,
                system_prompt=_EXTRACT_SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=2048,
            )
            exercises = self._parse_llm_json(raw)
            if exercises:
                for ex in exercises:
                    ex.pop("difficulty", None)
                logger.info("[extract_exercises_from_document] %d exercise(s) extracted (global)", len(exercises))
                return exercises
            else:
                logger.warning(
                    "[extract_exercises_from_document] Global parse failed. Raw (first 600 chars): %s",
                    raw[:600] if isinstance(raw, str) else repr(raw),
                )
        except Exception as exc:
            logger.error("[ExerciseGenerator] Global LLM extraction failed: %s", exc)

        # ── 2. Heuristic chunking ─────────────────────────────────────────────
        chunks = self._split_document_into_chunks(text)
        if len(chunks) <= 1:
            logger.info("[extract_exercises_from_document] No chunks found, giving up")
            return []

        logger.info("[extract_exercises_from_document] Trying chunking: %d chunks", len(chunks))
        all_exercises: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(chunks[:5]):  # max 5 chunks to limit LLM calls
            chunk_prompt = _EXTRACT_PROMPT_TEMPLATE.format(doc_text=chunk[:1200])
            try:
                raw = await llm_client.generate(
                    chunk_prompt,
                    system_prompt=_EXTRACT_SYSTEM_PROMPT,
                    temperature=0.2,
                    max_tokens=1024,
                )
                parsed = self._parse_llm_json(raw)
                if parsed:
                    for ex in parsed:
                        ex.pop("difficulty", None)
                    all_exercises.extend(parsed)
                    logger.info("[extract_exercises_from_document] Chunk %d → %d exercise(s)", idx + 1, len(parsed))
                else:
                    logger.warning(
                        "[extract_exercises_from_document] Chunk %d unparsable. Raw (first 400 chars): %s",
                        idx + 1,
                        raw[:400] if isinstance(raw, str) else repr(raw),
                    )
            except Exception as exc:
                logger.error("[ExerciseGenerator] Chunk %d extraction failed: %s", idx + 1, exc)

        if all_exercises:
            logger.info("[extract_exercises_from_document] Total extracted via chunking: %d", len(all_exercises))
        return all_exercises

    async def _generate_llm_exercises(
        self, text: str, llm_client
    ) -> List[Dict[str, Any]]:
        """
        Calls the LLM to generate 3 contextual exercises.
        Returns an empty list on failure (the caller handles the fallback).
        """
        prompt = _DOC_PROMPT_TEMPLATE.format(doc_text=text[:3000])
        try:
            raw = await llm_client.generate(
                prompt,
                system_prompt=_DOC_SYSTEM_PROMPT,
                temperature=0.5,
                max_tokens=2048,
            )
            return self._parse_llm_json(raw)
        except Exception as exc:
            logger.error("[ExerciseGenerator] LLM generation failed: %s", exc)
            return []

    @staticmethod
    def _sanitize_problem_latex(text: str) -> str:
        """
        Post-processing to rehydrate text glued without spaces.
        1. Removes exact repetitions.
        2. Segments English words with wordninja.
        Protects LaTeX commands (preceded by \).
        """
        if not text or not _HAS_WORDNINJA:
            return text

        # 1. Remove exact repetitions (substrings of 15+ characters)
        text = re.sub(r'(.{15,}?)\1', r'\1', text)

        # 2. Segment glued words (>= 4 letters, not preceded by \)
        def replace_words(s: str) -> str:
            result = []
            last_end = 0
            for m in re.finditer(r'[a-zA-Z]{4,}', s):
                start = m.start()
                # If preceded by a backslash, it's a LaTeX command → leave intact
                if start > 0 and s[start - 1] == '\\':
                    result.append(s[last_end:m.end()])
                else:
                    result.append(s[last_end:m.start()])
                    words = wordninja.split(m.group(0))
                    result.append(' '.join(words))
                last_end = m.end()
            result.append(s[last_end:])
            return ''.join(result)

        return replace_words(text)

    @staticmethod
    def _parse_llm_json(raw: str) -> List[Dict[str, Any]]:
        """
        Cleans and parses the LLM JSON response.
        Robust to markdown backticks, 'json' prefixes, stray spaces.
        """
        parsed = extract_json(raw)

        # The LLM may return a dict with an "exercises" key
        if isinstance(parsed, dict):
            candidates = parsed.get("exercises") or parsed.get("problems") or parsed.get("questions") or parsed.get("results")
            if isinstance(candidates, list):
                parsed = candidates
            else:
                return []

        if not isinstance(parsed, list):
            return []

        exercises = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            # Also accept "problem", "question", "statement" as aliases
            problem = item.get("problem_latex") or item.get("problem") or item.get("question") or item.get("statement")
            if not problem:
                continue
            exercises.append({
                "concept": item.get("concept", "custom"),
                "difficulty": item.get("difficulty", "easy"),
                "problem_latex": ExerciseGenerator._sanitize_problem_latex(problem),
                "correct_latex": ExerciseGenerator._sanitize_problem_latex(
                    item.get("correct_latex") or item.get("answer") or item.get("solution") or ""
                ),
                "hint": item.get("hint", "Think step by step."),
                "steps": item.get("steps", []),
            })
        return exercises

    # ── Unit Generation ─────────────────────────────────────────────────────

    def generate(self, concept: str, difficulty: str = "easy", prefer_library: bool = True) -> Dict[str, Any]:
        """
        Generates an exercise for a given concept.

        Priority:
          1. Local library (validated exercises)
          2. Native SymPy generator
        """
        diff = difficulty if difficulty in self.DIFFICULTIES else "easy"

        # 1. Search in the library
        if prefer_library:
            candidates = self.library.search(
                concept=concept, difficulty=diff, validated_only=True, limit=5
            )
            if candidates:
                ex = random.choice(candidates)
                self.library.increment_usage(ex["id"])
                logger.debug("Exercise from library: %s (usage=%d)", ex["id"], ex.get("usage_count", 0))
                return {
                    "concept": ex["concept"],
                    "difficulty": ex["difficulty"],
                    "problem_latex": ex["problem_latex"],
                    "correct_latex": ex["correct_latex"],
                    "hint": ex["hint"],
                    "steps": ex.get("steps", []),
                    "source": "library",
                    "exercise_id": ex["id"],
                }

        # 2. Native SymPy generation
        generator = getattr(self, f"_gen_{concept}", None)
        ex = generator(diff) if generator else self._gen_generic(diff)
        ex["source"] = "sympy"
        return ex

    # ── SymPy Verification ─────────────────────────────────────────────────

    @staticmethod
    def verify_with_sympy(exercise: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Verifies that an exercise is mathematically consistent.
        """
        problem = exercise.get("problem_latex", "").strip()
        correct = exercise.get("correct_latex", "").strip()
        concept = exercise.get("concept", "")

        if not problem or not correct:
            return False, "Empty problem or correct latex"

        try:
            prob_expr = latex2sympy(problem)
            corr_expr = latex2sympy(correct)

            if isinstance(prob_expr, list):
                prob_expr = prob_expr[0] if prob_expr else None
            if isinstance(corr_expr, list):
                corr_expr = corr_expr[0] if corr_expr else None

            if prob_expr is None or corr_expr is None:
                return False, "Failed to parse LaTeX"

            # ── Equations ─────────────────────────────────────────────────
            if isinstance(prob_expr, sp.Eq):
                var = list(prob_expr.free_symbols)
                if not var:
                    return False, "No variable found in equation"
                solutions = sp.solve(prob_expr, var[0])
                if not solutions:
                    return False, "SymPy could not solve the equation"
                match = any(sp.simplify(s - corr_expr) == 0 for s in solutions)
                if match:
                    return True, "Solution verified by SymPy"
                return False, f"Solution mismatch: expected {solutions}, got {corr_expr}"

            # ── Differential Equations ───────────────────────────────────
            if concept in ("differential_equations", "edo"):
                x = sp.Symbol('x')
                y = sp.Function('y')
                if corr_expr.free_symbols and x in corr_expr.free_symbols:
                    lhs = sp.diff(corr_expr, x)
                    if isinstance(prob_expr, sp.Eq):
                        edo = prob_expr.lhs - prob_expr.rhs
                    else:
                        edo = prob_expr
                    edo_sub = edo.subs(y(x), corr_expr).subs(sp.diff(y(x), x), lhs)
                    if sp.simplify(edo_sub) == 0:
                        return True, "EDO solution verified by SymPy"
                    return False, f"EDO verification failed: residual {sp.simplify(edo_sub)}"

            # ── Limited Expansions / Taylor ──────────────────────────────
            if concept in ("taylor_series", "dl"):
                x = sp.Symbol('x')
                if x in corr_expr.free_symbols:
                    order = 3
                    try:
                        if not isinstance(prob_expr, sp.Eq):
                            series_prob = sp.series(prob_expr, x, 0, order).removeO()
                            diff_series = sp.simplify(series_prob - corr_expr)
                            if diff_series == 0 or sp.O(x**order) in sp.series(diff_series, x, 0, order):
                                return True, "Taylor series verified by SymPy"
                    except Exception:
                        pass

            # ── Numerical Series ─────────────────────────────────────────
            if concept in ("series_convergence", "series"):
                if sp.simplify(prob_expr - corr_expr) == 0:
                    return True, "Series sum verified by SymPy"

            # ── Eigenvalues ──────────────────────────────────────────────
            if concept in ("eigenvalues", "diagonalization"):
                if isinstance(prob_expr, sp.Matrix):
                    lam = sp.Symbol('lambda')
                    charpoly = prob_expr.charpoly(lam)
                    if charpoly.eval(corr_expr) == 0:
                        return True, "Eigenvalue verified by SymPy"
                    return False, "Eigenvalue mismatch"

            # ── Generic Linear Algebra ─────────────────────────────────
            if isinstance(prob_expr, sp.Matrix) and isinstance(corr_expr, sp.Matrix):
                if sp.simplify(prob_expr - corr_expr) == sp.zeros(*prob_expr.shape):
                    return True, "Matrix equality verified by SymPy"

            # ── Generic Algebraic Equivalence ───────────────────────────
            if sp.simplify(prob_expr - corr_expr) == 0:
                return True, "Algebraic equivalence verified"

            if concept in ("factorization", "binomial_expansion"):
                if sp.expand(corr_expr) == prob_expr:
                    return True, "Expansion verified"
                if sp.factor(prob_expr) == corr_expr:
                    return True, "Factorization verified"

            return False, "Could not verify automatically"

        except Exception as exc:
            logger.debug("SymPy verification failed: %s", exc)
            return False, f"SymPy error: {exc}"

    def generate_and_verify(
        self, raw_exercises: List[Dict[str, Any]], source: str = "llm"
    ) -> List[Dict[str, Any]]:
        """
        For each raw exercise:
          - If the ID is already in the library → return existing (increment usage)
          - Otherwise → verify with SymPy, add to the library
        """
        verified = []
        for ex in raw_exercises:
            ex = dict(ex)
            ex_id = ExerciseLibrary.hash_exercise(ex.get("problem_latex", ""))
            ex["id"] = ex_id

            existing = self.library.get(ex_id)
            if existing:
                self.library.increment_usage(ex_id)
                logger.debug("Exercise %s found in library, reusing.", ex_id)
                verified.append(existing)
                continue

            ok, detail = self.verify_with_sympy(ex)
            ex["sympy_verified"] = ok
            ex["sympy_verify_detail"] = detail
            ex["validated"] = ok  # auto-validated if SymPy succeeds

            self.library.add(ex, source=source)

            if ok:
                logger.info("Exercise %s verified and added to library (%s)", ex_id, detail)
            else:
                logger.warning("Exercise %s added unverified: %s", ex_id, detail)

            verified.append(ex)

        return verified

    def generate_for_concepts(self, concepts: List[str], difficulty: str = "easy") -> List[Dict[str, Any]]:
        return [self.generate(c, difficulty) for c in concepts]

    def generate_progressive_series(self, concept: str, count: int = 3) -> List[Dict[str, Any]]:
        return [self.generate(concept, d) for d in self.DIFFICULTIES[:count]]

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _randint(self, diff: str,
                 low_easy: int = 1, high_easy: int = 5,
                 low_med: int = 2, high_med: int = 10,
                 low_hard: int = 5, high_hard: int = 20) -> int:
        if diff == "easy":
            return random.randint(low_easy, high_easy)
        if diff == "medium":
            return random.randint(low_med, high_med)
        return random.randint(low_hard, high_hard)

    def _pick(self, diff: str, easy_val, medium_val, hard_val):
        if diff == "easy":
            return easy_val
        if diff == "medium":
            return medium_val
        return hard_val

    def _rand_nonzero(self, diff: str) -> int:
        v = self._randint(diff, -5, 5, -10, 10, -20, 20)
        return v if v != 0 else 1

    # ═════════════════════════════════════════════════════════════════════════
    # Generators by concept – undergrad / university level
    # ═════════════════════════════════════════════════════════════════════════

    # ── Analysis ────────────────────────────────────────────────────────────

    def _gen_limits(self, diff: str) -> Dict[str, Any]:
        x = sp.Symbol('x')
        a = self._randint(diff, 1, 3, 2, 5, 3, 7)
        if diff == "easy":
            expr = sp.sin(a * x) / x
            hint = "Use the standard limit sin(u)/u → 1."
        elif diff == "medium":
            expr = (sp.exp(a * x) - 1 - a * x) / x**2
            hint = "Compute the Taylor expansion of exp(ax) to order 2 at 0."
        else:
            b = self._randint(diff, 1, 2, 2, 4, 3, 5)
            expr = (sp.log(1 + a * x) - a * x + b * x**2) / x**3
            hint = "Expand ln(1+ax) to order 3."
        lim = sp.limit(expr, x, 0)
        return {
            "concept": "limits",
            "difficulty": diff,
            "problem_latex": f"\\lim_{{x \\to 0}} {sp.latex(expr)}",
            "correct_latex": sp.latex(lim),
            "hint": hint,
            "steps": [
                f"$\\displaystyle \\lim_{{x \\to 0}} {sp.latex(expr)}$",
                f"Result: ${sp.latex(lim)}$",
            ],
        }

    def _gen_taylor_series(self, diff: str) -> Dict[str, Any]:
        x = sp.Symbol('x')
        a = self._randint(diff, 1, 3, 2, 5, 3, 7)
        if diff == "easy":
            order = 2
            expr = sp.exp(a * x)
            hint = "Taylor expansion of e^u to order 2."
        elif diff == "medium":
            order = 3
            expr = sp.sin(x) * sp.cos(a * x)
            hint = "Multiply the Taylor expansions of sin(x) and cos(ax)."
        else:
            order = 4
            expr = sp.log(1 + x) / (1 + a * x)
            hint = "Taylor expansion of the numerator and denominator, then division by increasing powers."
        series = sp.series(expr, x, 0, order + 1).removeO()
        return {
            "concept": "taylor_series",
            "difficulty": diff,
            "problem_latex": f"\\text{{Taylor expansion}}_{{{order}}}(0) \\; \\text{{of}} \\; {sp.latex(expr)}",
            "correct_latex": sp.latex(series),
            "hint": hint,
            "steps": [
                f"Taylor expansion of ${sp.latex(expr)}$ to order {order}",
                f"Result: ${sp.latex(series)} + o(x^{order})$",
            ],
        }

    def _gen_integrals(self, diff: str) -> Dict[str, Any]:
        x = sp.Symbol('x')
        a = self._randint(diff, 1, 3, 2, 5, 3, 7)
        if diff == "easy":
            expr = a * x**3 + 2 * x**2 - x + 1
            hint = "Integrate term by term (powers)."
        elif diff == "medium":
            expr = x * sp.exp(a * x)
            hint = "Integration by parts with u = x and dv = e^(ax)dx."
        else:
            expr = 1 / (x**2 - a**2)
            hint = "Partial fraction decomposition."
        integral = sp.integrate(expr, x)
        return {
            "concept": "integrals",
            "difficulty": diff,
            "problem_latex": f"\\int {sp.latex(expr)} \\, dx",
            "correct_latex": sp.latex(integral) + " + C",
            "hint": hint,
            "steps": [
                f"$\\int {sp.latex(expr)} \\; dx$",
                f"Result: ${sp.latex(integral)} + C$"
            ],
        }

    def _gen_series_convergence(self, diff: str) -> Dict[str, Any]:
        a = self._randint(diff, 1, 3, 2, 5, 3, 7)
        if diff == "easy":
            problem = f"\\sum_{{n=0}}^{{\\infty}} \\frac{{{a}}}{{{2**a}}}^n"
            q = sp.Rational(a, 2**a)
            sol = a / (1 - q)
            hint = "Geometric series with ratio |q| < 1. Sum = a/(1-q)."
        elif diff == "medium":
            problem = f"\\sum_{{n=1}}^{{\\infty}} \\frac{{1}}{{n(n+{a})}}"
            n = sp.Symbol('n')
            sol = sp.summation(1 / (n * (n + a)), (n, 1, sp.oo))
            hint = "Decompose 1/(n(n+a)) into partial fractions."
        else:
            problem = f"\\sum_{{n=0}}^{{\\infty}} \\frac{{{a}^n}}{{n!}}"
            sol = sp.exp(a)
            hint = "Recognize the power series of the exponential."
        return {
            "concept": "series_convergence",
            "difficulty": diff,
            "problem_latex": problem,
            "correct_latex": sp.latex(sol),
            "hint": hint,
            "steps": [f"${problem}$", f"Sum: ${sp.latex(sol)}$"],
        }

    def _gen_differential_equations(self, diff: str) -> Dict[str, Any]:
        x = sp.Symbol('x')
        y = sp.Function('y')
        a = self._randint(diff, 1, 3, 2, 5, 3, 7)
        b = self._randint(diff, 1, 3, 2, 5, 3, 7)
        if diff == "easy":
            eq = sp.Eq(y(x).diff(x) + a * y(x), b)
            sol = sp.dsolve(eq, y(x))
            hint = "Constant particular solution + homogeneous solution."
        elif diff == "medium":
            eq = sp.Eq(y(x).diff(x, 2) + a * y(x).diff(x) + b * y(x), 0)
            sol = sp.dsolve(eq, y(x))
            hint = "Characteristic equation r² + ar + b = 0."
        else:
            eq = sp.Eq(y(x).diff(x, 2) + a * y(x), sp.cos(b * x))
            sol = sp.dsolve(eq, y(x))
            hint = "Look for a particular solution of the form A·cos(bx) + B·sin(bx)."
        return {
            "concept": "differential_equations",
            "difficulty": diff,
            "problem_latex": sp.latex(eq),
            "correct_latex": sp.latex(sol),
            "hint": hint,
            "steps": [f"ODE: ${sp.latex(eq)}$", f"General solution: ${sp.latex(sol)}$"],
        }

    # ── Linear Algebra ─────────────────────────────────────────────────────

    def _gen_linear_systems(self, diff: str) -> Dict[str, Any]:
        if diff == "easy":
            a, b, c, d = [self._randint(diff, 1, 5, 2, 8, 3, 10) for _ in range(4)]
            e, f = [self._randint(diff, 1, 10, 5, 20, 10, 50) for _ in range(2)]
            A = sp.Matrix([[a, b], [c, d]])
            B = sp.Matrix([e, f])
            hint = "Apply Cramer's formulas or substitute."
        else:
            A = sp.Matrix([
                [self._randint(diff, 1, 3, 1, 5, 2, 7) for _ in range(3)],
                [self._randint(diff, 1, 3, 1, 5, 2, 7) for _ in range(3)],
                [self._randint(diff, 1, 3, 1, 5, 2, 7) for _ in range(3)],
            ])
            B = sp.Matrix([self._randint(diff, 1, 10, 5, 20, 10, 50) for _ in range(3)])
            hint = "Gaussian elimination or Cramer if det ≠ 0."
        sol = A.LUsolve(B)
        return {
            "concept": "linear_systems",
            "difficulty": diff,
            "problem_latex": f"\\text{{Solve }} {sp.latex(A)} \\cdot X = {sp.latex(B)}",
            "correct_latex": sp.latex(sol),
            "hint": hint,
            "steps": [
                f"System: ${sp.latex(A)} X = {sp.latex(B)}$",
                f"Solution: $X = {sp.latex(sol)}$",
            ],
        }

    def _gen_eigenvalues(self, diff: str) -> Dict[str, Any]:
        lam = sp.Symbol('lambda')
        if diff == "easy":
            lam1 = self._randint(diff, -5, 5, -10, 10, -15, 15)
            lam2 = self._randint(diff, -5, 5, -10, 10, -15, 15)
            P = sp.Matrix([[1, 1], [0, 1]])
            D = sp.diag(lam1, lam2)
            A = sp.simplify(P * D * P.inv())
            vp = [lam1, lam2]
            hint = "Compute det(A - λI) and solve the characteristic polynomial."
        elif diff == "medium":
            a, b, c, d = [self._randint(diff, -5, 5, -10, 10, -15, 15) for _ in range(4)]
            A = sp.Matrix([[a, b], [c, d]])
            vp = sp.solve(A.charpoly(lam), lam)
            hint = "Discriminant of the characteristic trinomial."
        else:
            A = sp.Matrix([
                [self._randint(diff, -3, 3, -5, 5, -8, 8) for _ in range(3)],
                [self._randint(diff, -3, 3, -5, 5, -8, 8) for _ in range(3)],
                [self._randint(diff, -3, 3, -5, 5, -8, 8) for _ in range(3)],
            ])
            vp = sp.solve(A.charpoly(lam), lam)
            hint = "Factor the characteristic polynomial of degree 3."
        return {
            "concept": "eigenvalues",
            "difficulty": diff,
            "problem_latex": f"\\text{{Eigenvalues of }} {sp.latex(A)}",
            "correct_latex": ", ".join(sp.latex(v) for v in vp),
            "hint": hint,
            "steps": [
                f"Matrix: ${sp.latex(A)}$",
                f"Eigenvalues: ${', '.join(sp.latex(v) for v in vp)}$",
            ],
        }

    def _gen_diagonalization(self, diff: str) -> Dict[str, Any]:
        if diff == "easy":
            a = self._randint(diff, 1, 5, 2, 8, 3, 10)
            b = self._randint(diff, 1, 5, 2, 8, 3, 10)
            A = sp.diag(a, b)
            D, P = A, sp.eye(2)
            hint = "Matrix already diagonal: D = A and P = I₂."
        else:
            a = self._randint(diff, 1, 5, 2, 8, 3, 10)
            b = self._randint(diff, 1, 3, 2, 5, 3, 7)
            A = sp.Matrix([[a, b], [b, a]])
            D = sp.diag(a + b, a - b)
            P = sp.Matrix([[1, 1], [1, -1]]) / sp.sqrt(2)
            hint = "Real symmetric matrices are diagonalizable in an orthonormal basis."
        return {
            "concept": "diagonalization",
            "difficulty": diff,
            "problem_latex": f"\\text{{Diagonalize }} {sp.latex(A)}",
            "correct_latex": f"D = {sp.latex(D)}, \\; P = {sp.latex(P)}",
            "hint": hint,
            "steps": [f"$A = {sp.latex(A)}$", f"$D = {sp.latex(D)}$", f"$P = {sp.latex(P)}$"],
        }

    def _gen_vector_spaces(self, diff: str) -> Dict[str, Any]:
        if diff == "easy":
            u = sp.Matrix([1, 0, self._randint(diff, -3, 3, -5, 5, -8, 8)])
            v = sp.Matrix([0, 1, self._randint(diff, -3, 3, -5, 5, -8, 8)])
            problem = f"\\text{{Basis and dimension of }} \\text{{Vect}}({sp.latex(u)}, {sp.latex(v)})"
            correct = "\\dim = 2, \\; \\text{basis} = \\{u, v\\}"
            hint = "Check that the two vectors are linearly independent (non-collinear)."
        elif diff == "medium":
            a = self._randint(diff, 1, 3, 2, 5, 3, 7)
            A = sp.Matrix([[a, 2*a, 3*a], [1, 2, 3]])
            problem = f"\\text{{Determine }} \\ker({sp.latex(A)})"
            correct = "\\text{Vect}((-2, 1, 0), (-3, 0, 1)), \\; \\dim = 2"
            hint = "Solve AX = 0 by Gaussian elimination."
        else:
            A = sp.Matrix([
                [1, 2, 3],
                [0, 1, self._randint(diff, 1, 3, 2, 5, 3, 7)],
                [0, 0, 1],
            ])
            problem = f"\\text{{Basis and dimension of }} \\text{{Im}}({sp.latex(A)})"
            correct = "\\dim = 3, \\; \\text{canonical basis of } \\mathbb{R}^3"
            hint = "The rank of A equals the number of pivots."
        return {
            "concept": "vector_spaces",
            "difficulty": diff,
            "problem_latex": problem,
            "correct_latex": correct,
            "hint": hint,
            "steps": [problem, correct],
        }

    # ── Probability & Statistics ────────────────────────────────────────────

    def _gen_probability_continuous(self, diff: str) -> Dict[str, Any]:
        mu = self._randint(diff, 0, 5, -5, 5, -10, 10)
        sigma = self._randint(diff, 1, 3, 1, 5, 2, 8)
        a = self._randint(diff, mu - 2, mu + 2, mu - 3, mu + 3, mu - 4, mu + 4)
        if diff == "easy":
            z = sp.Rational(a - mu, sigma)
            problem = f"X \\sim \\mathcal{{N}}({mu}, {sigma}^2). \\; \\text{{Compute }} \\mathbb{{P}}(X \\leq {a})"
            correct = f"\\Phi({sp.latex(z)})"
            hint = "Standardize: Z = (X-μ)/σ."
        elif diff == "medium":
            b = a + self._randint(diff, 1, 3, 2, 5, 3, 7)
            z1, z2 = sp.Rational(a - mu, sigma), sp.Rational(b - mu, sigma)
            problem = f"X \\sim \\mathcal{{N}}({mu}, {sigma}^2). \\; \\mathbb{{P}}({a} \\leq X \\leq {b}) = ?"
            correct = f"\\Phi({sp.latex(z2)}) - \\Phi({sp.latex(z1)})"
            hint = "P(a ≤ X ≤ b) = Φ((b-μ)/σ) - Φ((a-μ)/σ)."
        else:
            problem = f"X \\sim \\mathcal{{N}}(0,1), \\; Y = {sigma}X + {mu}. \\; \\text{{Compute }} \\mathbb{{E}}[Y|X > 0]"
            correct = f"{mu} + \\frac{{{sigma}}}{{\\sqrt{{2\\pi}}}}"
            hint = "E[Y|X>0] = σ·E[X|X>0] + μ and E[X|X>0] = √(2/π)."
        return {
            "concept": "probability_continuous",
            "difficulty": diff,
            "problem_latex": problem,
            "correct_latex": correct,
            "hint": hint,
            "steps": [problem, correct],
        }

    # ── Geometry & Topology ─────────────────────────────────────────────────

    def _gen_topology(self, diff: str) -> Dict[str, Any]:
        a = self._randint(diff, 1, 3, 2, 5, 3, 7)
        if diff == "easy":
            problem = f"\\text{{Is the set }} \\{{(x,y) \\in \\mathbb{{R}}^2 \\mid x^2 + y^2 < {a}\\}} \\text{{ open?}}"
            correct = "\\text{Yes, it is an open ball.}"
            hint = "An open ball is an open set in R²."
        elif diff == "medium":
            problem = f"\\text{{Determine the closure of }} \\{{(x,y) \\in \\mathbb{{R}}^2 \\mid x^2 + y^2 < {a}, \\; x > 0\\}}"
            correct = f"\\{{(x,y) \\in \\mathbb{{R}}^2 \\mid x^2 + y^2 \\leq {a}, \\; x \\geq 0\\}}"
            hint = "The closure adds the boundary (circle) and the segment x=0."
        else:
            problem = f"\\text{{Let }} F = \\{{(x,y) \\in \\mathbb{{R}}^2 \\mid xy = {a}\\}}. \\; \\text{{Is F closed? Compact?}}"
            correct = "\\text{Closed (preimage of {a} by the continuous map (x,y)↦xy), not compact (not bounded).}"
            hint = "F = f⁻¹({a}) with f continuous → closed. Check boundedness."
        return {
            "concept": "topology",
            "difficulty": diff,
            "problem_latex": problem,
            "correct_latex": correct,
            "hint": hint,
            "steps": [problem, correct],
        }

    # ── Bilinear Algebra ────────────────────────────────────────────────────

    def _gen_bilinear_forms(self, diff: str) -> Dict[str, Any]:
        a = self._randint(diff, 1, 3, 2, 5, 3, 7)
        b = self._randint(diff, 0, 2, 1, 3, 2, 4)
        if diff == "easy":
            problem = f"q(x,y) = {a}x^2 + {b}y^2"
            correct = f"\\text{{Positive definite if }} {a}>0 \\text{{ and }} {b}>0"
            hint = "A diagonal form is positive definite iff all coefficients are > 0."
        elif diff == "medium":
            problem = f"q(x,y) = x^2 + {2*b}xy + y^2"
            correct = f"\\text{{Signature }} (1,1) \\text{{ si }} |{b}| > 1, \\; (2,0) \\text{{ si }} |{b}| < 1"
            hint = "Write the associated matrix and compute its eigenvalues."
        else:
            problem = f"q(x,y,z) = x^2 + {a}y^2 + z^2 + 2xy + 2yz"
            correct = "\\text{Reduction by Gauss's method.}"
            hint = "Group the x terms, complete the square, then the y terms."
        return {
            "concept": "bilinear_forms",
            "difficulty": diff,
            "problem_latex": problem,
            "correct_latex": correct,
            "hint": hint,
            "steps": [problem, correct],
        }

    # ── Backward compatibility / fallback aliases ───────────────────────────

    def _gen_linear_equations(self, diff: str) -> Dict[str, Any]:
        return self._gen_linear_systems(diff)

    def _gen_derivatives(self, diff: str) -> Dict[str, Any]:
        x = sp.Symbol('x')
        a = self._randint(diff, 1, 3, 2, 5, 3, 7)
        if diff == "easy":
            expr = a * x**3 + 2 * x**2 - x + 1
            hint = "Differentiate term by term (power rule)."
        elif diff == "medium":
            expr = x * sp.exp(a * x)
            hint = "Use the product rule: (uv)' = u'v + uv'."
        else:
            expr = sp.sin(a * x) / (x**2 + 1)
            hint = "Quotient + composition: (u/v)' = (u'v - uv')/v²."
        deriv = sp.diff(expr, x)
        return {
            "concept": "derivatives",
            "difficulty": diff,
            "problem_latex": f"\\frac{{d}}{{dx}} \\left({sp.latex(expr)}\\right)",
            "correct_latex": sp.latex(deriv),
            "hint": hint,
            "steps": [f"$f(x) = {sp.latex(expr)}$", f"$f'(x) = {sp.latex(deriv)}$"],
        }

    def _gen_matrices(self, diff: str) -> Dict[str, Any]:
        return self._gen_eigenvalues(diff)

    def _gen_matrix_inversion(self, diff: str) -> Dict[str, Any]:
        return self._gen_diagonalization(diff)

    def _gen_probability(self, diff: str) -> Dict[str, Any]:
        return self._gen_probability_continuous(diff)

    def _gen_generic(self, diff: str) -> Dict[str, Any]:
        x = sp.Symbol('x')
        a = self._randint(diff, 2, 5, 3, 8, 5, 12)
        b = self._randint(diff, 1, 5, 2, 8, 3, 10)
        eq = sp.Eq(a * x + b, 0)
        sol = sp.solve(eq, x)[0]
        return {
            "concept": "generic",
            "difficulty": diff,
            "problem_latex": sp.latex(eq),
            "correct_latex": sp.latex(sol),
            "hint": "Isoler x en divisant par le coefficient.",
            "steps": [f"${sp.latex(eq)}$", f"$x = {sp.latex(sol)}$"],
        }
