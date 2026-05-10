"""
ast_utils – Utility functions for SymPy AST manipulation.

Centralizes SymPy → AST conversion and structural matching
to avoid duplication between MathExpert and BuggyRuleLearner.
"""

from typing import Any, Dict

import sympy as sp


def sympy_to_ast(expr) -> Dict[str, Any]:
    """Transforms a SymPy expression into a JSON-like AST."""
    if isinstance(expr, (int, float, str)):
        return {"type": type(expr).__name__, "content": str(expr)}
    node = {
        "type": getattr(expr.func, "__name__", type(expr).__name__),
        "content": str(expr),
    }
    if hasattr(expr, "args") and expr.args:
        node["children"] = [sympy_to_ast(arg) for arg in expr.args]
    return node


def expr_to_generic_ast(expr) -> Dict[str, Any]:
    """
    Transforms a SymPy expression into a **generic** AST
    (Symbol/Number leaves lose their value).
    """
    if isinstance(expr, sp.Atom):
        # Normalize numbers (One, Integer, Rational, etc.) to "Number"
        if expr.is_Number:
            return {"type": "Number"}
        return {"type": getattr(expr.func, "__name__", type(expr).__name__)}
    node = {"type": getattr(expr.func, "__name__", type(expr).__name__)}
    if hasattr(expr, "args") and expr.args:
        node["children"] = [expr_to_generic_ast(arg) for arg in expr.args]
    return node


def match_generic_ast(expr_ast: dict, generic_ast: dict) -> bool:
    """Matches a concrete AST against a generic AST (wildcards on leaves)."""
    # Numeric type normalization for matching
    expr_type = expr_ast.get("type")
    generic_type = generic_ast.get("type")
    if generic_type == "Number" and expr_type in (
        "Integer", "Rational", "Float", "One", "NegativeOne", "Half", "Zero",
    ):
        pass  # match accepted
    elif expr_type != generic_type:
        return False

    expr_children = expr_ast.get("children", [])
    generic_children = generic_ast.get("children", [])
    if len(expr_children) != len(generic_children):
        return False

    # Generic leaf → automatic match
    if not expr_children:
        return True

    # Handling commutativity for Add / Mul
    if expr_type in ("Add", "Mul"):
        used = set()
        for gc in generic_children:
            matched = False
            for idx, ec in enumerate(expr_children):
                if idx in used:
                    continue
                if match_generic_ast(ec, gc):
                    used.add(idx)
                    matched = True
                    break
            if not matched:
                return False
        return True

    # Ordered comparison for other operations
    return all(match_generic_ast(ec, gc) for ec, gc in zip(expr_children, generic_children))
