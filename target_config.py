from config_loader import load_list_config


def load_ashby_targets():
    return load_list_config(
        "ASHBY_COMPANIES_JSON",
        local_file_name="ashby_companies.local.json",
        example_file_name="ashby_companies.uk.example.json",
    )


def load_greenhouse_targets():
    return load_list_config(
        "GREENHOUSE_BOARD_TOKENS_JSON",
        local_file_name="greenhouse_boards.local.json",
        example_file_name="greenhouse_boards.uk.example.json",
    )


def load_lever_targets():
    return load_list_config(
        "LEVER_COMPANIES_JSON",
        local_file_name="lever_companies.local.json",
        example_file_name="lever_companies.uk.example.json",
    )


def load_nextjs_targets():
    return load_list_config(
        "NEXTJS_URLS_JSON",
        local_file_name="nextjs_urls.local.json",
        example_file_name="nextjs_urls.example.json",
    )


def load_configured_targets():
    return {
        "ashby": load_ashby_targets(),
        "greenhouse": load_greenhouse_targets(),
        "lever": load_lever_targets(),
        "nextjs": load_nextjs_targets(),
    }
