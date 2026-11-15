#!/usr/bin/env python3
"""Read-only AST import boundary check, adapted from v74's AST approach."""
import ast,pathlib,subprocess
def check_ast(root,rules):
    root=pathlib.Path(root).resolve()
    names=subprocess.run(["git","-C",str(root),"ls-files","-z"],check=True,capture_output=True).stdout
    errors=[]
    for raw in names.split(b"\0"):
        if not raw:continue
        rel=raw.decode("utf-8","surrogateescape")
        if not rel.endswith(".py") or rel.startswith("tests/"):continue
        p=root/rel
        try:
            if p.is_symlink() or not p.is_file():raise OSError("unsafe path")
            tree=ast.parse(p.read_text(encoding="utf-8"),filename=rel)
        except (OSError,UnicodeError,SyntaxError,ValueError):
            errors.append("unreadable or invalid Python: "+rel);continue
        for node in ast.walk(tree):
            names=[]
            if isinstance(node,ast.Import):names=[x.name for x in node.names]
            elif isinstance(node,ast.ImportFrom) and node.level==0 and node.module:names=[node.module]
            for rule in rules:
                if rel.startswith(rule["from"]):
                    target=rule["import"]
                    if any(name==target or name.startswith(target+".") for name in names):
                        errors.append("forbidden AST import: "+rel+" -> "+target)
    return errors
