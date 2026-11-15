import unittest
from scripts.model_feedback_loop import verify_addition,run_loop
class FeedbackLoopTests(unittest.TestCase):
    def test_good_code(self):
        self.assertTrue(verify_addition("```python\ndef add(x, y):\n    return x + y\n```")[0])
    def test_explanatory_prose_with_single_fenced_code(self):
        answer="Here is the corrected function:\\n\\n```python\\ndef add(x, y):\\n    return x + y\\n```\\n\\nIt adds the values."
        self.assertTrue(verify_addition(answer)[0])
    def test_reject_multiple_fences(self):
        answer="```python\\ndef add(x,y):\\n return x+y\\n```\\n```python\\nprint('bad')\\n```"
        self.assertFalse(verify_addition(answer)[0])
    def test_reject_code_outside_fence(self):
        answer="import os\\n```python\\ndef add(x,y):\\n return x+y\\n```"
        self.assertFalse(verify_addition(answer)[0])
    def test_reject_malformed_fence(self):
        self.assertFalse(verify_addition("```python\\ndef add(x,y):\\n return x+y")[0])
    def test_reject_side_effects(self):
        for code in ("import os\ndef add(x,y): return x+y",
                     "def add(x,y):\n print('hi')\n return x+y",
                     "def add(x,y): return eval('x+y')",
                     "def add(x,y): return x-y",
                     "def add(x,y): return x+y\nadd(1,2)"):
            with self.subTest(code=code):self.assertFalse(verify_addition(code)[0])
    def test_retry_with_failure_evidence(self):
        prompts=[]
        def fake(prompt):
            prompts.append(prompt)
            return "def add(x,y): return x-y" if len(prompts)==1 else "def add(x, y):\n return x + y"
        result=run_loop(fake,3)
        self.assertTrue(result["passed"])
        self.assertEqual(len(prompts),2)
        self.assertIn("expected exactly return x + y",prompts[1])
        self.assertFalse(result["model_output_executed"])
        self.assertFalse(result["harness_passed"])
    def test_bounded_failure(self):
        result=run_loop(lambda prompt:"not python",2)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["attempts"]),2)
    def test_invalid_limit(self):
        with self.assertRaises(ValueError):run_loop(lambda prompt:"",100)
if __name__=="__main__":unittest.main()
