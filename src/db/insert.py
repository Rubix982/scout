import duckdb
from typing import List, Dict, Any, Tuple
from src.db.init import DB_PATH
from src.log import get_logger
from src.common.utils import prettify_column_names

logger = get_logger("insert_ops")

con: duckdb.DuckDBPyConnection = duckdb.connect(str(DB_PATH))  # type: ignore


def get_columns_for_table(table_name: str) -> List[str]:
    if table_name == "processed_companies":
        return [
            "company",
            "summary",
            "product",
            "tags",
            "investors",
            "ideal_roles",
            "recent_news",
            "tone_advice",
            "alignment_reason",
            "suggested_opener",
            "funding_stage",
            "technologies_used",
            "website_url",
            "industry",
            "linkedin_company_url",
            "linkedin_search_links",
            "company_processed",
            "email_generated",
        ]
    elif table_name == "company_research":
        return ["company", "company_info", "contact_info"]
    else:
        logger.error(f"Unknown table name: {table_name}")
        raise ValueError(f"Unknown table name: {table_name}")


def get_comparison_fields_for_table(table_name: str) -> List[str]:
    if table_name == "processed_companies":
        return [
            "summary",
            "product",
            "tags",
            "investors",
            "ideal_roles",
            "recent_news",
            "tone_advice",
            "alignment_reason",
            "suggested_opener",
            "funding_stage",
            "technologies_used",
            "website_url",
            "industry",
            "linkedin_company_url",
            "linkedin_search_links",
            "company_processed",
            "email_generated",
        ]
    elif table_name == "company_research":
        return ["company_info", "contact_info"]
    else:
        logger.error(f"Unknown table name: {table_name}")
        raise ValueError(f"Unknown table name: {table_name}")


def get_primary_key_for_table(table_name: str) -> str:
    if table_name == "processed_companies":
        return "Company"
    elif table_name == "company_research":
        return "Company"
    else:
        logger.error(f"Unknown table name: {table_name}")
        raise ValueError(f"Unknown table name: {table_name}")


def get_primary_db_key_for_table(table_name: str) -> str:
    if table_name == "processed_companies":
        return "company"
    elif table_name == "company_research":
        return "company"
    else:
        logger.error(f"Unknown table name: {table_name}")
        raise ValueError(f"Unknown table name: {table_name}")


def insert_into_table(table_name: str, data: List[Dict[str, Any]]) -> None:
    if not data:
        logger.warning(f"[INSERT] No data provided to insert into table: {table_name}")
        return

    columns = get_columns_for_table(table_name)
    placeholders = ", ".join(["?"] * len(columns))
    column_names = ", ".join(columns)
    query = (
        f"INSERT OR REPLACE INTO {table_name} ({column_names}) VALUES ({placeholders})"
    )

    logger.info(f"[INSERT] Inserting {len(data)} rows into '{table_name}'...")

    for row in data:
        try:
            values = [
                row.get(col_title) for col_title in prettify_column_names(columns)
            ]
            con.execute(query, values)
        except Exception as e:
            logger.error(
                f"[INSERT] Failed to insert row with key '{row.get('Company')}' into '{table_name}': {e}"
            )


def fetch_existing_rows(table_name: str, primary_key: str) -> Dict[str, Dict[str, Any]]:
    try:
        cursor = con.execute(f"SELECT * FROM {table_name}")
        result = cursor.fetchall()
        if cursor.description is None:
            logger.warning(f"[FETCH] No columns found in table '{table_name}'")
            return {}
        columns = [desc[0] for desc in cursor.description]
        logger.info(
            f"[FETCH] Retrieved {len(result)} existing rows from '{table_name}'"
        )
        return {
            row[columns.index(primary_key)]: dict(zip(columns, row)) for row in result
        }
    except Exception as e:
        logger.error(f"[FETCH] Error fetching rows from table '{table_name}': {e}")
        return {}


def compute_delta_rows(
    existing: Dict[str, Dict[str, Any]],
    incoming: List[Dict[str, Any]],
    primary_key: str,
    comparison_fields: List[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    incoming_dict = {row[primary_key]: row for row in incoming}

    to_insert: List[Dict[str, Any]] = []
    for key, row in incoming_dict.items():
        if key not in existing:
            to_insert.append(row)
        else:
            if any(row.get(f) != existing[key].get(f) for f in comparison_fields):
                to_insert.append(row)

    to_delete = [k for k in existing if k not in incoming_dict]

    logger.info(
        f"[DELTA] Delta computed for {primary_key}: {len(to_insert)} to insert/update, {len(to_delete)} to delete"
    )
    return to_insert, to_delete


def get_incoming_for_table(table_name: str) -> List[Dict[str, Any]]:
    if table_name == "processed_companies":
        from src.clients.gsuite import get_processed_companies

        return get_processed_companies()
    elif table_name == "company_research":
        from src.clients.gsuite import get_company_research

        return get_company_research()
    else:
        logger.error(f"Unknown table name: {table_name}")
        raise ValueError(f"Unknown table name: {table_name}")


def sync_table(table_name: str):
    logger.info(f"[SYNC] Syncing table: {table_name}")
    try:
        incoming = get_incoming_for_table(table_name)
        primary_key = get_primary_key_for_table(table_name)
        comparison_fields = get_comparison_fields_for_table(table_name)
        db_primary_key = get_primary_db_key_for_table(table_name)
        existing = fetch_existing_rows(table_name, db_primary_key)

        to_insert, to_delete = compute_delta_rows(
            existing, incoming, primary_key, comparison_fields
        )

        logger.info(
            f"[SYNC] {table_name}: {len(to_insert)} insert/update, {len(to_delete)} delete operations"
        )

        insert_into_table(table_name, to_insert)

        for key in to_delete:
            try:
                con.execute(
                    f"DELETE FROM {table_name} WHERE {db_primary_key} = ?", [key]
                )
                logger.info(f"[DELETE] Removed '{key}' from '{table_name}'")
            except Exception as e:
                logger.error(
                    f"[DELETE] Failed to delete '{key}' from '{table_name}': {e}"
                )
    except Exception as e:
        logger.exception(f"[SYNC] Failed syncing table '{table_name}': {e}")
