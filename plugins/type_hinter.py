"""
Moruk OS - Type Hinter Plugin v3 (Improved)
Fügt Type Hints zu Python-Code hinzu.
"""

PLUGIN_NAME = "type_hinter"
PLUGIN_DESCRIPTION = "Add type hints to code using rules or ML. Test on brain.py"
PLUGIN_PARAMS = {"code": "Python code", "file": "path"}

import ast
import os


def execute(params):
    code = params.get("code", "")
    file_path = params.get("file", "")

    if file_path:
        file_path = os.path.expanduser(file_path)
        if not os.path.exists(file_path):
            return {"success": False, "result": f"File not found: {file_path}"}
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()

    if not code.strip():
        return {"success": False, "result": "No code provided"}

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"success": False, "result": f"Syntax error in code: {e}"}

    funcs_total = 0
    funcs_hinted = 0
    funcs_already = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs_total += 1

            # Smarter return hint: check if function has return statements
            has_return = False
            returns_value = False
            for subnode in ast.walk(node):
                if isinstance(subnode, ast.Return):
                    has_return = True
                    if subnode.value is not None:
                        returns_value = True
                        break

            if node.returns is None:
                if not has_return or (has_return and not returns_value):
                    node.returns = ast.Name(id="None", ctx=ast.Load())
                    funcs_hinted += 1
                else:
                    node.returns = ast.Name(id="Any", ctx=ast.Load())
                    funcs_hinted += 1
            else:
                funcs_already += 1

            # Add type hints to args without annotations
            for arg in node.args.args:
                if arg.annotation is None and arg.arg not in ("self", "cls"):
                    arg.annotation = ast.Name(id="Any", ctx=ast.Load())

    try:
        hinted_code = ast.unparse(tree)
    except Exception as e:
        return {"success": False, "result": f"Could not unparse AST: {e}"}

    # Add Any import if needed
    needs_any = "Any" in hinted_code
    has_typing_import = (
        "from typing import" in hinted_code or "import typing" in hinted_code
    )

    if needs_any and not has_typing_import:
        hinted_code = "from typing import Any\n" + hinted_code
    elif needs_any and "Any" not in hinted_code.split("import")[1].split("\n")[0]:
        # Simple check to add Any to existing typing import if missing (crude but works for now)
        if "from typing import" in hinted_code:
            hinted_code = hinted_code.replace(
                "from typing import ", "from typing import Any, "
            )

    return {
        "success": True,
        "result": f"Processed {funcs_total} functions.",
        "hinted_code": hinted_code,
    }
