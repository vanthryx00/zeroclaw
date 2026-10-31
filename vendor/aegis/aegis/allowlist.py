"""Per-command approval allowlist ("always allow this").

When a risky command is approved, the user may choose to remember it. The
decision is persisted and consulted by the Executor *before* it prompts, so a
command you have already blessed runs without asking again.

Safety rules are baked in, because an allowlist is a standing authorisation and
standing authorisations are how people get hurt:

* **BLOCKED commands can never be remembered.** They never reach a prompt, so
  they can never be blessed.
* **OFFENSIVE commands can never be remembered.** Authorisation for security
  tooling is about a *declared scope*, which can be revoked in one place — not
  a one-off click. `aegis scope` remains the only way to authorise those.
* **Matching is exact by default**, on a whitespace-normalised command. Prefix
  rules exist but must be opted into deliberately, and are labelled as such.
* **A rule records the level seen at approval time.** If the same command later
  classifies *higher* than when it was remembered (a new safety rule, an
  expanded protected-path list), the rule stops applying and the prompt returns.
  Remembering "risky" must not silently become "always allow anything".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .safety import Level
from .store import JsonlStore

MATCH_EXACT = "exact"
MATCH_PREFIX = "prefix"
VALID_MATCHES = (MATCH_EXACT, MATCH_PREFIX)

#: Levels that may never be turned into a standing rule.
UNREMEMBERABLE = {Level.OFFENSIVE, Level.BLOCKED}


def normalize(command: str) -> str:
    """Whitespace-normalise a command so trivial spacing does not break a rule."""
    return " ".join((command or "").split())


def is_rememberable(level: Level) -> bool:
    return level not in UNREMEMBERABLE


@dataclass
class AllowRule:
    id: str
    pattern: str
    match: str = MATCH_EXACT
    level: str = "risky"
    hits: int = 0
    created: float = 0.0
    note: str = ""

    @classmethod
    def from_record(cls, rec: Dict[str, Any]) -> "AllowRule":
        return cls(
            id=str(rec.get("id", "")),
            pattern=str(rec.get("pattern", "")),
            match=str(rec.get("match", MATCH_EXACT)),
            level=str(rec.get("level", "risky")),
            hits=int(rec.get("hits", 0) or 0),
            created=float(rec.get("created", 0.0) or 0.0),
            note=str(rec.get("note", "")),
        )

    @property
    def level_value(self) -> int:
        """Numeric level captured at approval time (-1 if unparseable)."""
        for lvl in Level:
            if lvl.name.lower() == self.level.lower() or \
                    lvl.name.lower().replace("_", "-") == self.level.lower():
                return int(lvl)
        return -1

    def level_ok(self, level: Level) -> bool:
        """False if the command now classifies higher than when remembered."""
        remembered = self.level_value
        if remembered < 0:
            return False  # unparseable rule: do not trust it
        return int(level) <= remembered

    def matches(self, command: str, level: Level) -> bool:
        if level in UNREMEMBERABLE:
            return False
        if not self.level_ok(level):
            return False
        target = normalize(command)
        if not target or not self.pattern:
            return False
        if self.match == MATCH_PREFIX:
            return target.startswith(self.pattern)
        return target == self.pattern

    def describe(self) -> str:
        kind = "exact" if self.match == MATCH_EXACT else "prefix"
        return (f"{self.id}  [{kind}] {self.pattern}  "
                f"(level={self.level}, hits={self.hits})")


class AllowStore:
    """Persistent allowlist backed by the shared JSONL store."""

    def __init__(self, path: str):
        self._store = JsonlStore(path, prefix="alw")
        self.path = path

    # -- queries --------------------------------------------------------
    def all(self) -> List[AllowRule]:
        return [AllowRule.from_record(r) for r in self._store.all()]

    def get(self, rule_id: str) -> Optional[AllowRule]:
        rec = self._store.get(rule_id)
        return AllowRule.from_record(rec) if rec else None

    def find(self, command: str, level: Level) -> Optional[AllowRule]:
        """First rule that authorises *command* at *level*, or None."""
        for rule in self.all():
            if rule.matches(command, level):
                return rule
        return None

    def permits(self, command: str, level: Level) -> bool:
        return self.find(command, level) is not None

    def count(self) -> int:
        return self._store.count()

    # -- mutations ------------------------------------------------------
    def add(self, command: str, level: Level, *, match: str = MATCH_EXACT,
            note: str = "") -> Optional[AllowRule]:
        """Remember a command. Returns None if it may not be remembered."""
        if not is_rememberable(level):
            return None
        pattern = normalize(command)
        if not pattern:
            return None
        if match not in VALID_MATCHES:
            match = MATCH_EXACT

        # Re-remembering the same thing refreshes it rather than duplicating.
        for rule in self.all():
            if rule.pattern == pattern and rule.match == match:
                rec = self._store.update(rule.id, level=level.name.lower(),
                                         note=note or rule.note)
                return AllowRule.from_record(rec) if rec else rule

        rec = self._store.add({
            "pattern": pattern,
            "match": match,
            "level": level.name.lower(),
            "hits": 0,
            "note": note,
        }, id_prefix="alw")
        return AllowRule.from_record(rec)

    def record_hit(self, rule_id: str) -> None:
        rule = self.get(rule_id)
        if rule:
            self._store.update(rule_id, hits=rule.hits + 1)

    def revoke(self, rule_id: str) -> bool:
        return self._store.delete(rule_id)

    def clear(self) -> int:
        return self._store.clear()

    # -- display --------------------------------------------------------
    def render(self) -> str:
        rules = self.all()
        if not rules:
            return ("No remembered commands. Approve a command with "
                    "'always allow' to add one.")
        lines = [f"{len(rules)} remembered command(s):", ""]
        for rule in rules:
            lines.append("  " + rule.describe())
        lines.append("")
        lines.append("Revoke with `aegis allow rm <id>`.")
        return "\n".join(lines)
