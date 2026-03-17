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
    match = re.search(rf"- {re.escape(label)}:[ \t]*([^\n]+)", text)
    return match.group(1).strip() if match else ""


def _parse(content: str) -> dict:
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""

    def section(name: str) -> str:
        m = re.search(rf"## {re.escape(name)}\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        return m.group(1) if m else ""

    why = section("Why")
    what = section("What")
    how = section("How")

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

    lines = [
        f"# {req.get('title', '')}",
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
    ]
    return "\n".join(lines)


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
