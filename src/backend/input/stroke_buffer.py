"""
StrokeBuffer – Smart stroke buffer with eraser management.

Replaces the simple list `[]` used in SessionState to:
  1. Compute bounding boxes for each stroke.
  2. Actually remove 'pen' strokes covered by an 'eraser'.
  3. Provide clean active strokes for OCR and rendering.
"""

from typing import List, Dict, Any, Optional


class StrokeBuffer:
    """
    Stroke buffer with geometric removal by the eraser.
    """

    ERASE_COVERAGE_THRESHOLD = 0.5  # a pen stroke must be covered by 50% to be deleted

    def __init__(self):
        self._strokes: List[Dict[str, Any]] = []

    # ── Add / Eraser ────────────────────────────────────────────────────────

    def add(self, stroke: dict) -> None:
        """Adds a stroke. If it's an eraser, removes covered strokes."""
        import time
        if stroke.get("tool") == "eraser":
            self._apply_eraser(stroke)
        else:
            self._strokes.append({
                "stroke": stroke,
                "bbox": self._compute_bbox(stroke),
                "timestamp": stroke.get("timestamp", time.time()),
            })

    def _apply_eraser(self, eraser_stroke: dict) -> None:
        """Removes pen strokes whose at least one point is close to the eraser."""
        eraser_points = eraser_stroke.get("points", [])
        if not eraser_points:
            return
        eraser_width = eraser_stroke.get("width", 20)
        threshold = eraser_width / 2.0
        eraser_bbox = self._compute_bbox(eraser_stroke)

        new_strokes = []
        for item in self._strokes:
            pen_bbox = item["bbox"]
            if not pen_bbox:
                new_strokes.append(item)
                continue

            # Quick filter: if bboxes are not close enough, we keep
            if not self._bbox_near(pen_bbox, eraser_bbox, threshold):
                new_strokes.append(item)
                continue

            # Precise point-to-point verification
            pen_points = item["stroke"].get("points", [])
            if self._any_point_near(pen_points, eraser_points, threshold):
                continue  # Stroke touched by the eraser → deleted
            new_strokes.append(item)

        self._strokes = new_strokes

    @staticmethod
    def _bbox_near(a: Dict[str, float], b: Dict[str, float], margin: float) -> bool:
        """True if two bboxes are less than `margin` apart from each other."""
        return (
            a["min_x"] <= b["max_x"] + margin
            and a["max_x"] >= b["min_x"] - margin
            and a["min_y"] <= b["max_y"] + margin
            and a["max_y"] >= b["min_y"] - margin
        )

    @staticmethod
    def _any_point_near(
        points_a: List[dict], points_b: List[dict], threshold: float
    ) -> bool:
        """True if at least one point from A is less than threshold away from a point in B."""
        th2 = threshold * threshold
        for pa in points_a:
            ax, ay = pa["x"], pa["y"]
            for pb in points_b:
                dx = ax - pb["x"]
                dy = ay - pb["y"]
                if dx * dx + dy * dy <= th2:
                    return True
        return False

    # ── Bounding Boxes ─────────────────────────────────────────────────────

    @staticmethod
    def _compute_bbox(stroke: dict) -> Optional[Dict[str, float]]:
        """Computes the bounding box [min_x, min_y, max_x, max_y] of a stroke."""
        points = stroke.get("points", [])
        if not points:
            return None
        xs = [p["x"] for p in points]
        ys = [p["y"] for p in points]
        return {
            "min_x": min(xs),
            "min_y": min(ys),
            "max_x": max(xs),
            "max_y": max(ys),
        }

    @staticmethod
    def _bbox_area(bbox: Dict[str, float]) -> float:
        return max(0.0, bbox["max_x"] - bbox["min_x"]) * max(0.0, bbox["max_y"] - bbox["min_y"])

    @staticmethod
    def _bbox_intersection_area(a: Dict[str, float], b: Dict[str, float]) -> float:
        x1 = max(a["min_x"], b["min_x"])
        y1 = max(a["min_y"], b["min_y"])
        x2 = min(a["max_x"], b["max_x"])
        y2 = min(a["max_y"], b["max_y"])
        if x2 <= x1 or y2 <= y1:
            return 0.0
        return (x2 - x1) * (y2 - y1)

    # ── Accessors ───────────────────────────────────────────────────────────

    def get_active_strokes(self) -> List[dict]:
        """Returns only non-erased strokes."""
        return [item["stroke"] for item in self._strokes]

    def get_recent_strokes(self, since_timestamp: float) -> List[dict]:
        """Returns non-erased strokes added after since_timestamp."""
        return [
            item["stroke"]
            for item in self._strokes
            if item.get("timestamp", 0) > since_timestamp
        ]

    def get_spatial_clusters(self, max_distance: float = 150.0) -> List[List[dict]]:
        """
        Groups active strokes by spatial proximity (greedy).
        Returns a list of clusters, each cluster being a list of strokes.
        """
        import math
        items = self._strokes
        if not items:
            return []

        clusters: List[Dict[str, Any]] = []
        for item in items:
            bbox = item["bbox"]
            if not bbox:
                continue
            cx = (bbox["min_x"] + bbox["max_x"]) / 2
            cy = (bbox["min_y"] + bbox["max_y"]) / 2

            placed = False
            for cluster in clusters:
                ccx, ccy = cluster["center"]
                if math.hypot(cx - ccx, cy - ccy) < max_distance:
                    cluster["items"].append(item)
                    # Recalculate the center
                    all_cx = [(i["bbox"]["min_x"] + i["bbox"]["max_x"]) / 2 for i in cluster["items"] if i["bbox"]]
                    all_cy = [(i["bbox"]["min_y"] + i["bbox"]["max_y"]) / 2 for i in cluster["items"] if i["bbox"]]
                    cluster["center"] = (sum(all_cx) / len(all_cx), sum(all_cy) / len(all_cy))
                    placed = True
                    break

            if not placed:
                clusters.append({"items": [item], "center": (cx, cy)})

        return [ [it["stroke"] for it in c["items"]] for c in clusters ]

    def clear(self) -> None:
        self._strokes.clear()

    def __len__(self) -> int:
        return len(self._strokes)

