# FitFindr

An AI-powered secondhand fashion assistant that searches thrift listings, suggests outfits based on your existing wardrobe, and generates shareable fit-card captions — all in one multi-step agent loop.

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Set your Groq API key**

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com) — no credit card required.

**3. Run the app**

```bash
python app.py
```

Open the URL shown in your terminal (usually http://localhost:7860).

**4. Run the tests**

```bash
pytest tests/
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

| | |
|---|---|
| **Purpose** | Searches the mock secondhand listings dataset for items matching the user's description. |
| **Inputs** | `description` (str) — natural-language keywords; `size` (str \| None) — size filter, case-insensitive substring match; `max_price` (float \| None) — maximum price inclusive |
| **Output** | `list[dict]` — matching listing dicts sorted by keyword-overlap score, highest first. Each dict has: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. Returns `[]` on no match — never raises. |

---

### `suggest_outfit(new_item, wardrobe)`

| | |
|---|---|
| **Purpose** | Calls the Groq LLM to suggest 1–2 complete outfits combining the thrifted item with the user's existing wardrobe. Falls back to general styling advice when wardrobe is empty. |
| **Inputs** | `new_item` (dict) — a listing dict from `search_listings`; `wardrobe` (dict) — wardrobe dict with an `items` key (list of wardrobe-item dicts, may be empty) |
| **Output** | Non-empty `str` — outfit suggestions naming specific wardrobe pieces (or general styling advice if wardrobe is empty). Always returns a string. |

---

### `create_fit_card(outfit, new_item)`

| | |
|---|---|
| **Purpose** | Calls the Groq LLM at temperature 0.9 to write a casual Instagram/TikTok-style OOTD caption for the thrifted find. Produces a different caption each run for the same input. |
| **Inputs** | `outfit` (str) — the outfit suggestion from `suggest_outfit`; `new_item` (dict) — listing dict for the thrifted item |
| **Output** | `str` — 2–4 sentence caption that mentions the item name, price, and platform once each. Returns an error message string (not an exception) if `outfit` is empty. |

---

### `compare_price(item)` *(Stretch — Price Comparison)*

| | |
|---|---|
| **Purpose** | Estimates whether a listing's price is fair by comparing it to similar listings (same category, overlapping style tags) in the dataset. |
| **Inputs** | `item` (dict) — a listing dict with `price`, `category`, and `style_tags` |
| **Output** | `str` — assessment like "Fair price — similar items average $28.50. This one at $24 is below average." Returns an informative message if fewer than 2 comparables exist. |

---

## Planning Loop Explanation

The planning loop lives in `run_agent()` in `agent.py`. It is a **linear conditional sequence** — each step's outcome determines whether the next step runs.

```
User query
     │
     ▼
Step 1: Parse query (regex heuristics)
        → session["parsed"] {description, size, max_price}
     │
     ▼
Step 2: search_listings(description, size, max_price)
        → session["search_results"]
     │
     ├── results == []  →  set session["error"], RETURN EARLY
     │                     (suggest_outfit and create_fit_card never called)
     │
     └── results != []  →  session["selected_item"] = results[0]
              │
              ▼
        Step 3: suggest_outfit(selected_item, wardrobe)
                → session["outfit_suggestion"]
              │
              ▼
        Step 4: create_fit_card(outfit_suggestion, selected_item)
                → session["fit_card"]
              │
              ▼
        RETURN session (all three output fields populated)
```

**The key conditional branch:** After `search_listings` runs, the loop checks whether `results` is an empty list. If yes, it sets `session["error"]` with a specific, actionable message and returns immediately — `suggest_outfit` and `create_fit_card` are never called with empty input. This is the only early-exit branch in the loop.

The agent does **not** call all three tools unconditionally. Its behavior differs based on what `search_listings` returns.

---

## State Management

All state for a single interaction lives in a `session` dict initialized by `_new_session()`. No tool re-queries the user or holds its own state. Each tool receives its inputs from the session and writes its output back to the session.

| Session key | Written by | Read by |
|---|---|---|
| `session["query"]` | `_new_session()` | query parser |
| `session["parsed"]` | `_parse_query()` | `search_listings` call |
| `session["search_results"]` | `search_listings` step | item-selection branch |
| `session["selected_item"]` | item-selection branch | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | `_new_session()` | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` step | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` step | `handle_query()` in `app.py` |
| `session["error"]` | any failure branch | early-return logic, `handle_query()` |

The completed session dict is returned to `handle_query()` in `app.py`, which maps the keys to the three Gradio output panels.

---

## Error Handling

### `search_listings` — no results

**Trigger:** The query and filters produce no keyword-overlap matches (e.g., "designer ballgown size XXS under $5").

**Behavior:** The tool returns `[]` without raising an exception. The planning loop detects `not results`, sets:

```
session["error"] = "No listings found for 'designer ballgown' in size XXS under $5.00.
Try broadening your search — remove the size filter or increase your budget."
```

...and returns the session immediately. `suggest_outfit` and `create_fit_card` are never called.

**What the user sees:** The error message appears in the top listing panel. The outfit and fit-card panels are empty.

**Tested by:** `test_search_empty_results()` — confirms `[]` is returned without exception.

---

### `suggest_outfit` — empty wardrobe

**Trigger:** `wardrobe["items"]` is an empty list (new user with no wardrobe entered).

**Behavior:** The tool detects the empty list before building the LLM prompt. It switches to a "general styling advice" prompt that doesn't reference specific wardrobe pieces. The LLM is still called; it returns practical general advice about colors, silhouettes, and shoe types that pair well with the item.

**What the user sees:** A paragraph of general styling advice rather than specific outfit combinations — still a useful, non-empty response.

**Tested by:** `test_suggest_outfit_empty_wardrobe()` — confirms a non-empty string is returned, no exception raised.

---

### `create_fit_card` — empty outfit string

**Trigger:** `outfit` argument is an empty string or contains only whitespace.

**Behavior:** The tool checks `if not outfit or not outfit.strip()` before making any LLM call. If true, it returns immediately with:

```
"Can't write a fit card without outfit details — run suggest_outfit first."
```

No LLM call is made; no exception is raised.

**What the user sees:** A descriptive error message in the fit-card panel.

**Tested by:** `test_create_fit_card_empty_outfit_returns_error_string()` and `test_create_fit_card_whitespace_outfit_returns_error_string()`.

---

## AI Tool Usage

### Instance 1 — Implementing `search_listings`

**Input given to AI:** The Tool 1 spec block from `planning.md` (inputs, return value, failure mode, the five TODO steps) plus the `load_listings()` function signature from `utils/data_loader.py`.

**What it produced:** A working implementation that filtered by price and size and scored by keyword overlap. However, the initial version only searched the `title` field — not `description`, `style_tags`, `colors`, or `brand`.

**What I changed:** Extended the `_score()` function to build a `searchable` string from all six relevant fields. I also added the size-as-substring check (`size.lower() in item_size`) rather than an exact match, which the AI had implemented as exact-match only. Verified with 3 test queries before moving on.

### Instance 2 — Implementing the planning loop in `agent.py`

**Input given to AI:** The full Architecture diagram from `planning.md` (ASCII art), the Planning Loop section, and the State Management table.

**What it produced:** A mostly correct `run_agent()` function that branched on empty results and populated the session dict. The AI used the Groq LLM for query parsing (an entire extra API call on every request).

**What I changed:** Replaced the LLM query parser with a regex-based `_parse_query()` function — this is faster, has no latency cost, and is more predictable for structured patterns like `"under $30"` or `"size M"`. I verified the regex against the five example queries in `app.py` before committing. The session key structure was checked against the planning.md table and matched correctly.

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── tests/
│   └── test_tools.py          # Pytest tests for all three tools
├── tools.py                   # Tool implementations
├── agent.py                   # Planning loop (run_agent)
├── app.py                     # Gradio interface
├── planning.md                # Full design spec and agent diagram
└── requirements.txt
```
