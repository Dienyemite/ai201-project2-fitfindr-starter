"""
tests/test_tools.py

Pytest tests for the three FitFindr tools.
Run with: pytest tests/

Tests cover:
  - search_listings: happy path, empty results, price filter
  - suggest_outfit: empty wardrobe graceful handling, non-empty wardrobe returns string
  - create_fit_card: empty outfit guard, valid input returns non-empty string
"""

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    """Happy path: a broad query with no filters should return matches."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    """Impossible query should return an empty list without raising."""
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    """All returned items must be at or below the price ceiling."""
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_no_filters():
    """With no size or price filter, all results must have a positive relevance score."""
    results = search_listings("denim jeans")
    assert isinstance(results, list)
    # All returned items should at least mention 'denim' or 'jeans' somewhere
    for item in results:
        searchable = (
            item.get("title", "").lower()
            + item.get("description", "").lower()
            + " ".join(item.get("style_tags", [])).lower()
            + " ".join(item.get("colors", [])).lower()
            + (item.get("brand") or "").lower()
            + item.get("category", "").lower()
        )
        assert "denim" in searchable or "jeans" in searchable or "bottoms" in searchable


def test_search_result_has_required_fields():
    """Each result dict must contain all required fields."""
    results = search_listings("jacket", size=None, max_price=None)
    required_fields = {"id", "title", "description", "category", "style_tags",
                       "size", "condition", "price", "colors", "platform"}
    for item in results:
        for field in required_fields:
            assert field in item, f"Missing field '{field}' in result: {item}"


def test_search_size_filter_case_insensitive():
    """Size filter should be case-insensitive."""
    results_upper = search_listings("top", size="M", max_price=None)
    results_lower = search_listings("top", size="m", max_price=None)
    assert len(results_upper) == len(results_lower)


def test_search_sorted_by_relevance():
    """Results with more keyword matches should come first."""
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    if len(results) >= 2:
        # The first result should have at least as many matching keywords as the last
        def count_kw(item):
            text = " ".join([
                item.get("title", ""),
                item.get("description", ""),
                " ".join(item.get("style_tags", [])),
            ]).lower()
            return sum(1 for kw in ["vintage", "graphic", "tee"] if kw in text)
        assert count_kw(results[0]) >= count_kw(results[-1])


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe():
    """Empty wardrobe should return a non-empty string (general advice), not raise."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0, "Need a search result for this test"
    item = results[0]

    suggestion = suggest_outfit(item, get_empty_wardrobe())

    assert isinstance(suggestion, str)
    assert len(suggestion.strip()) > 0


def test_suggest_outfit_with_wardrobe():
    """Non-empty wardrobe should return a non-empty outfit suggestion string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    item = results[0]

    suggestion = suggest_outfit(item, get_example_wardrobe())

    assert isinstance(suggestion, str)
    assert len(suggestion.strip()) > 0


def test_suggest_outfit_no_exception_on_minimal_item():
    """suggest_outfit should not crash if the item dict has minimal fields."""
    minimal_item = {
        "id": "test_001",
        "title": "Mystery Tee",
        "category": "tops",
        "style_tags": [],
        "colors": [],
        "price": 10.0,
        "platform": "depop",
    }
    result = suggest_outfit(minimal_item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    """Empty outfit string must return an error message string, not raise."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    item = results[0]

    result = create_fit_card("", item)

    assert isinstance(result, str)
    assert len(result.strip()) > 0
    # Should NOT be the normal caption format — it should signal an error
    assert "outfit" in result.lower() or "fit card" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    """Whitespace-only outfit must also return an error string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    item = results[0]
    result = create_fit_card("   \n  ", item)
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_create_fit_card_returns_non_empty_string():
    """Valid outfit input must produce a non-empty caption string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    item = results[0]
    outfit = suggest_outfit(item, get_example_wardrobe())

    card = create_fit_card(outfit, item)

    assert isinstance(card, str)
    assert len(card.strip()) > 0


def test_create_fit_card_no_exception_on_minimal_item():
    """create_fit_card should not crash if the item dict has minimal fields."""
    minimal_item = {
        "title": "Mystery Tee",
        "price": 10.0,
        "platform": "depop",
        "style_tags": [],
        "colors": [],
    }
    result = create_fit_card("Wear it with jeans and sneakers.", minimal_item)
    assert isinstance(result, str)
    assert len(result.strip()) > 0
