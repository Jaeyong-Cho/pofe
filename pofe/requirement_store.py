import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def _find_pofe_dir() -> Path:
    for path in [Path.cwd(), *Path.cwd().parents]:
        candidate = path / ".pofe"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("No .pofe directory found. Run 'pofe init' first.")


def _generate_id(timestamp: str, username: str) -> str:
    raw = f"{timestamp}{username}".encode()
    return hashlib.sha256(raw).hexdigest()


def _extract_bullet(text: str, label: str) -> str:
    match = re.search(rf"- {re.escape(label)}:[ \t]*([^\n]*)", text)
    if not match:
        return ""

    inline = match.group(1).strip()
    if inline:
        return inline

    # No inline value — collect immediately following indented sub-list items.
    sub_items = []
    for line in text[match.end():].split("\n"):
        if not line.strip():
            continue
        if re.match(r"^[ \t]+-", line):
            sub_items.append(re.sub(r"^[ \t]+-[ \t]*", "", line))
        else:
            break

    return "\n".join(sub_items)


def _parse_related_rs(content: str) -> list[str]:
    """Extract related requirement titles from the '## Related RS' section.

    Guarantees: returns a list of non-empty title strings; returns [] if the
                section is absent or contains no valid bullet items.
    """
    m = re.search(r"## Related RS\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if not m:
        return []
    items = []
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            title = stripped[2:].strip()
            if title:
                items.append(title)
    return items


def _parse(content: str) -> dict:
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""

    def section(name: str) -> str:
        m = re.search(rf"## {re.escape(name)}\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        return m.group(1) if m else ""

    why = section("Why")
    what = section("What")
    how = section("How")

    raw_tags = _extract_bullet(content, "Tags")
    tags = list(dict.fromkeys(
        t.strip().lower() for t in raw_tags.split(",") if t.strip()
    ))

    fields = {
        "title": title,
        "why": {
            "problem": _extract_bullet(why, "Problem"),
            "hypothesis": _extract_bullet(why, "Hypothesis"),
            "expect": _extract_bullet(why, "Expect"),
        },
        "what": {
            "input": _extract_bullet(what, "Input"),
            "process": _extract_bullet(what, "Process"),
            "output": _extract_bullet(what, "Output"),
        },
        "how": {
            "constraints": _extract_bullet(how, "Constraints"),
            "approach": _extract_bullet(how, "Approach"),
            "acceptance_criteria": _extract_bullet(how, "Acceptance Criteria"),
        },
        "tags": tags,
        "related_rs": _parse_related_rs(content),
    }

    missing = []
    if not fields["title"]:
        missing.append("title")
    for section, section_fields in [("why", fields["why"]), ("what", fields["what"]), ("how", fields["how"])]:
        for key, value in section_fields.items():
            if not value:
                missing.append(f"{section}.{key}")

    if missing:
        raise ValueError(f"Incomplete fields: {', '.join(missing)}")

    return fields


def append_requirement(content: str, username: str) -> str:
    """Parse, validate, and store a new requirement from editor content.

    Guarantees: returns a unique 64-char hex ID; entry is written to rsdb.json.
    Assumes: .pofe directory exists in a parent path; username is non-empty.
    Fails: raises ValueError if required template fields are missing;
           raises OSError on file write failure.
    """
    pofe_dir = _find_pofe_dir()
    data_dir = pofe_dir / "data"
    data_dir.mkdir(exist_ok=True)
    rsdb_path = data_dir / "rsdb.json"

    fields = _parse(content)
    now = datetime.now(timezone.utc).isoformat()
    req_id = _generate_id(now, username)

    entry = {
        "id": req_id,
        "title": fields["title"],
        "why": fields["why"],
        "what": fields["what"],
        "how": fields["how"],
        "tags": fields["tags"],
        "related_rs": fields["related_rs"],
        "created_at": now,
        "updated_at": now,
        "user": username,
        "qna": [],
    }

    db: dict = {}
    if rsdb_path.exists():
        with open(rsdb_path) as f:
            db = json.load(f)

    db[req_id] = entry

    with open(rsdb_path, "w") as f:
        json.dump(db, f, indent=2)

    return req_id


def get_requirement(id_or_title: str) -> dict:
    """Retrieve a stored requirement by ID (full or prefix) or by exact title.

    Guarantees: returns the matching requirement dict.
    Assumes: rsdb.json exists.
    Fails: raises FileNotFoundError if rsdb.json is missing;
           raises KeyError if no match or ambiguous prefix/title.
    """
    rsdb_path = _find_pofe_dir() / "data" / "rsdb.json"
    if not rsdb_path.exists():
        raise FileNotFoundError("rsdb.json not found. No requirements stored.")

    with open(rsdb_path) as f:
        db = json.load(f)

    # Exact ID match
    if id_or_title in db:
        return db[id_or_title]

    # Prefix ID match
    id_matches = [v for k, v in db.items() if k.startswith(id_or_title)]
    if len(id_matches) == 1:
        return id_matches[0]
    if len(id_matches) > 1:
        raise KeyError(f"Ambiguous ID prefix '{id_or_title}': matches {len(id_matches)} requirements.")

    # Title match (case-insensitive)
    title_matches = [v for v in db.values() if v.get("title", "").lower() == id_or_title.lower()]
    if len(title_matches) == 1:
        return title_matches[0]
    if len(title_matches) > 1:
        raise KeyError(f"Ambiguous title '{id_or_title}': matches {len(title_matches)} requirements.")

    raise KeyError(f"No requirement found for '{id_or_title}'.")


def format_as_markdown(req: dict) -> str:
    """Render a stored requirement dict back into the standard markdown format."""
    why = req.get("why", {})
    what = req.get("what", {})
    how = req.get("how", {})

    tags_str = ", ".join(req.get("tags") or [])

    related = req.get("related_rs") or []

    lines = [
        f"# {req.get('title', '')}",
        "",
        f"- Tags: {tags_str}",
        "",
        "## Why",
        f"- Problem: {why.get('problem', '')}",
        f"- Hypothesis: {why.get('hypothesis', '')}",
        f"- Expect: {why.get('expect', '')}",
        "",
        "## What",
        f"- Input: {what.get('input', '')}",
        f"- Process: {what.get('process', '')}",
        f"- Output: {what.get('output', '')}",
        "",
        "## How",
        f"- Constraints: {how.get('constraints', '')}",
        f"- Approach: {how.get('approach', '')}",
        f"- Acceptance Criteria: {how.get('acceptance_criteria', '')}",
        "",
        "## Related RS",
        *[f"- {title}" for title in related],
    ]
    return "\n".join(lines)


def list_requirements(
    *,
    owner: str | None = None,
    status: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    """Return all stored requirements, optionally filtered.

    Guarantees: returns a list sorted by created_at descending; never raises on
                missing optional fields (status, tags) – those records are simply
                excluded when the filter is specified.
    Assumes: .pofe directory exists.
    Fails: raises FileNotFoundError if rsdb.json is missing.
    """
    rsdb_path = _find_pofe_dir() / "data" / "rsdb.json"
    if not rsdb_path.exists():
        raise FileNotFoundError("rsdb.json not found. No requirements stored.")

    with open(rsdb_path) as f:
        db = json.load(f)

    results = list(db.values())

    if owner is not None:
        results = [r for r in results if r.get("user", "").lower() == owner.lower()]
    if status is not None:
        results = [r for r in results if r.get("status", "").lower() == status.lower()]
    if tag is not None:
        tag_lower = tag.lower()
        results = [
            r for r in results
            if tag_lower in [t.lower() for t in r.get("tags", [])]
        ]

    results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return results


def update_requirement(req_id: str, content: str) -> None:
    """Parse, validate, and overwrite an existing requirement by ID.

    Guarantees: the entry in rsdb.json is updated in place; updated_at is refreshed.
    Assumes: .pofe directory exists; req_id is the full 64-char ID.
    Fails: raises ValueError if required template fields are missing;
           raises FileNotFoundError if rsdb.json is missing;
           raises KeyError if req_id is not found;
           raises OSError on write failure.
    """
    rsdb_path = _find_pofe_dir() / "data" / "rsdb.json"

    if not rsdb_path.exists():
        raise FileNotFoundError("rsdb.json not found. No requirements stored.")

    with open(rsdb_path) as f:
        db = json.load(f)

    if req_id not in db:
        raise KeyError(f"Requirement '{req_id}' not found.")

    fields = _parse(content)
    now = datetime.now(timezone.utc).isoformat()

    entry = db[req_id]
    entry["title"] = fields["title"]
    entry["why"] = fields["why"]
    entry["what"] = fields["what"]
    entry["how"] = fields["how"]
    entry["tags"] = fields["tags"]
    entry["related_rs"] = fields["related_rs"]
    entry["updated_at"] = now

    with open(rsdb_path, "w") as f:
        json.dump(db, f, indent=2)


def list_all_tags() -> list[dict]:
    """Return all unique tags aggregated across requirements with usage counts.

    Guarantees: returns a list of {"name": str, "count": int} sorted by count
                descending, then name ascending; never raises on missing tags field.
    Assumes: .pofe directory exists.
    Fails: raises FileNotFoundError if rsdb.json is missing.
    """
    rsdb_path = _find_pofe_dir() / "data" / "rsdb.json"
    if not rsdb_path.exists():
        raise FileNotFoundError("rsdb.json not found. No requirements stored.")

    with open(rsdb_path) as f:
        db = json.load(f)

    counts: dict[str, int] = {}
    for req in db.values():
        for tag in req.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1

    return sorted(
        [{"name": name, "count": count} for name, count in counts.items()],
        key=lambda t: (-t["count"], t["name"]),
    )


def rename_tag(old_name: str, new_name: str) -> int:
    """Rename a tag across all requirements.

    Guarantees: all occurrences of old_name are replaced with new_name;
                deduplication is applied when new_name already exists on a requirement;
                updated_at is refreshed for each modified requirement;
                returns count of modified requirements.
    Assumes: .pofe directory exists; tag names are non-empty strings.
    Fails: raises FileNotFoundError if rsdb.json is missing;
           raises KeyError if old_name does not exist in any requirement;
           raises ValueError if either name is empty or old_name == new_name;
           raises OSError on write failure.
    """
    old_name = old_name.strip().lower()
    new_name = new_name.strip().lower()

    if not old_name or not new_name:
        raise ValueError("Tag names must be non-empty.")
    if old_name == new_name:
        raise ValueError(f"Old and new tag names are identical: '{old_name}'.")

    rsdb_path = _find_pofe_dir() / "data" / "rsdb.json"
    if not rsdb_path.exists():
        raise FileNotFoundError("rsdb.json not found. No requirements stored.")

    with open(rsdb_path) as f:
        db = json.load(f)

    if not any(old_name in req.get("tags", []) for req in db.values()):
        raise KeyError(f"Tag '{old_name}' not found.")

    now = datetime.now(timezone.utc).isoformat()
    modified = 0
    for req in db.values():
        tags = req.get("tags", [])
        if old_name not in tags:
            continue
        seen: set[str] = set()
        new_tags = []
        for t in tags:
            resolved = new_name if t == old_name else t
            if resolved not in seen:
                new_tags.append(resolved)
                seen.add(resolved)
        req["tags"] = new_tags
        req["updated_at"] = now
        modified += 1

    with open(rsdb_path, "w") as f:
        json.dump(db, f, indent=2)

    return modified


def delete_tag(name: str) -> int:
    """Remove a tag from all requirements.

    Guarantees: all occurrences of name are removed from every requirement;
                updated_at is refreshed for each modified requirement;
                returns count of modified requirements.
    Assumes: .pofe directory exists.
    Fails: raises FileNotFoundError if rsdb.json is missing;
           raises KeyError if name does not exist in any requirement;
           raises ValueError if name is empty;
           raises OSError on write failure.
    """
    name = name.strip().lower()
    if not name:
        raise ValueError("Tag name must be non-empty.")

    rsdb_path = _find_pofe_dir() / "data" / "rsdb.json"
    if not rsdb_path.exists():
        raise FileNotFoundError("rsdb.json not found. No requirements stored.")

    with open(rsdb_path) as f:
        db = json.load(f)

    if not any(name in req.get("tags", []) for req in db.values()):
        raise KeyError(f"Tag '{name}' not found.")

    now = datetime.now(timezone.utc).isoformat()
    modified = 0
    for req in db.values():
        tags = req.get("tags", [])
        if name in tags:
            req["tags"] = [t for t in tags if t != name]
            req["updated_at"] = now
            modified += 1

    with open(rsdb_path, "w") as f:
        json.dump(db, f, indent=2)

    return modified


def delete_requirement(req_id: str, *, confirm: bool = True) -> None:
    """Remove a requirement from rsdb.json by ID.

    Guarantees: requirement is removed from rsdb.json; action is printed to stdout.
    Assumes: .pofe directory and rsdb.json exist.
    Fails: raises FileNotFoundError if rsdb.json is missing;
           raises KeyError if req_id is not found;
           raises OSError on write failure.
    """
    rsdb_path = _find_pofe_dir() / "data" / "rsdb.json"

    if not rsdb_path.exists():
        raise FileNotFoundError("rsdb.json not found. No requirements stored.")

    with open(rsdb_path) as f:
        db = json.load(f)

    if req_id not in db:
        raise KeyError(f"Requirement '{req_id}' not found.")

    if confirm:
        title = db[req_id].get("title", req_id)
        answer = input(f"Delete '{title}' [{req_id[:8]}...]? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            return

    del db[req_id]

    with open(rsdb_path, "w") as f:
        json.dump(db, f, indent=2)

    print(f"Deleted: {req_id}")


def get_related_requirements(id_or_title: str) -> list[dict]:
    """Return requirements listed in the related_rs field of the given requirement.

    Each title in related_rs is resolved by exact case-insensitive title match.
    Titles that do not resolve to any stored requirement are silently skipped.

    Guarantees: returns a list of requirement dicts; order follows related_rs list.
    Assumes: rsdb.json exists.
    Fails: raises FileNotFoundError if rsdb.json is missing;
           raises KeyError if id_or_title is not found.
    """
    req = get_requirement(id_or_title)
    related_titles = req.get("related_rs") or []
    if not related_titles:
        return []

    rsdb_path = _find_pofe_dir() / "data" / "rsdb.json"
    with open(rsdb_path) as f:
        db = json.load(f)

    all_reqs = list(db.values())
    resolved = []
    for title in related_titles:
        title_lower = title.lower()
        matches = [r for r in all_reqs if r.get("title", "").lower() == title_lower]
        if len(matches) == 1:
            resolved.append(matches[0])
    return resolved
