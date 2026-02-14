"""Deterministic hash-based UID generation for context entities."""

import hashlib


def make_uid(prefix: str, *parts: str) -> str:
    """Generate a deterministic short hash UID.

    The UID is ``<prefix>-<8 hex chars>`` derived from a SHA-256
    hash of the joined *parts*.  The same inputs always produce
    the same UID.

    Prefixes by convention:
        cls   – implementation class
        mtd   – implementation method
        fn    – implementation function
        arch  – architecture component
        req   – requirement
    """
    key = ":".join(parts)
    digest = hashlib.sha256(key.encode()).hexdigest()[:8]
    return f"{prefix}-{digest}"
