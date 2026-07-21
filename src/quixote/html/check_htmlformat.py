#!/usr/bin/env python3
r"""
Check that all htmlformat() calls, normally aliased as H(), use a t-string
literal as their sole argument.

Usage:
  git ls-files | xargs uv run tools/check_htmlformat.py
"""

import argparse
import ast
import sys
from dataclasses import dataclass


@dataclass
class Violation:
    filename: str
    line: int
    col: int
    message: str


def find_htmlformat_name(tree: ast.Module) -> str | None:
    """Find the local name for htmlformat imported from quixote.html."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "quixote.html":
            for alias in node.names:
                if alias.name == "htmlformat":
                    return alias.asname or alias.name
    return None


def describe_arg_type(node: ast.expr) -> str:
    """Return a human-friendly description of an AST node type."""
    if isinstance(node, ast.Name):
        return f"variable '{node.id}'"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "string literal"
    if isinstance(node, ast.Constant):
        return f"constant ({type(node.value).__name__})"
    if isinstance(node, ast.JoinedStr):
        return "f-string"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return "% formatting expression (use t-string interpolation instead)"
    if isinstance(node, ast.BinOp):
        return "binary expression"
    if isinstance(node, ast.Call):
        return "function call"
    if isinstance(node, ast.IfExp):
        return "conditional expression"
    return node.__class__.__name__


class HCallChecker(ast.NodeVisitor):
    def __init__(self, filename: str, h_name: str):
        self.filename = filename
        self.h_name = h_name
        self.violations: list[Violation] = []

    def _add(self, node: ast.expr, message: str):
        self.violations.append(
            Violation(self.filename, node.lineno, node.col_offset, message)
        )

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == self.h_name:
            if not node.args:
                self._add(node, "htmlformat() call with no arguments")
            elif len(node.args) > 1:
                self._add(
                    node,
                    (
                        f"htmlformat() call with {len(node.args)} "
                        "arguments, expected 1"
                    ),
                )
            elif any(isinstance(a, ast.Starred) for a in node.args):
                self._add(node, "htmlformat() call with starred argument")
            elif not isinstance(node.args[0], ast.TemplateStr):
                desc = describe_arg_type(node.args[0])
                self._add(
                    node,
                    f"htmlformat() argument is {desc}, expected t-string",
                )
            if node.keywords:
                self._add(node, "htmlformat() call with keyword arguments")
        self.generic_visit(node)


def check_file(filename: str) -> list[Violation]:
    try:
        with open(filename, "rb") as f:
            source = f.read()
        tree = ast.parse(source, filename)
    except SyntaxError as e:
        print(f"warning: {filename}: {e}", file=sys.stderr)
        return []
    h_name = find_htmlformat_name(tree)
    if h_name is None:
        return []
    checker = HCallChecker(filename, h_name)
    checker.visit(tree)
    return checker.violations


def main(args: list[str], prog: str | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Check that htmlformat() calls use t-string arguments",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument("files", nargs="*", help="Python files to check")
    args = parser.parse_args(args)

    violations: list[Violation] = []
    for filename in args.files:
        if not filename.endswith(".py"):
            continue
        if args.verbose:
            print('checking', filename)
        violations.extend(check_file(filename))

    for v in violations:
        print(f"{v.filename}:{v.line}:{v.col}: {v.message}")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
