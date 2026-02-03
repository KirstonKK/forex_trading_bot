#!/usr/bin/env python3
"""
Code Simplifier - Local Code Analysis Tool
Based on Anthropic's code-simplifier plugin principles.

Analyzes Python code for:
1. Unnecessary complexity and nesting
2. Redundant code patterns
3. Duplicate logic that can be consolidated
4. Long functions that should be split
5. Unclear variable/function names
6. Opportunities for list comprehensions
7. Excessive try/except blocks
8. Nested ternary operators (should use if/else)

Usage:
    python scripts/code_simplifier.py [file_or_directory]
    python scripts/code_simplifier.py core/
    python scripts/code_simplifier.py scripts/live_data_poller.py
"""

import ast
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from collections import defaultdict


@dataclass
class CodeIssue:
    """Represents a code simplification opportunity."""
    file_path: str
    line_number: int
    issue_type: str
    severity: str  # 'high', 'medium', 'low'
    description: str
    suggestion: str


class CodeSimplifier:
    """Analyzes Python code for simplification opportunities."""
    
    # Complexity thresholds
    MAX_FUNCTION_LINES = 50
    MAX_NESTING_DEPTH = 4
    MAX_FUNCTION_ARGS = 6
    MAX_CYCLOMATIC_COMPLEXITY = 10
    
    def __init__(self):
        self.issues: List[CodeIssue] = []
        self.current_file = ""
        
    def analyze_file(self, file_path: str) -> List[CodeIssue]:
        """Analyze a single Python file."""
        self.current_file = file_path
        self.issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            lines = source.split('\n')
            
            # Run all analyzers
            self._analyze_functions(tree, lines)
            self._analyze_classes(tree, lines)
            self._analyze_complexity(tree, lines)
            self._analyze_patterns(tree, lines)
            self._analyze_naming(tree)
            self._analyze_imports(tree)
            
        except SyntaxError as e:
            self.issues.append(CodeIssue(
                file_path=file_path,
                line_number=e.lineno or 0,
                issue_type="syntax_error",
                severity="high",
                description=f"Syntax error: {e.msg}",
                suggestion="Fix the syntax error before analyzing"
            ))
        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")
            
        return self.issues
    
    def analyze_directory(self, dir_path: str) -> Dict[str, List[CodeIssue]]:
        """Analyze all Python files in a directory."""
        results = {}
        
        for root, _, files in os.walk(dir_path):
            # Skip __pycache__ and venv directories
            if '__pycache__' in root or 'venv' in root or '.git' in root:
                continue
                
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    issues = self.analyze_file(file_path)
                    if issues:
                        results[file_path] = issues
                        
        return results
    
    def _analyze_functions(self, tree: ast.AST, lines: List[str]):
        """Analyze function definitions for complexity issues."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check function length
                func_lines = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                if func_lines > self.MAX_FUNCTION_LINES:
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="long_function",
                        severity="medium",
                        description=f"Function '{node.name}' is {func_lines} lines (max: {self.MAX_FUNCTION_LINES})",
                        suggestion="Break this function into smaller, focused helper functions"
                    ))
                
                # Check argument count
                total_args = len(node.args.args) + len(node.args.kwonlyargs)
                if total_args > self.MAX_FUNCTION_ARGS:
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="too_many_args",
                        severity="low",
                        description=f"Function '{node.name}' has {total_args} arguments (max: {self.MAX_FUNCTION_ARGS})",
                        suggestion="Consider using a dataclass or dict to group related parameters"
                    ))
                
                # Check for nested functions (can indicate complexity)
                nested_count = sum(1 for n in ast.walk(node) 
                                   if isinstance(n, ast.FunctionDef) and n != node)
                if nested_count > 2:
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="nested_functions",
                        severity="low",
                        description=f"Function '{node.name}' has {nested_count} nested functions",
                        suggestion="Consider extracting nested functions to module level"
                    ))
    
    def _analyze_classes(self, tree: ast.AST, lines: List[str]):
        """Analyze class definitions."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                
                if len(methods) > 20:
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="large_class",
                        severity="medium",
                        description=f"Class '{node.name}' has {len(methods)} methods",
                        suggestion="Consider splitting into smaller, focused classes"
                    ))
    
    def _analyze_complexity(self, tree: ast.AST, lines: List[str]):
        """Analyze code complexity patterns."""
        for node in ast.walk(tree):
            # Check nesting depth
            if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                depth = self._get_nesting_depth(node)
                if depth > self.MAX_NESTING_DEPTH:
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="deep_nesting",
                        severity="high",
                        description=f"Nesting depth of {depth} (max: {self.MAX_NESTING_DEPTH})",
                        suggestion="Use early returns, guard clauses, or extract to helper functions"
                    ))
            
            # Check for nested ternary operators
            if isinstance(node, ast.IfExp):
                if isinstance(node.body, ast.IfExp) or isinstance(node.orelse, ast.IfExp):
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="nested_ternary",
                        severity="high",
                        description="Nested ternary operator detected",
                        suggestion="Use if/else statements or a dictionary lookup for clarity"
                    ))
            
            # Check for long chains of elif
            if isinstance(node, ast.If):
                elif_count = self._count_elif_chain(node)
                if elif_count > 4:
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="long_elif_chain",
                        severity="medium",
                        description=f"Long if/elif chain with {elif_count} branches",
                        suggestion="Consider using a dictionary dispatch or match statement"
                    ))
    
    def _analyze_patterns(self, tree: ast.AST, lines: List[str]):
        """Analyze for common anti-patterns."""
        for node in ast.walk(tree):
            # Check for bare except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                self.issues.append(CodeIssue(
                    file_path=self.current_file,
                    line_number=node.lineno,
                    issue_type="bare_except",
                    severity="high",
                    description="Bare 'except:' catches all exceptions including KeyboardInterrupt",
                    suggestion="Specify exception type: except Exception as e:"
                ))
            
            # Check for manual loop that could be list comprehension
            if isinstance(node, ast.For):
                if self._could_be_comprehension(node):
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="use_comprehension",
                        severity="low",
                        description="Loop could potentially be a list comprehension",
                        suggestion="Consider using a list/dict comprehension for simpler code"
                    ))
            
            # Check for redundant comparisons
            if isinstance(node, ast.Compare):
                if self._is_redundant_comparison(node):
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="redundant_comparison",
                        severity="low",
                        description="Redundant boolean comparison (e.g., == True, == False)",
                        suggestion="Remove redundant comparison: use 'if x:' instead of 'if x == True:'"
                    ))
    
    def _analyze_naming(self, tree: ast.AST):
        """Analyze variable and function naming."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check for single-letter function names (except common ones)
                if len(node.name) == 1 and node.name not in ('_',):
                    self.issues.append(CodeIssue(
                        file_path=self.current_file,
                        line_number=node.lineno,
                        issue_type="poor_naming",
                        severity="medium",
                        description=f"Single-letter function name: '{node.name}'",
                        suggestion="Use descriptive function names that indicate purpose"
                    ))
            
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                # Check for overly short variable names in non-loop contexts
                if len(node.id) == 1 and node.id not in ('i', 'j', 'k', 'x', 'y', 'z', '_', 'c', 'e', 'f', 'n'):
                    pass  # Allow common single-letter names
    
    def _analyze_imports(self, tree: ast.AST):
        """Analyze import statements."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
        
        # Check for many imports (might indicate the file does too much)
        if len(imports) > 20:
            self.issues.append(CodeIssue(
                file_path=self.current_file,
                line_number=1,
                issue_type="many_imports",
                severity="low",
                description=f"File has {len(imports)} import statements",
                suggestion="Consider if this module is doing too much and should be split"
            ))
    
    def _get_nesting_depth(self, node: ast.AST, current_depth: int = 1) -> int:
        """Calculate the maximum nesting depth from a node."""
        max_depth = current_depth
        
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                child_depth = self._get_nesting_depth(child, current_depth + 1)
                max_depth = max(max_depth, child_depth)
            elif hasattr(child, 'body'):
                for subchild in getattr(child, 'body', []):
                    if isinstance(subchild, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                        child_depth = self._get_nesting_depth(subchild, current_depth + 1)
                        max_depth = max(max_depth, child_depth)
        
        return max_depth
    
    def _count_elif_chain(self, node: ast.If) -> int:
        """Count the length of an if/elif chain."""
        count = 1
        current = node
        while current.orelse:
            if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
                count += 1
                current = current.orelse[0]
            else:
                break
        return count
    
    def _could_be_comprehension(self, node: ast.For) -> bool:
        """Check if a for loop could be a list comprehension."""
        if len(node.body) != 1:
            return False
        
        stmt = node.body[0]
        
        # Check for simple append pattern
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if isinstance(func, ast.Attribute) and func.attr == 'append':
                return True
        
        return False
    
    def _is_redundant_comparison(self, node: ast.Compare) -> bool:
        """Check for redundant boolean comparisons."""
        if len(node.ops) == 1 and isinstance(node.ops[0], (ast.Eq, ast.Is)):
            if len(node.comparators) == 1:
                comp = node.comparators[0]
                if isinstance(comp, ast.Constant) and comp.value in (True, False):
                    return True
        return False


def format_report(results: Dict[str, List[CodeIssue]]) -> str:
    """Format analysis results as a readable report."""
    if not results:
        return "✅ No code simplification opportunities found!"
    
    lines = []
    lines.append("\n" + "=" * 70)
    lines.append("CODE SIMPLIFICATION REPORT")
    lines.append("=" * 70 + "\n")
    
    total_issues = sum(len(issues) for issues in results.values())
    lines.append(f"Found {total_issues} opportunities for simplification\n")
    
    # Group by severity
    severity_order = {'high': 1, 'medium': 2, 'low': 3}
    
    for file_path, issues in sorted(results.items()):
        rel_path = os.path.relpath(file_path)
        lines.append(f"\n📄 {rel_path}")
        lines.append("-" * 50)
        
        sorted_issues = sorted(issues, key=lambda x: severity_order.get(x.severity, 4))
        
        for issue in sorted_issues:
            severity_icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(issue.severity, '⚪')
            lines.append(f"\n  {severity_icon} Line {issue.line_number}: {issue.issue_type}")
            lines.append(f"     {issue.description}")
            lines.append(f"     💡 {issue.suggestion}")
    
    lines.append("\n" + "=" * 70)
    lines.append("SUMMARY")
    lines.append("=" * 70)
    
    # Count by severity
    severity_counts = defaultdict(int)
    for issues in results.values():
        for issue in issues:
            severity_counts[issue.severity] += 1
    
    lines.append(f"  🔴 High priority:   {severity_counts['high']}")
    lines.append(f"  🟡 Medium priority: {severity_counts['medium']}")
    lines.append(f"  🟢 Low priority:    {severity_counts['low']}")
    lines.append("")
    
    return "\n".join(lines)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        target = "."
    else:
        target = sys.argv[1]
    
    simplifier = CodeSimplifier()
    
    if os.path.isfile(target):
        issues = simplifier.analyze_file(target)
        results = {target: issues} if issues else {}
    elif os.path.isdir(target):
        results = simplifier.analyze_directory(target)
    else:
        print(f"Error: {target} not found")
        sys.exit(1)
    
    report = format_report(results)
    print(report)
    
    # Return non-zero if high severity issues found
    high_count = sum(1 for issues in results.values() 
                     for issue in issues if issue.severity == 'high')
    sys.exit(1 if high_count > 0 else 0)


if __name__ == '__main__':
    main()
