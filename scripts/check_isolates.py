#!/usr/bin/env python3
import ast
import sys
import os

FORBIDDEN_MODULES = {"requests", "urllib", "socket", "sqlite3", "psycopg2"}


class IsolateVisitor(ast.NodeVisitor):
    """
    AST visitor that performs the following validation on a BaseIsolate subclass:
    1. No `async def` declarations are present within the class block.
    2. No `await` expressions exist inside the AST nodes of the isolate class definition.
    3. No imports or calls to typical blocking networking/database libraries inside handle_message.
    """

    def __init__(self):
        self.errors = []
        self.in_isolate_class = False
        self.in_handle_message = False

    def visit_ClassDef(self, node):
        # We check if this class is likely a BaseIsolate subclass.
        # It's an isolate class if it has a base class named 'BaseIsolate' or 'Isolate'.
        is_isolate = False
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in ("BaseIsolate", "Isolate"):
                is_isolate = True
            elif isinstance(base, ast.Attribute) and base.attr in (
                "BaseIsolate",
                "Isolate",
            ):
                is_isolate = True

        if is_isolate:
            old_in_isolate_class = self.in_isolate_class
            self.in_isolate_class = True

            # Look for async def or await inside this class block
            for body_item in node.body:
                if isinstance(body_item, ast.AsyncFunctionDef):
                    self.errors.append(
                        f"Line {body_item.lineno}: Class '{node.name}' contains 'async def {body_item.name}'. "
                        "BaseIsolate subclasses cannot use inline async."
                    )

            # Delegate to child node visitors
            self.generic_visit(node)
            self.in_isolate_class = old_in_isolate_class
        else:
            self.generic_visit(node)

    def visit_Await(self, node):
        if self.in_isolate_class:
            self.errors.append(
                f"Line {node.lineno}: 'await' expression detected within a BaseIsolate subclass definition. "
                "Isolates must run in a synchronous pure-like loop."
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if self.in_isolate_class and node.name == "handle_message":
            old_in_handle_message = self.in_handle_message
            self.in_handle_message = True
            self.generic_visit(node)
            self.in_handle_message = old_in_handle_message
        else:
            self.generic_visit(node)

    def visit_Import(self, node):
        if self.in_handle_message:
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name in FORBIDDEN_MODULES:
                    self.errors.append(
                        f"Line {node.lineno}: Import of forbidden module '{alias.name}' inside 'handle_message'."
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if self.in_handle_message and node.module:
            name = node.module.split(".")[0]
            if name in FORBIDDEN_MODULES:
                self.errors.append(
                    f"Line {node.lineno}: Import from forbidden module '{node.module}' inside 'handle_message'."
                )
        self.generic_visit(node)

    def visit_Call(self, node):
        if self.in_handle_message:
            # Check for direct calls to forbidden modules (e.g. requests.get(), urllib.request.urlopen())
            func = node.func
            if isinstance(func, ast.Attribute):
                # e.g., requests.get
                curr = func
                while isinstance(curr, ast.Attribute):
                    curr = curr.value
                if isinstance(curr, ast.Name) and curr.id in FORBIDDEN_MODULES:
                    self.errors.append(
                        f"Line {node.lineno}: Direct call to forbidden module '{curr.id}' library inside 'handle_message'."
                    )
            elif isinstance(func, ast.Name) and func.id in FORBIDDEN_MODULES:
                self.errors.append(
                    f"Line {node.lineno}: Direct call to forbidden function '{func.id}' library inside 'handle_message'."
                )
        self.generic_visit(node)


def lint_file(filepath: str) -> list:
    """Parses a file and returns a list of linter error messages."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError as e:
        return [f"Syntax Error: {e}"]

    visitor = IsolateVisitor()
    visitor.visit(tree)
    return visitor.errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/check_isolates.py <file_or_directory_path>")
        sys.exit(1)

    target = sys.argv[1]
    all_errors = []

    if os.path.isfile(target):
        errors = lint_file(target)
        if errors:
            all_errors.append((target, errors))
    elif os.path.isdir(target):
        for root, _, files in os.walk(target):
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    errors = lint_file(filepath)
                    if errors:
                        all_errors.append((filepath, errors))

    if all_errors:
        print("Isolate Linter Checks: FAILED", file=sys.stderr)
        for filepath, errors in all_errors:
            print(f"\nIn file: {filepath}", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print("Isolate Linter Checks: PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
