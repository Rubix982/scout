# src/sources/ats/__init__.py
from .roles import Role, fetch_roles, parse_roles
from .platforms import (
    SUPPORTED_PLATFORMS,
    ParsedBoard,
    Platform,
    board_url_for,
    parse_board_url,
    role_count,
)

__all__ = [
    "Role",
    "fetch_roles",
    "parse_roles",
    "SUPPORTED_PLATFORMS",
    "ParsedBoard",
    "Platform",
    "board_url_for",
    "parse_board_url",
    "role_count",
]
