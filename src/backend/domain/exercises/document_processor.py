"""
DocumentProcessor – Extraction of key concepts from an imported document.

Receives raw text (extracted from a PDF or OCR image), identifies the
mathematical concepts present, and adjusts the ACT-R declarative memory
(StudentModel) to focus learning on these concepts.
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from core.llm_client import LLMClient

logger = logging.getLogger(__name__)


# Heuristic mapping: keywords → ACT-R chunk (undergrad / university level)
MATH_KEYWORDS = {

    "limits": ["limit", "tends to", "asymptotic", "indeterminate form", "taylor expansion"],
    "taylor_series": ["taylor series", "taylor polynomial", "maclaurin", "remainder"],
    "integrals": ["integral", "integration", "antiderivative", "area under", "integration by parts", "substitution"],
    "series_convergence": ["series", "convergent", "sum", "telescoping", "geometric series", "power series", "radius"],
    "differential_equations": ["équation différentielle", "edo", "lineaire", "second membre", "homogène", "wronskien",
                               "differential equation", "ode", "linear", "particular solution", "homogeneous", "wronskian"],

    "linear_systems": ["linear system", "cramer's rule", "pivot", "gauss", "linear equation", "solve"],
    "eigenvalues": ["eigenvalue", "eigenvector", "characteristic polynomial", "spectrum", "diagonalizable"],
    "diagonalization": ["diagonalization", "diagonalizable matrix", "eigenbasis", "spectral projector"],
    "vector_spaces": ["vector space", "dimension", "basis", "subspace", "kernel", "image", "rank"],
    "matrices": ["matrix", "matrices", "determinant", "det", "inverse", "trace"],

    "probability_continuous": ["normal distribution", "density", "continuous random variable", "gaussian", "pdf"],
    "probability": ["probability", "random", "expectation", "variance", "distribution", "bernoulli"],
    "statistics": ["statistics", "mean", "standard deviation", "median", "quantile", "regression", "estimator"],

    "topology": ["topology", "open set", "closed", "compact", "closure", "ball", "neighborhood"],

    "bilinear_forms": ["quadratic form", "bilinear form", "signature", "inertia law", "symmetric"],

    "derivatives": ["derivative", "differentiation", "gradient", "jacobian", "slope"],
    "trigonometry": ["trigonometry", "sine", "cosine", "tangent", "angle", "radian"],
    "complex_numbers": ["complex number", "imaginary", "modulus", "argument", "conjugate", "holomorphic"],
    "logarithms": ["logarithm", "ln", "log", "exponential", "exp", "e^x"],
}



class DocumentProcessor:
    """
    Analyzes a document and extracts mathematical concepts to
    personalize the learner model.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    # ── Main Extraction ─────────────────────────────────────────────────────

    async def process_document_async(self, text: str, student_model=None) -> Dict[str, Any]:
        """
        Full pipeline: raw text → concepts → student model update.
        Returns {"concepts": [...]}.
        """
        concepts = self._extract_with_keywords(text)

        if student_model:
            for concept in concepts:
                student_model.record_action(f"doc_concept_{concept['name']}")

        return {"concepts": concepts}

    async def extract_concepts_async(self, text: str) -> List[Dict[str, Any]]:
        return self._extract_with_keywords(text)

 
    # ── Private Methods ─────────────────────────────────────────────────────

    def _extract_with_keywords(self, text: str) -> List[Dict[str, Any]]:
        """Heuristic fallback using keyword dictionary."""
        text_lower = text.lower()
        found = []

        for concept_name, keywords in MATH_KEYWORDS.items():
            score = 0
            for kw in keywords:
                count = len(re.findall(rf"\b{re.escape(kw.lower())}\b", text_lower))
                score += count
            if score > 0:
                # Normalize score (max ~10 to avoid outliers)
                confidence = min(score / 3.0, 1.0)
                found.append({
                    "name": concept_name,
                    "confidence": round(confidence, 2),
                    "keywords_matched": score,
                })

        # Sort by descending confidence
        found.sort(key=lambda x: x["confidence"], reverse=True)
        return found


    def generate_focus_message(self, concepts: List[Dict[str, Any]]) -> str:
        """Generates a pedagogical welcome message after document analysis."""
        if not concepts:
            return "Document imported. I couldn't detect specific math topics — feel free to ask anything!"

        top = concepts[:3]
        names = [c["name"].replace("_", " ") for c in top]
        return (
            f"📄 Document analyzed! I'll focus our session on: **{', '.join(names)}**.\n"
            "These topics are now prioritized in your learning model. "
            "Ready to start with an exercise?"
        )
