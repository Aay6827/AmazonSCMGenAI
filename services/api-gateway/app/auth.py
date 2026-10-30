from dataclasses import dataclass

ROLES = ("L1", "TEAM_LEAD", "MANAGER")


@dataclass(frozen=True)
class Principal:
    identity: str
    role: str


def load_keys(raw: str | None) -> dict[str, Principal]:
    """Parse 'key:identity:role,key:identity:role'. Error messages never echo key material."""
    keys: dict[str, Principal] = {}
    entries = [e.strip() for e in (raw or "").split(",") if e.strip()]
    for n, entry in enumerate(entries, start=1):
        parts = entry.split(":")
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"API_KEYS entry #{n} must be key:identity:role")
        key, identity, role = parts
        if len(key) < 8:
            raise ValueError(f"API_KEYS entry #{n} has a key shorter than 8 characters")
        if role not in ROLES:
            raise ValueError(f"API_KEYS entry #{n} has an unknown role")
        keys[key] = Principal(identity, role)
    return keys