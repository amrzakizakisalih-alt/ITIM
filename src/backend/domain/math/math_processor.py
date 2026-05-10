import sympy
from PIL import Image, ImageDraw
from latex2sympy2 import latex2sympy

# pix2tex is optional (requires torch, very heavy)
try:
    from pix2tex.cli import LatexOCR
    _HAS_PIX2TEX = True
except ImportError:
    _HAS_PIX2TEX = False
    LatexOCR = None

from typing import Optional

from core.llm_client import LLMClient


class MathProcessor:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.Page_W = 794
        self.Page_H = 1123
        self.model = LatexOCR() if _HAS_PIX2TEX else None
        self.vision = llm_client

    # ── Main pipeline: strokes → PIL crop + upscale image ──────────────────
    @staticmethod
    def _normalize_strokes(strokes):
        """Accepts a list or a StrokeBuffer."""
        if hasattr(strokes, 'get_active_strokes'):
            return strokes.get_active_strokes()
        return strokes

    def render_strokes_cropped(self, strokes, padding=60, upscale=4):
        """
        Renders 'pen' strokes on a PIL crop + upscale image.
        Pure white background, thick black strokes — optimized for vision LLM OCR.
        Returns the PIL image or None.
        """
        strokes = self._normalize_strokes(strokes)
        if not strokes:
            return None

        all_x, all_y = [], []
        pen_strokes = []
        for stroke in strokes:
            if stroke.get('tool') == 'eraser':
                continue
            pts = stroke.get('points', [])
            if len(pts) < 2:
                continue
            pen_strokes.append(stroke)
            for p in pts:
                all_x.append(p.get('x', 0))
                all_y.append(p.get('y', 0))

        if not all_x or not all_y:
            return None

        min_x = max(0, min(all_x) - padding)
        min_y = max(0, min(all_y) - padding)
        max_x = min(self.Page_W, max(all_x) + padding)
        max_y = min(self.Page_H, max(all_y) + padding)

        width = max_x - min_x
        height = max_y - min_y
        if width < 10 or height < 10:
            return None

        w_us = int(width * upscale)
        h_us = int(height * upscale)

        # Pure white background — as clean as possible for OCR
        img = Image.new('RGB', (w_us, h_us), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        for stroke in pen_strokes:
            points = [(p['x'] - min_x, p['y'] - min_y) for p in stroke.get('points', [])]
            points = [(int(px * upscale), int(py * upscale)) for px, py in points]
            # Thick strokes for vision recognition
            w = max(3, int(stroke.get('width', 2)) * upscale + 3)
            draw.line(points, fill=(0, 0, 0), width=w)

        return img

