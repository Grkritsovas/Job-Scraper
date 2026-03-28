import argparse

from storage import create_storage
from target_config import load_configured_targets


def build_parser():
    parser = argparse.ArgumentParser(description="Manage scraper targets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List configured targets.")
    list_parser.add_argument("source_type", nargs="?", help="Optional source filter.")

    add_parser = subparsers.add_parser("add", help="Add or enable a target.")
    add_parser.add_argument("source_type", choices=["ashby", "greenhouse", "nextjs"])
    add_parser.add_argument("target_value")

    disable_parser = subparsers.add_parser("disable", help="Disable a target.")
    disable_parser.add_argument("source_type", choices=["ashby", "greenhouse", "nextjs"])
    disable_parser.add_argument("target_value")

    enable_parser = subparsers.add_parser("enable", help="Enable a target.")
    enable_parser.add_argument("source_type", choices=["ashby", "greenhouse", "nextjs"])
    enable_parser.add_argument("target_value")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    storage = create_storage()
    storage.ensure_schema()
    storage.seed_targets(load_configured_targets())

    if args.command == "list":
        rows = storage.list_targets(args.source_type)
        for row in rows:
            status = "enabled" if row["enabled"] else "disabled"
            print(f"{row['source_type']}: {row['target_value']} ({status})")
        return

    if args.command == "add":
        storage.upsert_target(args.source_type, args.target_value, enabled=1)
        print(f"Added {args.source_type}: {args.target_value}")
        return

    if args.command == "disable":
        storage.set_target_enabled(args.source_type, args.target_value, enabled=0)
        print(f"Disabled {args.source_type}: {args.target_value}")
        return

    if args.command == "enable":
        storage.set_target_enabled(args.source_type, args.target_value, enabled=1)
        print(f"Enabled {args.source_type}: {args.target_value}")


if __name__ == "__main__":
    main()
