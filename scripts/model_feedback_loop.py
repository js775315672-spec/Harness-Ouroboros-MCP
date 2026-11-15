#!/usr/bin/env python3
"""Bounded model -> static verification -> feedback -> retry experiment.

Untrusted model output is NEVER executed, imported, applied or committed.
The only accepted task is a simple addition function; AST is inspected.
"""
import ast
import json
import re
from pathlib import Path

def extract_code(answer):
    """Extract exactly one fenced Python code block, rejecting ambiguous fences."""
    if len(answer)>4000:
        raise ValueError("model response exceeds 4000 characters")
    answer=answer.strip()
    fence=r"```(?:python|py)?[ \t]*\n([\s\S]*?)\n```"
    matches=list(re.finditer(fence,answer,re.I))
    if not matches:
        if "```" in answer:
            raise ValueError("malformed code fence")
        return answer
    if len(matches)!=1 or answer.count("```")!=2:
        raise ValueError("ambiguous or multiple code fences")
    before=answer[:matches[0].start()]
    after=answer[matches[0].end():]
    # Explanatory prose is permitted, but no un-fenced Python statements.
    for prose in (before,after):
        if re.search(r"(?m)^\s*(?:import |from |def |class |@|exec\(|eval\()",prose):
            raise ValueError("executable-looking text outside code fence")
    return matches[0].group(1)


def verify_addition(answer):
    try: code=extract_code(answer)
    except ValueError as exc:return False,str(exc)
    if len(code)>2000:return False,"output exceeds 2000 characters"
    try: tree=ast.parse(code)
    except SyntaxError as exc:return False,"syntax error: "+str(exc)
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef):
        return False,"expected exactly one function definition"
    fn=tree.body[0]
    if fn.name!="add" or fn.decorator_list or fn.returns is not None:
        return False,"expected undecorated add function"
    args=fn.args
    if (len(args.args)!=2 or [a.arg for a in args.args]!=["x","y"] or
        args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or
        args.defaults or args.kw_defaults or any(a.annotation for a in args.args)):
        return False,"expected only two plain arguments x and y"
    if len(fn.body)!=1 or not isinstance(fn.body[0],ast.Return):
        return False,"expected one return statement"
    expr=fn.body[0].value
    if not (isinstance(expr,ast.BinOp) and isinstance(expr.op,ast.Add) and
            isinstance(expr.left,ast.Name) and expr.left.id=="x" and
            isinstance(expr.right,ast.Name) and expr.right.id=="y"):
        return False,"expected exactly return x + y"
    return True,"static AST contract passed (no code execution)"

def run_loop(generate,max_attempts=3):
    if not 1<=max_attempts<=5:raise ValueError("attempt limit must be 1..5")
    prompt="Write exactly one Python function def add(x, y): returning x + y. Code only."
    attempts=[]
    for number in range(1,max_attempts+1):
        response=generate(prompt)
        passed,reason=verify_addition(response)
        attempts.append({"attempt":number,"passed":passed,"reason":reason,
                         "output_preview":response[:500]})
        if passed:break
        prompt=("Previous answer failed static validation: "+reason+
                ". Return only def add(x, y): followed by return x + y; no other code.")
    return {"passed":attempts[-1]["passed"],"attempts":attempts,
            "model_output_executed":False,"patch_applied":False,
            "harness_passed":False,"validation":"static_ast_contract_only"}

def save_report(result,path):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
