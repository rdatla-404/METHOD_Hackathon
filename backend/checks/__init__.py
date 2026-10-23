CHECKS = []

def check(fn):
    CHECKS.append(fn)
    return fn

from . import logic, reference
