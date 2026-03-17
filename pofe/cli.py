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
    from pofe.requirement_store import append_requirement, list_all_tags
    from pofe.user_manager import get_username

    try:
        username = get_username()
        try:
            available_tags = [t["name"] for t in list_all_tags()]
        except FileNotFoundError:
            available_tags = []
        content = open_editor(available_tags=available_tags)
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


def cmd_req_edit(args: argparse.Namespace) -> None:
    from pofe.editor_adapter import open_editor
    from pofe.requirement_store import get_requirement, format_as_markdown, update_requirement, list_all_tags

    try:
        req = get_requirement(args.id)
    except (FileNotFoundError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        available_tags = [t["name"] for t in list_all_tags()]
    except FileNotFoundError:
        available_tags = []

    try:
        edited_content = open_editor(initial_content=format_as_markdown(req), available_tags=available_tags)
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        update_requirement(req["id"], edited_content)
        print(f"Updated: {req['id']}")
    except ValueError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except (FileNotFoundError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Storage error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tag_list(args: argparse.Namespace) -> None:
    from pofe.requirement_store import list_all_tags

    try:
        tags = list_all_tags()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not tags:
        print("No tags found.")
        return

    col_name = max(max(len(t["name"]) for t in tags), 3)
    header = f"{'TAG':<{col_name}}  COUNT"
    separator = "-" * len(header)
    print(header)
    print(separator)
    for t in tags:
        print(f"{t['name']:<{col_name}}  {t['count']}")
    print(separator)
    print(f"{len(tags)} tag(s).")


def cmd_tag_rename(args: argparse.Namespace) -> None:
    from pofe.requirement_store import rename_tag

    try:
        count = rename_tag(args.old, args.new)
        print(f"Renamed '{args.old}' to '{args.new}' in {count} requirement(s).")
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Storage error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tag_delete(args: argparse.Namespace) -> None:
    from pofe.requirement_store import delete_tag

    if not args.yes:
        answer = input(f"Delete tag '{args.name}' from all requirements? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            return

    try:
        count = delete_tag(args.name)
        print(f"Deleted tag '{args.name}' from {count} requirement(s).")
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Storage error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_req_related(args: argparse.Namespace) -> None:
    from pofe.requirement_store import get_requirement, get_related_requirements

    try:
        req = get_requirement(args.id)
        related = get_related_requirements(args.id)
    except (FileNotFoundError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    titles = req.get("related_rs") or []
    if not titles:
        print("No related requirements.")
        return

    print(f"Related requirements for: {req['title']}")
    print()
    resolved_by_title = {r.get("title", "").lower(): r for r in related}
    for title in titles:
        match = resolved_by_title.get(title.lower())
        if match:
            print(f"  [{match['id'][:8]}] {title}")
        else:
            print(f"  [unresolved] {title}")


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

    tag_parser = sub.add_parser("tag", help="Manage tags across all requirements.")
    tag_sub = tag_parser.add_subparsers(dest="tag_command")

    tag_sub.add_parser("list", help="List all tags with usage counts.")

    rename_parser = tag_sub.add_parser("rename", help="Rename a tag across all requirements.")
    rename_parser.add_argument("old", help="Current tag name.")
    rename_parser.add_argument("new", help="New tag name.")

    tag_del_parser = tag_sub.add_parser("delete", help="Remove a tag from all requirements.")
    tag_del_parser.add_argument("name", help="Tag name to delete.")
    tag_del_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt.")

    req_sub.add_parser("create", help="Open editor and store a new requirement.")

    list_parser = req_sub.add_parser("list", help="List stored requirements.")
    list_parser.add_argument("--owner", metavar="USER", help="Filter by owner username.")
    list_parser.add_argument("--status", metavar="STATUS", help="Filter by status value.")
    list_parser.add_argument("--tag", metavar="TAG", help="Filter by tag.")
    list_parser.add_argument("-o", "--output", metavar="FILE", help="Export results to a file.")

    edit_parser = req_sub.add_parser("edit", help="Open editor to modify an existing requirement.")
    edit_parser.add_argument("id", help="Requirement ID (full or prefix) or title.")

    del_parser = req_sub.add_parser("delete", help="Delete a requirement by ID.")
    del_parser.add_argument("id", help="64-char requirement ID.")
    del_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt.")

    related_parser = req_sub.add_parser("related", help="Show related requirements for a given requirement.")
    related_parser.add_argument("id", help="Requirement ID (full or prefix) or title.")

    analyze_parser = req_sub.add_parser("analyze", help="Analyze a requirement using AI.")
    analyze_parser.add_argument(
        "requirement",
        nargs="?",
        help="Requirement ID (full or prefix) or title. If omitted, opens editor for raw input.",
    )

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "tag":
        if args.tag_command == "list":
            cmd_tag_list(args)
        elif args.tag_command == "rename":
            cmd_tag_rename(args)
        elif args.tag_command == "delete":
            cmd_tag_delete(args)
        else:
            tag_parser.print_help()
    elif args.command == "req":
        if args.req_command == "create":
            cmd_req_create(args)
        elif args.req_command == "list":
            cmd_req_list(args)
        elif args.req_command == "edit":
            cmd_req_edit(args)
        elif args.req_command == "delete":
            cmd_req_delete(args)
        elif args.req_command == "related":
            cmd_req_related(args)
        elif args.req_command == "analyze":
            cmd_req_analyze(args)
        else:
            req_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
