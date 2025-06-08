from openai import OpenAI
import duckdb
import json
from typing import List, cast
from src.db.init import DB_PATH
from src.log import get_logger
from src.common.models import EnrichedCompany, get_empty_enriched_company

logger = get_logger("enrichment")

con: duckdb.DuckDBPyConnection = duckdb.connect(str(DB_PATH))  # type: ignore

PROMPT_TEMPLATE = """
You are helping a professional researcher enrich information about the company **{company}**. Here are the available raw details:

- What they do: {q1}
- Recent news: {q2}
- Investors & funding: {q3}
- Tech stack: {q4}
- Outreach roles / tone: {q5}
- Industry & website: {q6}

Return a JSON object like:
{{
  "summary": "...",
  "product": "...",
  "tags": ["...", "..."],
  "investors": ["...", "..."],
  "ideal_roles": "...",
  "recent_news": "...",
  "tone_advice": "...",
  "alignment_reason": "...",
  "suggested_opener": "...",
  "funding_stage": "...",
  "technologies_used": "...",
  "website_url": "...",
  "industry": "...",
  "linkedin_company_url": "...",
  "linkedin_search_links": ["...", "..."]
}}
"""

client = OpenAI()


def ask_openai(prompt: str) -> EnrichedCompany:
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful researcher."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            timeout=30,
        )
        content = response.choices[0].message.content  # type: ignore
        if not isinstance(content, str):
            logger.error("OpenAI response content is not a string")
            return get_empty_enriched_company()
        return cast(EnrichedCompany, json.loads(content.strip()))
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return get_empty_enriched_company()


def get_questions(company: str) -> List[str]:
    questions = [
        f"What does the company {company} do?",
        f"Any recent news about {company}?",
        f"Who are the investors in {company}?",
        f"What technology stack does {company} use?",
        f"Which roles at {company} are best for outreach?",
        f"What industry is {company} in? Does it have a website?",
    ]
    results: List[str] = []
    for i, q in enumerate(questions):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": q}],
                temperature=0.3,
                timeout=30,
            )
            content = response.choices[0].message.content  # type: ignore
            if not isinstance(content, str):
                logger.error("OpenAI response content is not a string")
                results.append("")
                continue
            results.append(content.strip())
        except Exception as e:
            logger.error(f"Error fetching Q{i+1} for {company}: {e}")
            results.append("")
    return results


def update_company_metadata(company: str, enriched: EnrichedCompany):
    con.execute(
        """
        UPDATE processed_companies SET
            summary = ?,
            product = ?,
            tags = ?,
            investors = ?,
            ideal_roles = ?,
            recent_news = ?,
            tone_advice = ?,
            alignment_reason = ?,
            suggested_opener = ?,
            funding_stage = ?,
            technologies_used = ?,
            website_url = ?,
            industry = ?,
            linkedin_company_url = ?,
            linkedin_search_links = ?,
            company_processed = TRUE,
            last_updated = CURRENT_TIMESTAMP
        WHERE company = ?;
        """,
        [
            enriched.get("summary"),
            enriched.get("product"),
            ", ".join(enriched.get("tags", [])),
            ", ".join(enriched.get("investors", [])),
            enriched.get("ideal_roles"),
            enriched.get("recent_news"),
            enriched.get("tone_advice"),
            enriched.get("alignment_reason"),
            enriched.get("suggested_opener"),
            enriched.get("funding_stage"),
            enriched.get("technologies_used"),
            enriched.get("website_url"),
            enriched.get("industry"),
            enriched.get("linkedin_company_url"),
            ", ".join(enriched.get("linkedin_search_links", [])),
            company,
        ],
    )
    logger.info(f"✅ Enriched and updated: {company}")


def run_enrichment_pipeline():
    rows = con.execute(
        "SELECT company FROM processed_companies WHERE company_processed = FALSE"
    ).fetchall()
    for (company,) in rows:
        logger.info(f"🔍 Processing: {company}")
        question_data: List[str] = get_questions(company)
        # Map the list of answers to the expected prompt keys
        prompt_keys = ["q1", "q2", "q3", "q4", "q5", "q6"]
        prompt_kwargs = {
            k: question_data[i] if i < len(question_data) else ""
            for i, k in enumerate(prompt_keys)
        }
        full_prompt: str = PROMPT_TEMPLATE.format(company=company, **prompt_kwargs)
        enriched = ask_openai(full_prompt)
        if enriched:
            update_company_metadata(company, enriched)
        else:
            logger.warning(f"⚠️ No enrichment data for {company}")
