import argparse
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

    del_parser = req_sub.add_parser("delete", help="Delete a requirement by ID.")
    del_parser.add_argument("id", help="64-char requirement ID.")
    del_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt.")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "req":
        if args.req_command == "create":
            cmd_req_create(args)
        elif args.req_command == "delete":
            cmd_req_delete(args)
        else:
            req_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
