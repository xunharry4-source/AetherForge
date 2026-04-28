from __future__ import annotations
import ast
import builtins
import os

def check_file(filepath):
    with open(filepath, 'r') as f:
        tree = ast.parse(f.read(), filename=filepath)
    
    class NameVisitor(ast.NodeVisitor):
        def __init__(self):
            self.loaded = set()
            self.stored = set()
            self.imported = set()

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                self.loaded.add(node.id)
            elif isinstance(node.ctx, ast.Store):
                self.stored.add(node.id)
            self.generic_visit(node)

        def visit_Import(self, node):
            for alias in node.names:
                name = alias.asname or alias.name.split('.')[0]
                self.imported.add(name)
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            for alias in node.names:
                name = alias.asname or alias.name
                self.imported.add(name)
            self.generic_visit(node)
            
        def visit_FunctionDef(self, node):
            self.stored.add(node.name)
            self.generic_visit(node)
            
        def visit_ClassDef(self, node):
            self.stored.add(node.name)
            self.generic_visit(node)

    visitor = NameVisitor()
    visitor.visit(tree)
    builtin_names = set(dir(builtins))
    
    # Types that often cause NameError
    typing_names = {'List', 'Dict', 'Optional', 'Any', 'Union', 'Tuple', 'Set', 'Callable'}
    missing = (visitor.loaded - visitor.stored - visitor.imported - builtin_names) & typing_names
    
    if missing:
        print(f"{filepath} might be missing imports for: {missing}")

for root, dirs, files in os.walk('..'):
    for f in files:
        if f.endswith('.py') and '__pycache__' not in root:
            filepath = os.path.join(root, f)
            try:
                check_file(filepath)
            except Exception:
                pass
