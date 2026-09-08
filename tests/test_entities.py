"""Entity taxonomy tests (E-010)."""

from __future__ import annotations

import pytest

from src.common.entities import VALID_VALUES, EntityType, parse


@pytest.mark.parametrize("value", sorted(VALID_VALUES))
def test_every_valid_value_round_trips(value):
    assert parse(value) == value


@pytest.mark.parametrize("raw", ["EMPLOYER", "  Employer  ", "Employer"])
def test_parse_is_case_and_whitespace_insensitive(raw):
    assert parse(raw) == "employer"


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_becomes_unknown_and_never_employer(blank):
    """The core guarantee of E-010.

    Defaulting a blank to `employer` would recreate the silent failure the
    taxonomy exists to remove: the row would be attempted for role fetching,
    fail, and be indistinguishable from a genuine coverage gap.
    """
    assert parse(blank) == EntityType.UNKNOWN.value
    assert parse(blank) != EntityType.EMPLOYER.value


@pytest.mark.parametrize("bad", ["employers", "startup", "vc", "job board", "x"])
def test_unrecognised_value_raises_rather_than_defaulting(bad):
    """A typo must not quietly become `unknown` either -- that reintroduces the
    same silence by another route."""
    with pytest.raises(ValueError) as exc:
        parse(bad)
    assert bad in str(exc.value)


def test_source_kinds_are_exactly_the_non_employer_known_kinds():
    sources = {e.value for e in EntityType if e.is_source}
    assert sources == {"board", "agency", "investor", "community"}
    assert not EntityType.EMPLOYER.is_source
    assert not EntityType.UNKNOWN.is_source, (
        "unknown must not count as a source either -- it is un-triaged, and "
        "lumping it in would hide it from the unclassified count"
    )
