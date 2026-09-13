import os
from typing import List

class Outer:
    class Inner:
        def nested(self, x: int) -> int:
            return x

    def method(self, a: int, /, b: int = 1, *rest, c: int = 2, **kw) -> int:
        return a + b

def top(a: str) -> str:
    return a
