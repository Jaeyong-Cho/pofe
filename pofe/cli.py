import argparse
import subprocess
import sys
from pathlib import Path


def cmd_init(args: argparse.Namespace) -> None:
    pofe_dir = Path.cwd() / ".pofe"
    pofe_dir.mkdir(exist_ok=True)
    (pofe_dir / "data").mkdir(exist_ok=True)

    username = input("Username: ").strip()
    if not username:
        print("Error: username cannot be empty.", file=sys.stderr)
        sys.exit(1)

    from pofe.user_manager import init
    init(pofe_dir, username)
    print(f"Initialized .pofe in {Path.cwd()}")


def cmd_req_create(args: argparse.Namespace) -> None:
    from pofe.editor_adapter import open_editor
    from pofe.requirement_store import append_requirement
    from pofe.user_manager import get_username

    try:
        username = get_username()
        content = open_editor()
        req_id = append_requirement(content, username)
        print(f"Created: {req_id}")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Storage error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_req_analyze(args: argparse.Namespace) -> None:
    from pofe.requirement_store import get_requirement, format_as_markdown
    from pofe.editor_adapter import open_editor

    if args.requirement:
        try:
            req = get_requirement(args.requirement)
            content = format_as_markdown(req)
        except (FileNotFoundError, KeyError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            content = open_editor()
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    prompt_path = Path(__file__).parent / "prompts" / "analyze_rs.md"
    try:
        system_prompt = prompt_path.read_text()
    except OSError as e:
        print(f"Prompt file error: {e}", file=sys.stderr)
        sys.exit(1)

    full_prompt = system_prompt + content

    cmd = [
        "copilot", "-s",
        "--stream", "on",
        "--model", "gpt-4.1",
        "--allow-all-paths",
        "--allow-tool", "read",
        "-p", full_prompt,
    ]
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def cmd_req_list(args: argparse.Namespace) -> None:
    from pofe.requirement_store import list_requirements

    try:
        reqs = list_requirements(
            owner=args.owner,
            status=args.status,
            tag=args.tag,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not reqs:
        print("No requirements found.")
        return

    lines = _format_req_table(reqs)
    output = "\n".join(lines)
    print(output)

    if args.output:
        try:
            Path(args.output).write_text(output + "\n")
            print(f"\nExported to {args.output}")
        except OSError as e:
            print(f"Export error: {e}", file=sys.stderr)
            sys.exit(1)


def _format_req_table(reqs: list) -> list[str]:
    """Render requirements as a fixed-width table for terminal display."""
    col_id = 8
    col_title = max(len(r.get("title", "")) for r in reqs)
    col_title = min(max(col_title, 5), 50)
    col_owner = max((len(r.get("user", "")) for r in reqs), default=5)
    col_owner = max(col_owner, 5)

    header = (
        f"{'ID':<{col_id}}  "
        f"{'TITLE':<{col_title}}  "
        f"{'OWNER':<{col_owner}}  "
        f"{'CREATED':<10}"
    )
    separator = "-" * len(header)

    rows = [header, separator]
    for r in reqs:
        short_id = r.get("id", "")[:col_id]
        title = r.get("title", "")[:col_title]
        owner = r.get("user", "")[:col_owner]
        created = r.get("created_at", "")[:10]
        row = (
            f"{short_id:<{col_id}}  "
            f"{title:<{col_title}}  "
            f"{owner:<{col_owner}}  "
            f"{created:<10}"
        )
        # Append optional fields so they don't clutter the fixed columns.
        extras = []
        if r.get("status"):
            extras.append(f"status={r['status']}")
        if r.get("tags"):
            extras.append(f"tags={','.join(r['tags'])}")
        if extras:
            row += "  " + "  ".join(extras)
        rows.append(row)

    rows.append(separator)
    rows.append(f"{len(reqs)} requirement(s) listed.")
    return rows


def cmd_req_delete(args: argparse.Namespace) -> None:
    from pofe.requirement_store import delete_requirement

    try:
        delete_requirement(args.id, confirm=not args.yes)
    except (FileNotFoundError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Storage error: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="pofe")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize .pofe directory and set username.")

    req_parser = sub.add_parser("req", help="Manage requirement specifications.")
    req_sub = req_parser.add_subparsers(dest="req_command")

    req_sub.add_parser("create", help="Open editor and store a new requirement.")

    list_parser = req_sub.add_parser("list", help="List stored requirements.")
    list_parser.add_argument("--owner", metavar="USER", help="Filter by owner username.")
    list_parser.add_argument("--status", metavar="STATUS", help="Filter by status value.")
    list_parser.add_argument("--tag", metavar="TAG", help="Filter by tag.")
    list_parser.add_argument("-o", "--output", metavar="FILE", help="Export results to a file.")

    del_parser = req_sub.add_parser("delete", help="Delete a requirement by ID.")
    del_parser.add_argument("id", help="64-char requirement ID.")
    del_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt.")

    analyze_parser = req_sub.add_parser("analyze", help="Analyze a requirement using AI.")
    analyze_parser.add_argument(
        "requirement",
        nargs="?",
        help="Requirement ID (full or prefix) or title. If omitted, opens editor for raw input.",
    )

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "req":
        if args.req_command == "create":
            cmd_req_create(args)
        elif args.req_command == "list":
            cmd_req_list(args)
        elif args.req_command == "delete":
            cmd_req_delete(args)
        elif args.req_command == "analyze":
            cmd_req_analyze(args)
        else:
            req_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
