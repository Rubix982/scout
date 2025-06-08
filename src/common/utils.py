def prettify_column_names(columns: list[str]) -> list[str]:
    return [col.replace("_", " ").title() for col in columns]
