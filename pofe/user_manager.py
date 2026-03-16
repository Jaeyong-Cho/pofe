import json
from pathlib import Path


def _find_pofe_dir() -> Path:
    for path in [Path.cwd(), *Path.cwd().parents]:
        candidate = path / ".pofe"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("No .pofe directory found. Run 'pofe init' first.")


def get_username() -> str:
    """Return the username stored during init.

    Guarantees: returns a non-empty string.
    Assumes: pofe init has been run in a parent directory.
    Fails: raises FileNotFoundError if .pofe or config.json is missing,
           raises ValueError if the username field is empty.
    """
    config_path = _find_pofe_dir() / "config.json"
    if not config_path.exists():
        raise FileNotFoundError("config.json not found. Run 'pofe init' first.")
    with open(config_path) as f:
        username = json.load(f).get("user", "")
    if not username:
        raise ValueError("Username not set. Run 'pofe init' first.")
    return username


def init(directory: Path, username: str) -> None:
    """Write the username to config.json inside directory.

    Guarantees: config.json is created or updated atomically.
    Assumes: directory exists and is writable.
    Fails: raises OSError on write failure.
    """
    config_path = directory / "config.json"
    config: dict = {}
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    config["user"] = username
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
