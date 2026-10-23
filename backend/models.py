from dataclasses import dataclass, field

BLOCKER, WARNING, INFO = "blocker", "warning", "info"


@dataclass
class Issue:
    check: str
    severity: str            # blocker | warning | info
    field: str               # submission column the issue is about
    message: str             # what's wrong
    fix: str                 # what to do about it
    source: str              # where the rule came from (file -> column)
    source_row: str = "—"    # Excel row in the reference file (header = row 1)
    suggestions: list = field(default_factory=list)
