"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural-language query.

    Uses a combination of regex heuristics and the Groq LLM for accuracy.
    Falls back to using the full query as the description if parsing fails.

    Returns a dict with keys: description (str), size (str | None), max_price (float | None).
    """
    # Regex pass first — fast and reliable for common patterns
    size_pattern = re.compile(
        r'\b(XXS|XS|S/M|S|M/L|M|L/XL|L|XL|XXL|XXXL|W\d{2}(?:\s*L\d{2})?|\d+(?:W|L))\b',
        re.IGNORECASE,
    )
    price_pattern = re.compile(r'\$\s*(\d+(?:\.\d+)?)|under\s+\$?\s*(\d+(?:\.\d+)?)', re.IGNORECASE)

    size_match = size_pattern.search(query)
    price_match = price_pattern.search(query)

    size = size_match.group(0).upper() if size_match else None
    max_price = None
    if price_match:
        raw = price_match.group(1) or price_match.group(2)
        try:
            max_price = float(raw)
        except ValueError:
            max_price = None

    # Strip out the size and price fragments to get the clean description
    description = query
    if size_match:
        description = description[:size_match.start()] + description[size_match.end():]
    if price_match:
        description = description[:price_match.start()] + description[price_match.end():]

    # Clean up leftover filler words from stripping
    filler = re.compile(
        r'\b(in|size|under|for|around|approximately|about|at|a|an|the|'
        r'looking for|i(?:\'m| am) looking for|find me|find|get me|'
        r'i want|i need|show me|can you find)\b',
        re.IGNORECASE,
    )
    description = filler.sub(' ', description).strip(' ,.-')
    description = re.sub(r'\s{2,}', ' ', description).strip()

    # If description ended up empty or very short, use the full query
    if len(description) < 3:
        description = query

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    Planning loop (matches Architecture diagram in planning.md):

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price using regex heuristics (fast + no LLM cost).
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.
    """
    # Step 1 — initialize session
    session = _new_session(query, wardrobe)

    # Step 2 — parse query
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3 — search listings
    results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = results

    if not results:
        # Branch: no matches — set error, return early
        size_part = f" in size {size}" if size else ""
        price_part = f" under ${max_price:.2f}" if max_price is not None else ""
        session["error"] = (
            f"No listings found for '{description}'{size_part}{price_part}. "
            f"Try broadening your search — remove the size filter or increase your budget."
        )
        return session

    # Step 4 — select top result
    session["selected_item"] = results[0]

    # Step 5 — suggest outfit
    outfit_suggestion = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit_suggestion

    # Step 6 — create fit card
    fit_card = create_fit_card(outfit_suggestion, session["selected_item"])
    session["fit_card"] = fit_card

    # Step 7 — return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
