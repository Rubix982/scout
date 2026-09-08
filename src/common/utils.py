# src/common/utils.py
"""Shared helpers.

`prettify_column_names()` was removed in E-002. It reconstructed sheet headers by
title-casing db column names (`company_processed` -> "Company Processed"), which
coupled the schema to the sheet's exact capitalisation and made a header rename
fail silently. Column mapping is now explicit in `SheetTable.columns`.
"""
