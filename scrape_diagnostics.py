class ScrapeDiagnostics:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.target_summaries = []
        self.recipient_summaries = []
        self.description_fallbacks = []

    def record_target_summary(self, source, target, summary):
        if not self.enabled:
            return

        payload = {"source": source, "target": target, **summary}
        self.target_summaries.append(payload)

        sample_title = payload.get("sample_title") or "-"
        reason = payload.get("reason") or "-"
        print(
            f"[scrape:{source}:{target}] "
            f"fetched={payload.get('fetched_jobs', 0)} "
            f"uk={payload.get('uk_jobs', 0)} "
            f"url_ok={payload.get('url_ok_jobs', 0)} "
            f"new={payload.get('new_jobs', 0)} "
            f"desc_ok={payload.get('description_ok_jobs', 0)} "
            f"desc_html={payload.get('html_like_descriptions', 0)} "
            f"usable={payload.get('usable_jobs', 0)} "
            f"reason={reason} "
            f"sample={sample_title}"
        )

    def record_recipient_summary(self, recipient_id, summary):
        if not self.enabled:
            return

        payload = {"recipient_id": recipient_id, **summary}
        self.recipient_summaries.append(payload)
        print(
            f"[ranking:{recipient_id}] "
            f"input={payload.get('input_jobs', 0)} "
            f"hard_filtered={payload.get('hard_filtered_jobs', 0)} "
            f"sponsorship_rejected={payload.get('sponsorship_rejected_jobs', 0)} "
            f"below_threshold={payload.get('below_threshold_jobs', 0)} "
            f"ranked={payload.get('ranked_jobs', 0)} "
            f"unseen={payload.get('unseen_jobs', 0)} "
            f"recipient_seen={payload.get('recipient_seen_urls', 0)} "
            f"legacy_seen={payload.get('legacy_seen_urls', 0)}"
        )

    def record_sponsor_lookup_summary(self, count):
        if not self.enabled:
            return

        print(f"[sponsorship] sponsor_lookup_companies={count}")

    def record_description_fallback(
        self,
        source,
        target,
        title,
        url,
        status,
        looks_like_html,
    ):
        if not self.enabled:
            return

        payload = {
            "source": source,
            "target": target,
            "title": title,
            "url": url,
            "status": status,
            "looks_like_html": looks_like_html,
        }
        self.description_fallbacks.append(payload)
        print(
            f"[description_fallback:{source}:{target}] "
            f"status={status} "
            f"html={1 if looks_like_html else 0} "
            f"title={title or '-'} "
            f"url={url or '-'}"
        )
