"""
LLMClient – Native Groq client for text (reasoning) and vision.

Configuration (.env) :
    GROQ_API_KEY=gsk_...
"""

import base64
import io
import logging
import os
import re
from typing import Optional, List, Dict

from PIL import Image

try:
    from groq import AsyncGroq
    _HAS_GROQ = True
except ImportError:
    _HAS_GROQ = False

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

_REASONING_MODEL = "openai/gpt-oss-120b"
_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class LLMClient:
    """Native Groq client with mock fallback."""

    SYSTEM_PROMPT = (
        "You are an expert mathematics tutor named ITIM. "
        "Your goal is to help students learn by giving hints, not direct answers. "
        "Be concise, encouraging, and adapt your explanation to the student's level. "
        "Respond in the same language as the student's question (English by default)."
    )

    def __init__(self, force_mock: bool = False):
        self.mock_counter = 0
        self._force_mock = force_mock
        self._client: Optional[AsyncGroq] = None
        self._has_llm = False

        if force_mock or not _HAS_GROQ or not _GROQ_API_KEY:
            if not force_mock:
                logger.warning(
                    "No GROQ_API_KEY found. LLMClient will run in MOCK mode."
                )
            return

        self._client = AsyncGroq(api_key=_GROQ_API_KEY)
        self._has_llm = True
        logger.info("[LLMClient] Groq API configured")

    def is_available(self) -> bool:
        return not self._force_mock and self._has_llm

    # ── Text / Reasoning ─────────────────────────────────────────────────────

    async def generate(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate a pedagogical response via the Groq reasoning model."""
        if not self._has_llm or self._client is None:
            self.mock_counter += 1
            return (
                f"[MOCK_LLM_{self.mock_counter}] No LLM backend available. "
                "Set GROQ_API_KEY to enable the tutor."
            )

        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt or self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

        try:
            response = await self._client.chat.completions.create(
                model=_REASONING_MODEL,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_tokens,
                reasoning_effort="medium",
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"[LLM ERROR] {type(e).__name__}: {e}"

    async def explain_buggy_rule(
        self,
        rule_name: str,
        rule_description: str,
        student_answer: str,
    ) -> str:
        """Generate a natural explanation for a detected buggy rule."""
        prompt = (
            f"A student made a common mistake called '{rule_name}'.\n"
            f"Description of the misconception: {rule_description}\n"
            f"Student's answer: {student_answer}\n"
            f"Explain gently why this is incorrect and how to avoid it."
        )
        return await self.generate(prompt, temperature=0.7, max_tokens=300)

    # ── Vision ───────────────────────────────────────────────────────────────

    @property
    def has_vision(self) -> bool:
        """True if the backend is available for vision."""
        return self.is_available()

    async def ocr_document(self, image) -> Optional[str]:
        """
        General-purpose OCR for a scanned document/image.
        Extracts text + mathematical expressions in LaTeX.
        """
        if not self._has_llm or self._client is None:
            return None

        # Resize if too large to respect the 4MB Groq limit
        max_dim = 1024
        if max(image.size) > max_dim:
            ratio = max_dim / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{b64}"

        system_prompt = (
            "You are an expert OCR engine for educational documents. "
            "Extract ALL text and mathematical expressions from the image. "
            "Preserve the structure: paragraphs, numbered exercises, equations. "
            "For mathematical expressions, output them in LaTeX format between $...$ or $$...$$. "
            "Return ONLY the extracted text and LaTeX, no commentary, no markdown."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract all text and mathematical expressions from this document image. Preserve the structure and format equations in LaTeX.",
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]

        try:
            response = await self._client.chat.completions.create(
                model=_VISION_MODEL,
                messages=messages,
                temperature=0.2,
                max_completion_tokens=1024,
            )
            raw = response.choices[0].message.content.strip()
            if raw.upper() == "NONE":
                return None
            return raw
        except Exception as e:
            logger.error("[LLMClient ocr_document] ERROR: %s", e)
            return None

    async def image_to_latex(self, image) -> Optional[str]:
        """
        Send a PIL image to the Groq vision model and return the extracted LaTeX.
        Uses meta-llama/llama-4-scout-17b-16e-instruct.
        """
        if not self._has_llm or self._client is None:
            return None

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"

        system_prompt = (
            "You are an expert mathematical OCR engine. "
            "Your ONLY job is to look at the handwritten mathematical expression in the image "
            "and output its exact LaTeX representation. "
            "Rules:\n"
            "1. Return ONLY the raw LaTeX code, no markdown, no explanation, no quotes.\n"
            "2. Use standard LaTeX: \\frac for fractions, \\sqrt for roots, ^ for exponents, _ for subscripts.\n"
            "3. If you see an equation with =, include the equals sign.\n"
            "4. If the image contains multiple lines or separate expressions, preserve them on separate lines using \\ or by placing each expression on its own line.\n"
            "5. If the image is blank or unreadable, return exactly: NONE\n"
            "6. Do NOT add ANY text before or after the LaTeX."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Read the handwritten mathematical expression in this image and output ONLY its LaTeX code. If there are multiple lines or separate expressions, keep them on separate lines. Nothing else.",
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]

        try:
            response = await self._client.chat.completions.create(
                model=_VISION_MODEL,
                messages=messages,
                temperature=0.2,
                max_completion_tokens=256,
            )
            raw = response.choices[0].message.content.strip()
            return self._clean_latex(raw)
        except Exception as e:
            logger.error("[LLMClient vision] ERROR: %s", e)
            return None

    @staticmethod
    def _clean_latex(raw: str) -> Optional[str]:
        """Clean the LLM response to extract pure LaTeX."""
        if not raw or raw.upper() == "NONE":
            return None

        code_block = re.search(r"```(?:latex)?\s*(.*?)```", raw, re.DOTALL)
        if code_block:
            return code_block.group(1).strip()

        inline = re.search(r"\$\$(.*?)\$\$", raw, re.DOTALL)
        if inline:
            return inline.group(1).strip()

        inline_single = re.search(r"\$(.*?)\$", raw, re.DOTALL)
        if inline_single:
            return inline_single.group(1).strip()

        prefix = re.search(r"(?:latex|expression|is)\s*[:=]\s*(.+)", raw, re.IGNORECASE | re.DOTALL)
        if prefix:
            return prefix.group(1).strip()

        return raw.strip()
