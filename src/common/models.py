from typing import List, TypedDict


class EnrichedCompany(TypedDict):
    summary: str
    product: str
    tags: List[str]
    investors: List[str]
    ideal_roles: str
    recent_news: str
    tone_advice: str
    alignment_reason: str
    suggested_opener: str
    funding_stage: str
    technologies_used: str
    website_url: str
    industry: str
    linkedin_company_url: str
    linkedin_search_links: List[str]


def get_empty_enriched_company() -> EnrichedCompany:
    return EnrichedCompany(
        summary="",
        product="",
        tags=[],
        investors=[],
        ideal_roles="",
        recent_news="",
        tone_advice="",
        alignment_reason="",
        suggested_opener="",
        funding_stage="",
        technologies_used="",
        website_url="",
        industry="",
        linkedin_company_url="",
        linkedin_search_links=[],
    )
