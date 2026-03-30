import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = BASE_DIR / "examples"


def _load_json_from_file(file_path):
    if not file_path.exists():
        return None

    with file_path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _dedupe(values):
    return list(dict.fromkeys(value for value in values if value))


def load_json_config(
    env_name,
    local_file_name=None,
    example_file_name=None,
    default_value=None,
):
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        try:
            return json.loads(env_value)
        except json.JSONDecodeError as exc:
            lines = env_value.splitlines()
            context_line = ""
            if 1 <= exc.lineno <= len(lines):
                context_line = lines[exc.lineno - 1]
            raise RuntimeError(
                f"Invalid JSON in {env_name} at line {exc.lineno}, column {exc.colno}: "
                f"{exc.msg}. Context: {context_line}"
            ) from exc

    candidate_paths = []
    if local_file_name:
        candidate_paths.append(BASE_DIR / local_file_name)
    if example_file_name:
        candidate_paths.append(EXAMPLES_DIR / example_file_name)

    for candidate_path in candidate_paths:
        parsed = _load_json_from_file(candidate_path)
        if parsed is not None:
            return parsed

    return default_value


def load_list_config(
    env_name,
    local_file_name=None,
    example_file_name=None,
    default_values=None,
):
    resolved = resolve_list_config(
        env_name,
        local_file_name=local_file_name,
        example_file_name=example_file_name,
        default_values=default_values,
    )
    return resolved["values"]


def resolve_list_config(
    env_name,
    local_file_name=None,
    example_file_name=None,
    default_values=None,
):
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        try:
            parsed = json.loads(env_value)
            if isinstance(parsed, list):
                return {
                    "values": _dedupe(parsed),
                    "source": "environment",
                    "path": env_name,
                }
        except json.JSONDecodeError:
            return {
                "values": _dedupe(
                    item.strip()
                    for item in env_value.split(",")
                    if item.strip()
                ),
                "source": "environment",
                "path": env_name,
            }

    candidate_paths = []
    if local_file_name:
        candidate_paths.append(("local_file", BASE_DIR / local_file_name))
    if example_file_name:
        candidate_paths.append(("example_file", EXAMPLES_DIR / example_file_name))

    for source_name, candidate_path in candidate_paths:
        parsed = _load_json_from_file(candidate_path)
        if isinstance(parsed, list):
            return {
                "values": _dedupe(parsed),
                "source": source_name,
                "path": str(candidate_path),
            }

    return {
        "values": _dedupe(default_values or []),
        "source": "default",
        "path": "",
    }
