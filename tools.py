"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # Step 1 — apply hard filters (price and size)
    filtered = []
    for item in listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None:
            item_size = (item.get("size") or "").lower()
            if size.lower() not in item_size:
                continue
        filtered.append(item)

    if not filtered:
        return []

    # Step 2 — score by keyword overlap with description
    keywords = description.lower().split()

    def _score(item: dict) -> int:
        searchable = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            " ".join(item.get("style_tags", [])),
            " ".join(item.get("colors", [])),
            item.get("brand", "") or "",
            item.get("category", ""),
        ]).lower()
        return sum(1 for kw in keywords if kw in searchable)

    scored = [(item, _score(item)) for item in filtered]

    # Step 3 — drop zero-score items and sort highest first
    matches = [(item, score) for item, score in scored if score > 0]
    matches.sort(key=lambda x: x[1], reverse=True)

    return [item for item, _ in matches]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"Outfit suggestions unavailable: {e}"

    item_name = new_item.get("title", "the item")
    item_category = new_item.get("category", "piece")
    item_tags = ", ".join(new_item.get("style_tags", []))
    item_colors = ", ".join(new_item.get("colors", []))
    item_price = new_item.get("price", "")
    item_platform = new_item.get("platform", "")

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe — give general styling advice
        prompt = (
            f"I just thrifted a '{item_name}' (category: {item_category}, "
            f"style: {item_tags}, colors: {item_colors}, price: ${item_price} from {item_platform}). "
            "I have no other clothes yet. Give me 1–2 paragraphs of general styling advice: "
            "what silhouettes, colors, and shoe types pair well with this piece? "
            "What vibe or aesthetic does it suit? Keep it practical and conversational."
        )
    else:
        # Build a wardrobe summary for the prompt
        wardrobe_lines = []
        for w in wardrobe_items:
            notes = f" ({w['notes']})" if w.get("notes") else ""
            tags = ", ".join(w.get("style_tags", []))
            colors = ", ".join(w.get("colors", []))
            wardrobe_lines.append(
                f"- {w['name']} | colors: {colors} | tags: {tags}{notes}"
            )
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            f"I'm considering buying this thrifted item:\n"
            f"  Name: {item_name}\n"
            f"  Category: {item_category}\n"
            f"  Style tags: {item_tags}\n"
            f"  Colors: {item_colors}\n"
            f"  Price: ${item_price} from {item_platform}\n\n"
            f"Here's my current wardrobe:\n{wardrobe_text}\n\n"
            "Suggest 1–2 complete outfit combinations using the new item and specific "
            "pieces from my wardrobe. Name the exact wardrobe pieces in each suggestion. "
            "Mention any styling tips (tucking, layering, rolling sleeves, etc.). "
            "Keep it conversational and 150–250 words."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        result = response.choices[0].message.content.strip()
        return result if result else (
            f"This {item_category} pairs well with neutral basics and classic denim."
        )
    except Exception:
        return (
            f"Outfit suggestions are temporarily unavailable. "
            f"Here's a tip: this {item_category} pairs well with neutral basics and classic denim."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)
    """
    # Guard: empty or whitespace-only outfit
    if not outfit or not outfit.strip():
        return "Can't write a fit card without outfit details — run suggest_outfit first."

    item_name = new_item.get("title", "this find")
    item_price = new_item.get("price", "")
    item_platform = new_item.get("platform", "")
    item_tags = ", ".join(new_item.get("style_tags", []))
    item_colors = ", ".join(new_item.get("colors", []))

    prompt = (
        f"Write a 2–4 sentence Instagram OOTD caption for this outfit.\n\n"
        f"The thrifted find: '{item_name}' — ${item_price} from {item_platform}.\n"
        f"Colors: {item_colors}. Style vibe: {item_tags}.\n"
        f"Outfit context: {outfit}\n\n"
        "Rules:\n"
        "- Sound like a real person posting an OOTD, not a product description\n"
        "- Mention the item name, price ($), and platform once each, woven in naturally\n"
        "- Capture the specific outfit vibe (not generic)\n"
        "- Casual, lowercase-friendly tone — the kind of caption that gets engagement\n"
        "- 2–4 sentences only\n"
        "Write only the caption, nothing else."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=200,
        )
        result = response.choices[0].message.content.strip()
        return result if result else "Fit card unavailable right now — but this find is worth posting about."
    except Exception:
        return "Fit card unavailable right now — but this find is worth posting about."


# ── Tool 4 (Stretch): compare_price ──────────────────────────────────────────

def compare_price(item: dict) -> str:
    """
    Estimate whether a listing's price is fair by comparing it to similar
    listings in the dataset (same category, overlapping style tags).

    Args:
        item: A listing dict with at least price (float), category (str),
              and style_tags (list[str]).

    Returns:
        A string assessment like:
        "Fair price — similar items average $28.50. This one at $24 is below average."
        Returns an informative message if fewer than 2 comparable listings exist.
    """
    try:
        listings = load_listings()
    except Exception:
        return "Price comparison unavailable — could not load listings data."

    item_price = item.get("price")
    item_category = item.get("category", "")
    item_tags = set(item.get("style_tags", []))
    item_id = item.get("id", "")

    if item_price is None:
        return "Price comparison unavailable — this item has no price listed."

    # Find comparable listings: same category AND at least 1 overlapping style tag
    comparables = [
        lst for lst in listings
        if lst.get("id") != item_id
        and lst.get("category") == item_category
        and bool(item_tags & set(lst.get("style_tags", [])))
    ]

    if len(comparables) < 2:
        return "Not enough comparable listings to estimate price fairness."

    prices = [lst["price"] for lst in comparables]
    avg_price = sum(prices) / len(prices)
    min_price = min(prices)
    max_price = max(prices)

    if item_price < avg_price * 0.85:
        verdict = "Great deal"
        comparison = "below average"
    elif item_price <= avg_price * 1.15:
        verdict = "Fair price"
        comparison = "around average"
    else:
        verdict = "Above average"
        comparison = "above average"

    return (
        f"{verdict} — {len(comparables)} similar {item_category} listings "
        f"range from ${min_price:.2f}–${max_price:.2f}, averaging ${avg_price:.2f}. "
        f"This one at ${item_price:.2f} is {comparison}."
    )
