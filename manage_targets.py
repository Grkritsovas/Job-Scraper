import argparse

from target_config import load_configured_target_details


def build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect the effective scraper targets loaded from config."
    )
    parser.add_argument("source_type", nargs="?", help="Optional source filter.")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    details = load_configured_target_details()

    valid_sources = set(details)
    if args.source_type and args.source_type not in valid_sources:
        parser.error(
            f"source_type must be one of: {', '.join(sorted(valid_sources))}"
        )

    selected_sources = [args.source_type] if args.source_type else sorted(details)
    for source_type in selected_sources:
        payload = details[source_type]
        source_name = payload["source"].replace("_", " ")
        source_path = f" [{payload['path']}]" if payload.get("path") else ""
        print(f"{source_type} ({source_name}{source_path})")
        for value in payload["values"]:
            print(f"  - {value}")
        if not payload["values"]:
            print("  - <none>")


if __name__ == "__main__":
    main()
