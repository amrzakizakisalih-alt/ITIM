"""
BuggyRuleLearner – Incremental learning of error rules.

When the LLM discovers a new buggy rule (area not covered by hard-coded
rules), this module:
  1. Stores the discovery (LaTeX example + description).
  2. Counts occurrences.
  3. After N occurrences (default 3), promotes the rule to a local rule
     using an example-based matcher.
  4. Persists in a JSON file to survive restarts.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import sympy as sp
from latex2sympy2 import latex2sympy

from core.persistence import SQLiteStore

logger = logging.getLogger(__name__)

DEFAULT_LEARNED_PATH = os.path.join(os.path.dirname(__file__), "buggy_rules_learned.db")
MIN_OCCURRENCES_FOR_VALIDATION = 3


# ── AST Helpers (factored into ast_utils) ────────────────────────────────────

from domain.math.ast_utils import sympy_to_ast, expr_to_generic_ast, match_generic_ast


# ── BuggyRule ────────────────────────────────────────────────────────────────


class BuggyRule:
    """Typical cognitive error rule (buggy rule)."""

    def __init__(
        self,
        name: str,
        description: str,
        checker,
        weight: float = 1.0,
        tags: Optional[List[str]] = None,
    ):
        self.name = name
        self.description = description
        self.checker = checker
        self.weight = weight
        self.tags = tags or []

    def check(self, expr) -> bool:
        try:
            return self.checker(expr)
        except Exception as exc:
            logger.debug("Buggy rule '%s' checker failed: %s", self.name, exc)
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "weight": self.weight,
            "tags": self.tags,
        }


# ── Learner ──────────────────────────────────────────────────────────────────


class BuggyRuleLearner(SQLiteStore):
    """
    Incremental learning of buggy rules.
    """

    _TABLE = "buggy_rules"
    _PK = "name"
    _COLUMNS = [
        "name", "description", "examples", "count", "weight",
        "tags", "validated", "first_seen", "last_seen",
    ]
    _CREATE_SQL = """
        CREATE TABLE IF NOT EXISTS buggy_rules (
            name TEXT PRIMARY KEY,
            description TEXT NOT NULL DEFAULT '',
            examples TEXT NOT NULL DEFAULT '[]',
            count INTEGER NOT NULL DEFAULT 0,
            weight REAL NOT NULL DEFAULT 0.7,
            tags TEXT NOT NULL DEFAULT '[]',
            validated INTEGER NOT NULL DEFAULT 0,
            first_seen REAL NOT NULL DEFAULT 0,
            last_seen REAL NOT NULL DEFAULT 0
        )
    """

    def __init__(self, storage_path: Optional[str] = None):
        raw_path = storage_path or DEFAULT_LEARNED_PATH
        if raw_path.endswith(".json"):
            raw_path = raw_path[:-5] + ".db"
        super().__init__(raw_path)
        self._rules: Dict[str, Dict[str, Any]] = {}
        self._ensure_table(self._CREATE_SQL)
        self._maybe_migrate_json_legacy()
        self._load()

    def _maybe_migrate_json_legacy(self) -> None:
        json_path = self.storage_path[:-3] + ".json" if self.storage_path.endswith(".db") else self.storage_path + ".json"
        self._migrate_json(json_path, lambda item: self._upsert_item(item))

    def _upsert_item(self, rule: Dict[str, Any]) -> None:
        self._upsert(
            self._TABLE,
            self._COLUMNS,
            self._PK,
            (
                rule["name"], rule["description"], json.dumps(rule.get("examples", [])),
                rule.get("count", 0), rule.get("weight", 0.7), json.dumps(rule.get("tags", [])),
                int(rule.get("validated", False)), rule.get("first_seen", 0), rule.get("last_seen", 0),
            ),
        )

    def _load(self):
        for row in self._fetch_all(self._TABLE):
            rule = dict(row)
            rule["validated"] = bool(rule["validated"])
            rule["examples"] = json.loads(rule["examples"]) if rule["examples"] else []
            rule["tags"] = json.loads(rule["tags"]) if rule["tags"] else []
            self._rules[rule["name"]] = rule
        logger.info("Loaded %d learned rule(s) from %s", len(self._rules), self.storage_path)

    def persist(self):
        """Writes learned rules to disk."""
        try:
            for rule in self._rules.values():
                self._upsert_item(rule)
            logger.info("Persisted %d learned rule(s)", len(self._rules))
        except Exception as exc:
            logger.error("Failed to persist learned rules: %s", exc)

    # ── Discovery ──────────────────────────────────────────────────────────

    def record_discovery(
        self,
        name: str,
        description: str,
        user_latex: str,
        weight: float = 0.7,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Records an LLM discovery. Increments the occurrence counter
        and adds the LaTeX example to the list.
        """
        now = time.time()
        if name not in self._rules:
            self._rules[name] = {
                "name": name,
                "description": description,
                "examples": [],
                "count": 0,
                "weight": weight,
                "tags": list(tags or ["llm_discovered"]),
                "validated": False,
                "first_seen": now,
                "last_seen": now,
            }

        rule = self._rules[name]
        rule["count"] += 1
        rule["last_seen"] = now
        if user_latex not in rule["examples"]:
            rule["examples"].append(user_latex)

        # Auto-validation by voting
        if not rule["validated"] and rule["count"] >= MIN_OCCURRENCES_FOR_VALIDATION:
            rule["validated"] = True
            logger.info("Rule '%s' promoted to validated (count=%d)", name, rule["count"])

        self.persist()
        return dict(rule)

    # ── Conversion to BuggyRule ───────────────────────────────────────────

    def get_learned_buggy_rules(self) -> List[BuggyRule]:
        """
        Returns the *validated* rules as BuggyRule objects
        with a checker based on stored examples.
        """
        rules: List[BuggyRule] = []
        for item in self._rules.values():
            if not item.get("validated"):
                continue
            examples = item.get("examples", [])
            generic_patterns = self._build_generic_patterns(examples)

            def make_checker(patterns, exs):
                def checker(expr: sp.Expr) -> bool:
                    # 1. Exact match by simplification
                    for ex_str in exs:
                        try:
                            ex = latex2sympy(ex_str)
                            if isinstance(ex, list):
                                ex = ex[0] if ex else None
                            if ex is not None and sp.simplify(expr - ex) == 0:
                                return True
                        except Exception:
                            continue
                    # 2. Generic structural match
                    try:
                        ast = sympy_to_ast(expr)
                        for pat in patterns:
                            if match_generic_ast(ast, pat):
                                return True
                    except Exception:
                        pass
                    return False
                return checker

            rules.append(
                BuggyRule(
                    name=item["name"],
                    description=item["description"],
                    checker=make_checker(generic_patterns, examples),
                    weight=item.get("weight", 0.7),
                    tags=item.get("tags", ["llm_discovered"]),
                )
            )
        return rules

    def _build_generic_patterns(self, examples: List[str]) -> List[Dict[str, Any]]:
        """Builds generic ASTs from LaTeX examples."""
        patterns = []
        for ex in examples:
            try:
                expr = latex2sympy(ex)
                if isinstance(expr, list):
                    expr = expr[0] if expr else None
                if expr is not None:
                    patterns.append(expr_to_generic_ast(expr))
            except Exception:
                continue
        return patterns

    def list_pending(self) -> List[Dict[str, Any]]:
        """Lists discoveries not yet validated."""
        return [dict(r) for r in self._rules.values() if not r.get("validated")]

    def validate_rule(self, name: str) -> bool:
        """Forces manual validation of a rule."""
        if name not in self._rules:
            return False
        self._rules[name]["validated"] = True
        self._rules[name]["count"] = max(
            self._rules[name].get("count", 0),
            MIN_OCCURRENCES_FOR_VALIDATION,
        )
        self.persist()
        logger.info("Rule '%s' manually validated", name)
        return True

    def reject_rule(self, name: str) -> bool:
        """Removes a learned rule (rejection)."""
        if name not in self._rules:
            return False
        del self._rules[name]
        self.persist()
        logger.info("Rule '%s' rejected and removed", name)
        return True
