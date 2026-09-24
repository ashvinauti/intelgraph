_KNOWN_LEGITIMATE_DOMAINS: set[str] = {
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "crunchbase.com",
    "bloomberg.com",
    "reuters.com",
    "sec.gov",
    "edgar.sec.gov",
    "whois.icann.org",
    "crt.sh",
    "censys.io",
    "shodan.io",
    "archive.org",
    "web.archive.org",
    "wikipedia.org",
    "wikidata.org",
}


class TrustScorer:
    @staticmethod
    def compute(
        source_tier: int,
        source_url: str,
        validation_count: int = 0,
        days_since_first_seen: float = 0.0,
        is_https: bool | None = None,
        is_legitimate_domain: bool | None = None,
        consensus_penalty: int = 0,
        is_suspicious: bool = False,
    ) -> int:
        base = TrustScorer._base_score(source_tier)
        modifiers = TrustScorer._compute_modifiers(
            source_url=source_url,
            validation_count=validation_count,
            days_since_first_seen=days_since_first_seen,
            is_https=is_https,
            is_legitimate_domain=is_legitimate_domain,
            consensus_penalty=consensus_penalty,
            is_suspicious=is_suspicious,
        )
        score = base + modifiers
        return max(0, min(100, score))

    @staticmethod
    def _base_score(tier: int) -> int:
        if tier == 1:
            return 90
        elif tier == 2:
            return 60
        elif tier == 3:
            return 30
        return 0

    @staticmethod
    def _compute_modifiers(
        source_url: str,
        validation_count: int,
        days_since_first_seen: float,
        is_https: bool | None,
        is_legitimate_domain: bool | None,
        consensus_penalty: int,
        is_suspicious: bool,
    ) -> int:
        modifiers = 0

        if is_https is None:
            is_https = source_url.startswith("https://")
        if is_https:
            modifiers += 5

        if is_legitimate_domain is None:
            import urllib.parse

            try:
                domain = urllib.parse.urlparse(source_url).netloc.lower()
                is_legitimate_domain = any(
                    domain == d or domain.endswith("." + d) for d in _KNOWN_LEGITIMATE_DOMAINS
                )
            except Exception:
                is_legitimate_domain = False
        if is_legitimate_domain:
            modifiers += 10

        if days_since_first_seen > 730:
            modifiers += 5
        elif days_since_first_seen > 365:
            modifiers += 3

        if validation_count >= 10:
            modifiers += 10
        elif validation_count >= 5:
            modifiers += 7
        elif validation_count >= 2:
            modifiers += 5
        elif validation_count >= 1:
            modifiers += 3

        if consensus_penalty:
            modifiers -= min(abs(consensus_penalty), 30)

        if is_suspicious:
            modifiers -= 30

        return modifiers

    @staticmethod
    def reliability_score(tier: int, validation_count: int) -> int:
        base = {1: 85, 2: 60, 3: 35}.get(tier, 0)
        boost = min(validation_count * 2, 15)
        return min(100, base + boost)
