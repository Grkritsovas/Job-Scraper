from config_loader import load_list_config, resolve_list_config


TARGET_CONFIG_SPECS = {
    "ashby": {
        "env_name": "ASHBY_COMPANIES_JSON",
        "local_file_name": "ashby_companies.local.json",
        "example_file_name": "ashby_companies.uk.example.json",
    },
    "greenhouse": {
        "env_name": "GREENHOUSE_BOARD_TOKENS_JSON",
        "local_file_name": "greenhouse_boards.local.json",
        "example_file_name": "greenhouse_boards.uk.example.json",
    },
    "lever": {
        "env_name": "LEVER_COMPANIES_JSON",
        "local_file_name": "lever_companies.local.json",
        "example_file_name": "lever_companies.uk.example.json",
    },
    "nextjs": {
        "env_name": "NEXTJS_URLS_JSON",
        "local_file_name": "nextjs_urls.local.json",
        "example_file_name": "nextjs_urls.example.json",
    },
}


def load_ashby_targets():
    return load_list_config(**TARGET_CONFIG_SPECS["ashby"])


def load_greenhouse_targets():
    return load_list_config(**TARGET_CONFIG_SPECS["greenhouse"])


def load_lever_targets():
    return load_list_config(**TARGET_CONFIG_SPECS["lever"])


def load_nextjs_targets():
    return load_list_config(**TARGET_CONFIG_SPECS["nextjs"])


def load_configured_targets():
    return {
        "ashby": load_ashby_targets(),
        "greenhouse": load_greenhouse_targets(),
        "lever": load_lever_targets(),
        "nextjs": load_nextjs_targets(),
    }


def load_configured_target_details():
    details = {}
    for source_type, spec in TARGET_CONFIG_SPECS.items():
        details[source_type] = resolve_list_config(**spec)
    return details
