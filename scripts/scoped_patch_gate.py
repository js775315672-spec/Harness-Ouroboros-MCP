#!/usr/bin/env python3
"""Cross-check static model patch inspection against a scoped coding task.

Never applies, imports, executes, or commits generated code.
"""
try:
    from .coding_task_contract import validate_task
    from .patch_gate import inspect_patch
    from .unified_diff_structure import validate_diff_structure
except ImportError:
    from coding_task_contract import validate_task
    from patch_gate import inspect_patch
    from unified_diff_structure import validate_diff_structure

def inspect_scoped_patch(task,model_response):
    contract=validate_task(task)
    inspected=inspect_patch(model_response)
    structure=validate_diff_structure(model_response["patch"])
    touched=inspected["files"]
    if sorted(structure["files"])!=touched:
        raise ValueError("diff structure disagrees with patch inspection")
    if not touched or not set(touched).issubset(set(contract["allowed_files"])):
        raise ValueError("patch modifies files outside approved task scope")
    if not set(contract["acceptance_tests"]).issubset(set(touched)):
        raise ValueError("patch must include its scoped acceptance test files")
    return {"task_id":contract["task_id"],"files":touched,
            "acceptance_tests":contract["acceptance_tests"],
            "static_patch_inspection_passed":True,
            "diff_hunks_validated":structure["hunks"],
            "patch_approved_for_application":False,
            "generated_code_executed":False,
            "merge_authorized":False,
            "requires_harness_revalidation":True}
