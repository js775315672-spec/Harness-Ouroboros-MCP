#!/usr/bin/env python3
"""Trusted negative-control probe for one scoped regression test.

Loads unchanged test logic and injects a deliberately broken parser answer
for real newline-delimited multiple fences. Run inside disposable Docker only.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest


def run_probe(test_path):
    path=Path(test_path)
    spec=importlib.util.spec_from_file_location("scoped_mutation_test",path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load scoped test")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original=module.verify_addition

    def broken_parser(answer):
        if (isinstance(answer,str) and "\n" in answer
                and answer.count(chr(96)*3+"python")==2):
            return True,"deliberate multiple-fence false acceptance"
        return original(answer)

    module.verify_addition=broken_parser
    test=module.FeedbackLoopTests("test_reject_multiple_fences")
    result=unittest.TestResult()
    test.run(result)
    if result.testsRun!=1 or result.errors or result.skipped:
        raise ValueError("mutation target was not executed cleanly")
    return {"negative_control":"accept_multiple_real_newline_fences",
            "target_tests_run":result.testsRun,
            "mutant_detected":len(result.failures)==1,
            "test_passed_with_mutant":len(result.failures)==0,
            "model_generated_code_executed":False,
            "mutant_limited_to_trusted_probe":True}


if __name__=="__main__":
    try:
        report=run_probe(Path(__file__).resolve().parents[1]/
                         "tests/test_model_feedback_loop.py")
        print(json.dumps(report,sort_keys=True))
    except (OSError,ValueError,AttributeError,TypeError) as exc:
        print(json.dumps({"status":"probe_error","error":str(exc)[:250]}))
        sys.exit(2)
