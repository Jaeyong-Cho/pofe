from datetime import datetime, timezone
from pathlib import Path


def _find_pofe_dir() -> Path:
    for path in [Path.cwd(), *Path.cwd().parents]:
        candidate = path / ".pofe"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("No .pofe directory found. Run 'pofe init' first.")


def _count_tokens(text: str) -> int:
    # Approximation: ~4 characters per token (GPT-family heuristic).
    return max(1, len(text) // 4)


def open_history_session() -> Path:
    """Create and return a timestamped directory for one AI exchange.

    Guarantees: the returned path exists and is writable.
    Assumes: .pofe directory exists in the current tree.
    Fails: raises FileNotFoundError if .pofe is missing;
           raises OSError on filesystem failure.
    """
    pofe_dir = _find_pofe_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_dir = pofe_dir / "history" / timestamp
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def write_request(
    session_dir: Path,
    prompt: str,
    metadata: dict | None = None,
) -> None:
    """Write the prompt and its estimated token count to request.log.

    Guarantees: request.log contains a plain-text header followed by the prompt.
    Assumes: session_dir exists and is writable.
    Fails: raises OSError on write failure.
    """
    lines = [f"timestamp: {datetime.now(timezone.utc).isoformat()}"]
    if metadata:
        for key, value in metadata.items():
            lines.append(f"{key}: {value}")
    lines.append(f"tokens: {_count_tokens(prompt)}")
    lines.append("")
    lines.append(prompt)
    (session_dir / "request.log").write_text("\n".join(lines))


def write_response(session_dir: Path, response: str) -> None:
    """Write the response and its estimated token count to response.log.

    Guarantees: response.log contains a plain-text header followed by the response.
    Assumes: session_dir exists and is writable.
    Fails: raises OSError on write failure.
    """
    lines = [
        f"timestamp: {datetime.now(timezone.utc).isoformat()}",
        f"tokens: {_count_tokens(response)}",
        "",
        response,
    ]
    (session_dir / "response.log").write_text("\n".join(lines))
