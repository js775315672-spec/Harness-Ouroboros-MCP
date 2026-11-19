import re


def select_grade(artifacts, run):
    matches = [artifact for artifact in artifacts if artifact['name'] == 'hydra-checkpoint-independent-grade']
    if len(matches) != 1:
        raise ValueError("expected one independent grade archive")
    grade = matches[0]
    if (type(grade["id"]) is not int or grade["id"] <= 0
            or grade["expired"] is not False
            or grade["workflow_run"]["id"] != run
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", grade["digest"])):
        raise ValueError("invalid grade archive provenance")
    size = grade.get("size_in_bytes")
    if type(size) is not int or not (1 <= size <= 256000):
        raise ValueError("invalid grade archive size")
    return grade
