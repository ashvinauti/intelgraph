from intelgraph.core.verification.base import VerificationState

HIGH_IMPACT_KEYWORDS: set[str] = {
    "ceo",
    "cto",
    "cfo",
    "coo",
    "chief",
    "president",
    "chairman",
    "founder",
    "director",
    "executive",
    "vp",
    "vice president",
    "governor",
    "senator",
    "congressman",
    "congresswoman",
    "minister",
    "ambassador",
    "judge",
    "general",
    "admiral",
    "secretary",
    "politician",
    "candidate",
    "mayor",
}

HIGH_IMPACT_DOMAINS: set[str] = {
    "finance",
    "banking",
    "health",
    "healthcare",
    "medical",
    "government",
    "gov",
    "military",
    "defense",
    "intelligence",
    "pharma",
    "energy",
    "nuclear",
    "biotech",
}

HIGH_IMPACT_PEOPLE: set[str] = set()  # can be populated with known names


class HighImpactHandler:
    @staticmethod
    def is_high_impact(
        entity_type: str,
        name: str = "",
        title: str = "",
        industry: str = "",
        domain: str = "",
    ) -> bool:
        if name.lower() in {n.lower() for n in HIGH_IMPACT_PEOPLE}:
            return True

        title_lower = title.lower()
        for kw in HIGH_IMPACT_KEYWORDS:
            if kw in title_lower or kw in name.lower():
                return True

        for dom in HIGH_IMPACT_DOMAINS:
            if dom in industry.lower() or dom in domain.lower():
                return True

        if entity_type in ("person", "company") and any(
            kw in name.lower() for kw in ["gov", "state", "federal", "national", "president"]
        ):
            return True

        return False

    @staticmethod
    def requires_confirmed(
        entity_type: str, name: str = "", title: str = "", industry: str = ""
    ) -> bool:
        return HighImpactHandler.is_high_impact(entity_type, name, title, industry)

    @staticmethod
    def verification_requirement(
        verification_state: VerificationState, is_high_impact: bool
    ) -> str:
        if not is_high_impact:
            return "standard"
        if verification_state == VerificationState.CONFIRMED:
            return "verified"
        return "requires_confirmed"
