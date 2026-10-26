from pkg.util.math import mul


class Greeter:
    def hello(self, name: str) -> str:
        return f"hi {name}"


def add(a: int, b: int) -> int:
    return a + b


def format_greeting(name: str, *, excited: bool = False) -> str:
    """Template-friendly greeting helper for codegen / fuzz fixtures."""
    base = f"hello, {name}"
    return base + "!" if excited else base


def shout_count(n: int) -> int:
    """Depends on util.math so import graphs have a real edge."""
    return mul(n, 2)
