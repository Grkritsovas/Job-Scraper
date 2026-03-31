from matching.hard_filters import (
    DEFAULT_MAX_YEARS_EXPERIENCE,
    extract_required_experience_years,
    passes_experience_filter,
)
from shared.company_names import get_company_name_from_url, normalize_company_name
from shared.descriptions import (
    HEADERS,
    description_looks_like_html,
    extract_ashby_description_text,
    fetch_job_description_details,
    get_visible_text,
)
from shared.digest import build_digest_bodies, format_company_heading
from shared.locations import (
    UK_LOCATION_TERMS,
    dedupe_keep_order,
    format_locations,
    is_uk_location,
)
