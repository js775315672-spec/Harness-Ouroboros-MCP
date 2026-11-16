"""Frozen P1e held-out nine case checks plus one no-mutation check per lane.

This differs materially from the P1d tests. The model prompt sees task
specifications only, not the CASES or actual expected values below.
"""
import copy
import os
import unittest

from candidate import solve

CASES = {
    "01": [
        ({"current": 0, "ceiling": 2, "step": 1}, 1),
        ({"current": 6, "ceiling": 10, "step": 3}, 9),
        ({"current": 6, "ceiling": 8, "step": 3}, None),
        ({"current": 1, "ceiling": 5, "step": True}, None),
        ({"current": True, "ceiling": 10, "step": 1}, None),
        ({"current": 3, "ceiling": False, "step": 1}, None),
        ({"current": -1, "ceiling": 10, "step": 2}, None),
        ({"current": 10000, "ceiling": 10000, "step": 1}, None),
        ({"current": 4, "ceiling": 10, "step": 5}, 9),
    ],
    "02": [
        ([], []),
        (["z", "b", "z", "a"], ["a", "b", "z"]),
        (["ab", "AB"], ["AB", "ab"]),
        ([""], []),
        (["okay", None], []),
        (["x"*13], []),
        (["x"]*13, []),
        ("x", []),
        (["a", "a", "b", "c"], ["a", "b", "c"]),
    ],
    "03": [
        ({"items": [], "done": []}, []),
        ({"items": [{"id": "a", "deps": ["x"]}], "done": []}, ["a"]),
        ({"items": [{"id": "a", "deps": ["x"]}], "done": ["x"]}, []),
        ({"items": [{"id": "b", "deps": ["x", "z"]},
                    {"id": "a", "deps": ["y"]}], "done": ["x"]},
         ["a", "b"]),
        ({"items": [{"id": "a", "deps": []}], "done": []}, []),
        ({"items": [{"id": "a", "deps": ["x"]},
                    {"id": "a", "deps": ["z"]}], "done": []}, []),
        ({"items": [{"id": "a", "deps": ["x"]}], "done": ["a"]}, []),
        ({"items": [{"id": "a", "deps": [1]}], "done": []}, []),
        ({"items": [{"id": "a", "deps": ["x"]}], "done": "x"}, []),
    ],
    "04": [
        ({"parents": ["a"], "per_parent": 1, "budget": 1}, ["a#0"]),
        ({"parents": ["a", "b"], "per_parent": 2, "budget": 3},
         ["a#0", "a#1", "b#0"]),
        ({"parents": ["a"], "per_parent": 3, "budget": 2},
         ["a#0", "a#1"]),
        ({"parents": ["a", "a"], "per_parent": 1, "budget": 2}, []),
        ({"parents": ["a"], "per_parent": True, "budget": 2}, []),
        ({"parents": ["a"], "per_parent": 1, "budget": False}, []),
        ({"parents": [], "per_parent": 1, "budget": 2}, []),
        ({"parents": ["a"], "per_parent": 4, "budget": 10}, []),
        ({"parents": ["a", "b", "c"], "per_parent": 3, "budget": 9},
         ["a#0","a#1","a#2","b#0","b#1","b#2","c#0","c#1","c#2"]),
    ],
    "05": [
        ({"cpu_used":0,"cpu_max":10,"mem_used":0,"mem_max":20}, True),
        ({"cpu_used":8,"cpu_max":10,"mem_used":16,"mem_max":20}, True),
        ({"cpu_used":9,"cpu_max":10,"mem_used":10,"mem_max":20}, False),
        ({"cpu_used":7,"cpu_max":10,"mem_used":17,"mem_max":20}, False),
        ({"cpu_used":True,"cpu_max":10,"mem_used":1,"mem_max":2}, False),
        ({"cpu_used":1,"cpu_max":10,"mem_used":1,"mem_max":0}, False),
        ({"cpu_used":1,"cpu_max":10,"mem_used":1}, False),
        ({"cpu_used":-1,"cpu_max":10,"mem_used":1,"mem_max":20}, False),
        ({"cpu_used":1,"cpu_max":2,"mem_used":1,"mem_max":2}, True),
    ],
    "06": [
        (["src/a.py"], ["src/a.py"]),
        (["docs/z.md","tests/a.py","src/b.py"],
         ["docs/z.md","src/b.py","tests/a.py"]),
        (["src/a.py","src/a.py"], ["src/a.py"]),
        (["src/../x.py"], []),
        (["src//x.py"], []),
        (["src/./x.py"], []),
        (["src\\x.py"], []),
        (["src/a.py", "bad/x.py"], []),
        (["src/a.py"]*13, []),
    ],
    "07": [
        ([], []),
        ([{"id":"a","passed":True,"score":5}], ["a"]),
        ([{"id":"b","passed":True,"score":5},
          {"id":"a","passed":True,"score":5}], ["a","b"]),
        ([{"id":"c","passed":True,"score":6},
          {"id":"b","passed":True,"score":8},
          {"id":"a","passed":True,"score":4}], ["b","c"]),
        ([{"id":"bad","passed":False,"score":20},
          {"id":"good","passed":True,"score":1}], ["good"]),
        ([{"id":"a","passed":1,"score":5}], []),
        ([{"id":"a","passed":True,"score":True}], []),
        ([{"id":"a","passed":True,"score":2},
          {"id":"a","passed":True,"score":3}], []),
        ([{"id":"a","passed":True,"score":-1}], []),
    ],
    "08": [
        ({"phase":"queued","event":"begin"}, "running"),
        ({"phase":"running","event":"pass"}, "checked"),
        ({"phase":"running","event":"fail"}, "closed"),
        ({"phase":"checked","event":"archive"}, "closed"),
        ({"phase":"closed","event":"retry"}, "queued"),
        ({"phase":"queued","event":"pass"}, "closed"),
        ({"phase":"checked","event":"merge"}, "closed"),
        ({"phase":None,"event":"begin"}, "closed"),
        (None, "closed"),
    ],
}
LANE = os.environ.get("P1E_LANE")
if LANE not in CASES:
    raise RuntimeError("P1E_LANE not in the fixed eight-lane registry")


class FreshUnseenTaskHoldouts(unittest.TestCase):
    def test_no_input_mutation(self):
        sample=copy.deepcopy(CASES[LANE][0][0])
        before=copy.deepcopy(sample)
        solve(sample)
        self.assertEqual(sample,before)


def make_test(index):
    def test(self):
        data,expected=CASES[LANE][index]
        original=copy.deepcopy(data)
        actual=solve(data)
        self.assertEqual(actual,expected)
        self.assertEqual(data,original)
    return test


for index in range(9):
    setattr(FreshUnseenTaskHoldouts,"test_case_%02d"%(index+1),
            make_test(index))
