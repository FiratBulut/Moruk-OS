"""
Moruk OS - Code Analyzer Plugin v2
Analysiert Python-Code auf Qualität, Complexity und potentielle Bugs.
"""

PLUGIN_CORE = True
PLUGIN_NAME = "code_analyzer"
PLUGIN_DESCRIPTION = (
    "Analyze Python code for quality, complexity, and potential issues."
)
PLUGIN_PARAMS = {"code": "Python code to analyze", "file": "or path to Python file"}

import ast
import os


def execute(params):
    code = params.get("code", "")
    file_path = params.get("file", "")

    if file_path:
        file_path = os.path.expanduser(file_path)
        if not os.path.exists(file_path):
            return {"success": False, "result": f"File not found: {file_path}"}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            return {"success": False, "result": f"Cannot read file: {e}"}

    if not code:
        return {"success": False, "result": "No code provided"}

    issues = []
    suggestions = []
    complexity = 0
    funcs = []
    classes = []
    imports = []

    try:
        tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                funcs.append(node.name)
                # Cyclomatic complexity per function
                for child in ast.walk(node):
                    if isinstance(
                        child,
                        (
                            ast.If,
                            ast.While,
                            ast.For,
                            ast.ExceptHandler,
                            ast.With,
                            ast.Assert,
                            ast.comprehension,
                        ),
                    ):
                        complexity += 1

            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)

            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                else:
                    imports.append(node.module or "?")

            elif isinstance(node, ast.Compare):
                if len(node.ops) > 3:
                    issues.append(f"Line {node.lineno}: Overly complex comparison")

            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id == "exec":
                        issues.append(
                            f"Line {node.lineno}: Avoid 'exec' (security risk)"
                        )
                    elif node.func.id == "eval":
                        issues.append(
                            f"Line {node.lineno}: Avoid 'eval' (security risk)"
                        )
                    elif node.func.id == "__import__":
                        issues.append(f"Line {node.lineno}: Dynamic import detected")

            # Bare except detection
            elif isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    issues.append(
                        f"Line {node.lineno}: Bare 'except:' catches everything - too broad"
                    )

        # Suggestions based on metrics
        if complexity > 15:
            suggestions.append(
                f"High complexity ({complexity}) - consider refactoring into smaller functions"
            )
        elif complexity > 8:
            suggestions.append(
                f"Moderate complexity ({complexity}) - review for simplification"
            )

        if len(funcs) > 20:
            suggestions.append("Many functions - consider splitting into modules")

        if not any(isinstance(n, ast.AnnAssign) for n in ast.walk(tree)):
            suggestions.append("No type hints found - consider adding type annotations")

        if len(imports) > 15:
            suggestions.append(f"Many imports ({len(imports)}) - check for unused ones")

        lines = len(code.splitlines())
        if lines > 500:
            suggestions.append(f"Large file ({lines} lines) - consider splitting")

        return {
            "success": True,
            "result": (
                f"Lines: {lines} | Functions: {len(funcs)} | Classes: {len(classes)} | "
                f"Complexity: {complexity} | Issues: {len(issues)}"
            ),
            "functions": funcs,
            "classes": classes,
            "imports": imports,
            "complexity_score": complexity,
            "issues": issues if issues else ["No critical issues found"],
            "suggestions": suggestions if suggestions else ["Code looks good!"],
            "lines": lines,
        }

    except SyntaxError as e:
        return {"success": False, "result": f"Syntax error at line {e.lineno}: {e.msg}"}
    except Exception as e:
        return {"success": False, "result": f"Analysis error: {e}"}
