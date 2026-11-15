#!/usr/bin/env python3
"""Cross-check static model patch inspection against a scoped coding task.

Never applies, imports, executes, or commits generated code.
"""
from coding_task_contract import validate_task
from patch_gate import inspect_patch

def inspect_scoped_patch(task,model_response):
    contract=validate_task(task)
    inspected=inspect_patch(model_response)
    touched=inspected["files"]
    if not touched or not set(touched).issubset(set(contract["allowed_files"])):
        raise ValueError("patch modifies files outside approved task scope")
    if not set(contract["acceptance_tests"]).issubset(set(touched)):
        raise ValueError("patch must include its scoped acceptance test files")
    return {"task_id":contract["task_id"],"files":touched,
            "acceptance_tests":contract["acceptance_tests"],
            "static_patch_inspection_passed":True,
            "patch_approved_for_application":False,
            "generated_code_executed":False,
            "merge_authorized":False,
            "requires_harness_revalidation":True}
