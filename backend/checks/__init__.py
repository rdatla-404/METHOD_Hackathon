"""Check registry. A check is `fn(sub, ref) -> list[Issue] | None`.
Return [] when it passes, issues when it fails, and None when it could not run
(because a field it depends on is missing or itself invalid)."""
CHECKS = []


def check(label):
    def deco(fn):
        fn.check_name = fn.__name__
        fn.label = label
        CHECKS.append(fn)
        return fn
    return deco


from . import logic, reference  # noqa: E402,F401  (registers the checks, in this order)