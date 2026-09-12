class Greeter:
    def hello(self, name: str) -> str:
        if name:
            return f"hi {name}"
        return "hi"


def add(a: int, b: int) -> int:
    return a + b
