from graders.criteria import grade_success
from graders.hallucination import grade_hallucination


def test_answer_contains_all() -> None:
    got = grade_success(
        "Greeter is a class in pkg/greeter.py",
        {"type": "answer_contains_all", "values": ["Greeter", "greeter.py", "class"]},
    )
    assert got["passed"] is True


def test_hallucination_flags_unknown_symbol() -> None:
    pmap = {
        "packages": [
            {
                "name": "pkg",
                "path": "pkg",
                "symbols": [{"name": "Greeter", "kind": "class"}],
            }
        ],
        "languages": ["python"],
    }
    got = grade_hallucination("Greeter and TotallyFakeService are used", pmap)
    assert "TotallyFakeService" in got["nonexistent"]
    assert "Greeter" not in got["nonexistent"]
