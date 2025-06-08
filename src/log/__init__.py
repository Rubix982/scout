# src/log/__init__.py
from .config import get_logger

get_logger(__name__).info("src/log/__init__.py - Logger ready!")
