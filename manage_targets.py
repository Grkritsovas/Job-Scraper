import argparse

from config.target_config import load_configured_target_details


def build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect the effective scraper targets loaded from config."
    )
    parser.add_argument(
        "command_or_source",
        nargs="?",
        help="Optional command ('list') or source filter.",
    )
    parser.add_argument(
        "source_type",
        nargs="?",
        help="Optional source filter when using the 'list' command.",
    )
    return parser


def resolve_selected_sources(command_or_source, source_type, valid_sources):
    if command_or_source in (None, "list"):
        selected_source = source_type
    elif command_or_source in valid_sources and source_type is None:
        selected_source = command_or_source
    else:
        raise ValueError(
            "usage must be either: manage_targets.py [source_type] "
            "or manage_targets.py list [source_type]"
        )

    if selected_source and selected_source not in valid_sources:
        raise ValueError(
            f"source_type must be one of: {', '.join(sorted(valid_sources))}"
        )

    return [selected_source] if selected_source else sorted(valid_sources)


def main():
    parser = build_parser()
    args = parser.parse_args()
    details = load_configured_target_details()

    valid_sources = set(details)
    try:
        selected_sources = resolve_selected_sources(
            args.command_or_source,
            args.source_type,
            valid_sources,
        )
    except ValueError as exc:
        parser.error(str(exc))

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
