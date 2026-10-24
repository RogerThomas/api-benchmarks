#!yeet
"""Fail if a module-level name is used above the line that defines it.

Python allows it (a function body only looks names up when it runs), but it
makes a file read out of order: everything here should be defined before it's
used. No ruff/pylint/pyright rule enforces this, hence this check. Run by
pre-commit and `task check`:

    uv run yeet ./check_definition_order.py bench.py services/python/apps/*.py

A use only counts if it really refers to the module-level name: a function's
parameters, its locals and comprehension variables shadow it, and `global`
declarations are honoured.
"""

import ast
import sys
from pathlib import Path


def _module_definitions(tree: ast.Module) -> dict[str, int]:
    """Module-level name -> line of its first definition."""
    defined: dict[str, int] = {}
    for node in tree.body:
        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                names = [node.name]
            case ast.Assign():
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            case ast.AnnAssign(target=ast.Name(id=name)) | ast.TypeAlias(name=ast.Name(id=name)):
                names = [name]
            case _:
                names = []
        for name in names:
            defined.setdefault(name, node.lineno)
    return defined


def _local_names(func: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> set[str]:
    """Names bound inside `func` itself (not in nested functions), minus globals."""
    args = func.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    params += [a for a in (args.vararg, args.kwarg) if a is not None]
    local = {a.arg for a in params}
    declared_global: set[str] = set()
    pending: list[ast.AST] = [*func.body] if isinstance(func.body, list) else [func.body]
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            local.add(node.name)
            continue  # a nested scope: its own locals aren't ours
        if isinstance(node, ast.Lambda):
            continue
        if isinstance(node, ast.Global):
            declared_global.update(node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            local.add(node.id)
        pending.extend(ast.iter_child_nodes(node))
    return local - declared_global


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    defined = _module_definitions(tree)
    found: list[str] = []

    def visit(node: ast.AST, shadowed: frozenset[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            # Decorators, defaults and annotations are evaluated in the outer scope.
            outer = [
                *getattr(node, "decorator_list", []),
                *node.args.defaults,
                *(d for d in node.args.kw_defaults if d is not None),
            ]
            for child in outer:
                visit(child, shadowed)
            inner = shadowed | _local_names(node)
            body = node.body if isinstance(node.body, list) else [node.body]
            for child in body:
                visit(child, inner)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            targets = {
                n.id
                for gen in node.generators
                for n in ast.walk(gen.target)
                if isinstance(n, ast.Name)
            }
            shadowed |= targets
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in defined
            and node.id not in shadowed
            and node.lineno < defined[node.id]
        ):
            found.append(
                f"{path}:{node.lineno}: {node.id!r} is used before its definition "
                f"at line {defined[node.id]}"
            )
        for child in ast.iter_child_nodes(node):
            visit(child, shadowed)

    visit(tree, frozenset())
    return found


def main(*paths: str) -> None:
    """Check each Python file; exit 1 listing every use-before-definition."""
    problems = [v for p in paths if p.endswith(".py") for v in _violations(Path(p))]
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main(*sys.argv[1:])
