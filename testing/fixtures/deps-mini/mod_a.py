import mod_b
from mod_c import helper


def run() -> str:
    return mod_b.name() + helper()
