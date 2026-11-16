"""Frozen nine-method per-lane held-out functional oracle for P1d.

This file is copied unchanged to disposable baseline/candidate Docker stages.
It is NEVER included in model prompt; task prompts contain specifications only.
"""
import copy
import os
import unittest

from candidate import solve

CASES = {
    "01": [
        ({"epoch":0,"limit":1},1),
        ({"epoch":4,"limit":5},5),
        ({"epoch":5,"limit":5},None),
        ({"epoch":-1,"limit":5},None),
        ({"epoch":True,"limit":5},None),
        ({"epoch":4,"limit":False},None),
        ({"epoch":"4","limit":5},None),
        ({"epoch":100000,"limit":100000},None),
    ],
    "02": [
        ([],[]),
        (["a","b","a"],["a","b"]),
        (["z","z","y","z"],["z","y"]),
        (["x"],["x"]),
        (["x",1],[]),
        ("x",[]),
        ([""] ,[]),
        (["a"]*17,[]),
    ],
    "03": [
        ({"tasks":[],"done":[]},[]),
        ({"tasks":[{"id":"b","deps":[]},{"id":"a","deps":[]}],"done":[]},["a","b"]),
        ({"tasks":[{"id":"x","deps":["base"]}],"done":["base"]},["x"]),
        ({"tasks":[{"id":"a","deps":["z"]}],"done":[]},[]),
        ({"tasks":[{"id":"a","deps":[]}],"done":["a"]},[]),
        ({"tasks":[{"id":"a","deps":[]},{"id":"a","deps":[]}],"done":[]},[]),
        ({"tasks":[{"id":"b","deps":["a"]},{"id":"a","deps":[]}],"done":[]},["a"]),
        ({"tasks":[{"id":"x","deps":["a","b"]}],"done":["a"]},[]),
    ],
    "04": [
        ({"parents":["a"],"fanout":1},["a/0"]),
        ({"parents":["p"],"fanout":3},["p/0","p/1","p/2"]),
        ({"parents":["a","b"],"fanout":2},["a/0","a/1","b/0","b/1"]),
        ({"parents":["a","a"],"fanout":2},[]),
        ({"parents":["a"],"fanout":True},[]),
        ({"parents":[],"fanout":1},[]),
        ({"parents":["a"],"fanout":9},[]),
        ({"parents":["a","b","c","d","e","f","g","h"],"fanout":8},
         [p+"/"+str(i) for p in ("a","b","c","d","e","f","g","h") for i in range(8)]),
    ],
    "05": [
        ({"cpu":0,"cpu_max":1,"mem":0,"mem_max":1},True),
        ({"cpu":5,"cpu_max":5,"mem":20,"mem_max":20},True),
        ({"cpu":6,"cpu_max":5,"mem":10,"mem_max":20},False),
        ({"cpu":3,"cpu_max":5,"mem":21,"mem_max":20},False),
        ({"cpu":True,"cpu_max":5,"mem":1,"mem_max":2},False),
        ({"cpu":1,"cpu_max":0,"mem":1,"mem_max":2},False),
        ({"cpu":-1,"cpu_max":5,"mem":1,"mem_max":2},False),
        ({"cpu":2,"cpu_max":4,"mem":1},False),
    ],
    "06": [
        (["scripts/a.py"],["scripts/a.py"]),
        (["docs/readme.md","tests/t.py","scripts/a.py"],["docs/readme.md","scripts/a.py","tests/t.py"]),
        (["scripts/a.py","scripts/a.py"],["scripts/a.py"]),
        (["src/secret.py"],[]),
        (["scripts/../secret.py"],[]),
        (["scripts//bad.py"],[]),
        (["scripts\\evil.py"],[]),
        (["docs/ok.md","/etc/passwd"],[]),
    ],
    "07": [
        ([],[]),
        ([{"id":"a","passed":True,"latency":5}],["a"]),
        ([{"id":"b","passed":True,"latency":3},{"id":"a","passed":True,"latency":3}],["a","b"]),
        ([{"id":"b","passed":False,"latency":1},{"id":"a","passed":True,"latency":3}],["a"]),
        ([{"id":"d","passed":True,"latency":4},{"id":"b","passed":True,"latency":2},{"id":"a","passed":True,"latency":1},{"id":"c","passed":True,"latency":3}],["a","b","c"]),
        ([{"id":"a","passed":1,"latency":3}],[]),
        ([{"id":"a","passed":True,"latency":-1}],[]),
        ([{"id":"a","passed":True,"latency":1},{"id":"a","passed":True,"latency":2}],[]),
    ],
    "08": [
        ({"phase":"pending","event":"start"},"running"),
        ({"phase":"running","event":"pass"},"verified"),
        ({"phase":"running","event":"fail"},"blocked"),
        ({"phase":"verified","event":"review"},"review"),
        ({"phase":"blocked","event":"reset"},"pending"),
        ({"phase":"verified","event":"merge"},"blocked"),
        ({"phase":"pending","event":"pass"},"blocked"),
        ({"phase":None,"event":"start"},"blocked"),
    ],
}

LANE = os.environ.get("P1D_LANE", "")
if LANE not in CASES:
    raise RuntimeError("P1D_LANE must be one of eight preregistered tasks")


class HeldoutDistinctTasks(unittest.TestCase):
    def test_nonmutation(self):
        """Input must be treated as immutable even when result is a new list."""
        example = CASES[LANE][0][0]
        data = copy.deepcopy(example)
        original = copy.deepcopy(data)
        solve(data)
        self.assertEqual(data, original)


def make_test(index):
    def test(self):
        data, expected = CASES[LANE][index]
        original = copy.deepcopy(data)
        got = solve(data)
        self.assertEqual(got, expected)
        self.assertEqual(data, original)
    return test


for index in range(8):
    setattr(HeldoutDistinctTasks, "test_case_%02d" % (index+1), make_test(index))
