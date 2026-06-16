# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock secondhand listings dataset for items that match the user's description, optional size filter, and optional maximum price. Returns a ranked list of matches, best match first.

**Input parameters:**
- `description` (str): Natural-language keywords describing what the user wants (e.g., "vintage graphic tee"). Matched case-insensitively against listing `title`, `description`, `style_tags`, `category`, `colors`, and `brand` fields.
- `size` (str | None): Size string to filter by (e.g., "M", "S/M", "W28"). Matching is case-insensitive substring check so "M" matches "S/M". Pass `None` to skip size filtering.
- `max_price` (float | None): Maximum price inclusive (e.g., 30.0). Pass `None` to skip price filtering.

**What it returns:**
A `list[dict]` of matching listing dictionaries sorted by relevance score (highest first). Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). Returns an empty list `[]` when nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to a specific message like: `"No listings found for '[description]' in size [size] under $[max_price]. Try broadening your search — remove the size filter or increase your budget."` It then returns the session immediately without calling `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Given the thrifted item the user found and their existing wardrobe, calls the Groq LLM to suggest 1–2 complete outfit combinations using pieces the user already owns. If the wardrobe is empty, returns general styling advice instead.

**Input parameters:**
- `new_item` (dict): A listing dict from `search_listings` — the item the user is considering buying. The tool uses `title`, `category`, `style_tags`, `colors`, `condition`, and `price` to give the LLM context.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe-item dicts. Each item has: `id`, `name`, `category`, `colors`, `style_tags`, `notes` (optional). May be empty.

**What it returns:**
A non-empty string (200–400 words) with outfit suggestions. If the wardrobe has items, it names specific wardrobe pieces in the suggestion (e.g., "pair with your dark-wash baggy jeans"). If the wardrobe is empty, it returns a paragraph of general styling advice for the item (what silhouettes, colors, and shoe types pair well with it).

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the tool still returns a useful string (general styling advice) — it does not crash or return an empty string. If the LLM call fails with an exception, the tool catches it and returns: `"Outfit suggestions are temporarily unavailable. Here's a tip: this [category] pairs well with neutral basics and classic denim."`.

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM to generate a short (2–4 sentence) social-media caption for the outfit — the kind of thing someone would post as an Instagram OOTD caption. Uses a high temperature (0.9) so the output varies each time.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. Must be non-empty.
- `new_item` (dict): The listing dict for the thrifted item — the tool uses `title`, `price`, `platform`, `style_tags`, and `colors`.

**What it returns:**
A 2–4 sentence string that reads like an authentic casual OOTD caption: mentions the item name, price, and platform naturally once each; captures the outfit vibe in specific terms (not generic); sounds like a real person posted it. Returns a different caption each time for different inputs. If `outfit` is empty or whitespace-only, returns the error string: `"Can't write a fit card without outfit details — run suggest_outfit first."` (never raises an exception).

**What happens if it fails or returns nothing:**
If `outfit` is empty/whitespace, returns the descriptive error string immediately without calling the LLM. If the LLM call throws an exception, returns: `"Fit card unavailable right now — but this find is worth posting about."`.

---

### Additional Tools (if any)

#### Tool 4: compare_price (Stretch — Price Comparison)

**What it does:**
Given a listing item, estimates whether its price is fair by comparing it to similar listings in the dataset (same category, overlapping style tags).

**Input parameters:**
- `item` (dict): A listing dict with at least `price`, `category`, and `style_tags`.

**What it returns:**
A string assessment like: `"Fair price — similar items average $28.50. This one at $24 is below average."` or `"Above average — comparable [category] listings range from $15–$30, this one is $45."`.

**What happens if it fails or returns nothing:**
If fewer than 2 comparable listings exist, returns: `"Not enough comparable listings to estimate price fairness."`.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop in `run_agent()` follows a strict linear conditional sequence driven entirely by the results of each prior step:

1. **Parse query** — Extract `description`, `size`, and `max_price` from the user's natural-language query using the Groq LLM. Store in `session["parsed"]`.

2. **Call `search_listings`** — Use the parsed parameters. Store the result list in `session["search_results"]`.
   - **Branch: empty list** → set `session["error"]` to a specific actionable message, return session immediately. `suggest_outfit` and `create_fit_card` are never called.
   - **Branch: non-empty list** → set `session["selected_item"] = session["search_results"][0]` (top result), continue.

3. **Call `suggest_outfit`** — Pass `session["selected_item"]` and the wardrobe. Store result in `session["outfit_suggestion"]`.
   - No early-exit branch here (the tool itself handles the empty-wardrobe case internally and always returns a string).

4. **Call `create_fit_card`** — Pass `session["outfit_suggestion"]` and `session["selected_item"]`. Store result in `session["fit_card"]`.

5. **Return session** — The caller checks `session["error"]` first. If `None`, all three output fields are populated.

The agent does **not** call all tools unconditionally. It only calls `suggest_outfit` and `create_fit_card` when `search_listings` returns at least one result.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()` at the top of `run_agent()`. The dict persists across all tool calls within one interaction:

| Key | Set by | Used by |
|-----|--------|---------|
| `session["query"]` | `_new_session()` | LLM query parser |
| `session["parsed"]` | query parser | `search_listings` call |
| `session["search_results"]` | `search_listings` | item selection |
| `session["selected_item"]` | item selection | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | `_new_session()` | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` | returned to UI |
| `session["error"]` | any failure branch | early return, UI display |

No tool re-queries the user. Every tool receives its inputs from the session dict. The session is returned to `handle_query()` in `app.py`, which maps the keys to the three Gradio output panels.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the query (empty list returned) | Sets `session["error"]` = `"No listings found for '[desc]' in size [size] under $[price]. Try broadening your search — remove the size filter or increase your budget."` Returns session early. The other two tools are never called. |
| `suggest_outfit` | `wardrobe["items"]` is empty (new user) | The tool itself detects the empty list and calls the LLM for general styling advice instead of specific pairings. Returns a non-empty string — never crashes or returns `""`. |
| `create_fit_card` | `outfit` parameter is empty or whitespace-only | Returns the string `"Can't write a fit card without outfit details — run suggest_outfit first."` immediately, without calling the LLM. |

---

## Architecture

```
User query
     │
     ▼
Planning Loop ────────────────────────────────────────────────────┐
     │                                                             │
     ├─► [Step 1] LLM query parser                                │
     │         Extracts: description, size, max_price             │
     │         → session["parsed"]                                 │
     │                                                             │
     ├─► [Step 2] search_listings(description, size, max_price)   │
     │         → session["search_results"]                         │
     │                                                             │
     │         results == []                                       │
     │         ├──► session["error"] = "No listings found…"       │
     │         └──► RETURN session  ◄────────────────────── error path
     │                                                             │
     │         results != []                                       │
     │         └──► session["selected_item"] = results[0]         │
     │                                                             │
     ├─► [Step 3] suggest_outfit(selected_item, wardrobe)         │
     │         wardrobe empty → general styling advice            │
     │         wardrobe has items → specific outfit combos        │
     │         → session["outfit_suggestion"]                      │
     │                                                             │
     ├─► [Step 4] create_fit_card(outfit_suggestion, selected_item)│
     │         outfit empty → error string (no LLM call)          │
     │         → session["fit_card"]                               │
     │                                                             │
     └─► RETURN session  ◄─────────────────────────────── happy path
              │
              ▼
         app.py handle_query()
              │
     ┌────────┴──────────────────────┐
     ▼                               ▼
session["error"]            session["selected_item"]
(if set → show in           session["outfit_suggestion"]
 listing panel,             session["fit_card"]
 clear other panels)        (→ three Gradio panels)
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For `search_listings`: Provide the Tool 1 spec above (inputs, return value, failure mode, the TODO steps in tools.py) and ask the AI to implement the function using `load_listings()` from the data loader. Verify the generated code: (a) filters by all three parameters, (b) uses case-insensitive matching for size, (c) scores by keyword overlap across title/description/style_tags/colors/brand, (d) drops zero-score items, (e) returns `[]` (not an exception) on no results. Test with 3 queries before trusting.

For `suggest_outfit`: Provide the Tool 2 spec and the wardrobe schema. Ask the AI to implement the function using Groq's `llama-3.3-70b-versatile`. Verify: (a) empty wardrobe branch calls LLM with a general-styling prompt, (b) non-empty branch formats wardrobe items into the prompt and requests specific named pairings, (c) exception from LLM is caught and returns a fallback string.

For `create_fit_card`: Provide the Tool 3 spec. Ask the AI to implement using Groq at temperature=0.9. Verify: (a) empty `outfit` guard returns error string without LLM call, (b) the caption mentions item name, price, and platform exactly once each, (c) running the same inputs twice gives different outputs (verify temperature is actually applied).

**Milestone 4 — Planning loop and state management:**

Provide the Architecture diagram above, the Planning Loop section, and the State Management table. Ask the AI to implement `run_agent()` in `agent.py`. Verify: (a) the function branches on `search_results == []`, (b) each step stores its result in the correct session key, (c) `suggest_outfit` is never called when search returns empty, (d) the session is returned at the end with all fields populated on success.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** The agent calls the LLM query parser with the raw query string. The LLM extracts: `description = "vintage graphic tee"`, `size = None` (no size mentioned), `max_price = 30.0`. These are stored in `session["parsed"]`.

**Step 2:** The agent calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. The function loads all 40 listings, filters to those priced ≤ $30, scores each by keyword overlap with "vintage graphic tee" (checking title, description, style_tags, colors, brand), drops zero-score items, and returns a sorted list. The top result might be listing `lst_007` — `"Faded Band Tee — $22, Depop, Good condition"` with style_tags `["graphic tee", "vintage", "band tee", "grunge"]`. This list is stored in `session["search_results"]` and `session["selected_item"] = results[0]`.

**Step 3:** Since results are non-empty, the agent calls `suggest_outfit(session["selected_item"], session["wardrobe"])`. The wardrobe has 10 items (example wardrobe). The LLM receives a prompt describing the Faded Band Tee and the 10 wardrobe pieces, and returns something like: *"Pair this faded band tee with your dark-wash baggy jeans and chunky white sneakers for a classic 90s streetwear look. Roll the sleeves once and leave it untucked. Alternatively, layer it under your vintage black denim jacket with the wide-leg khakis and black combat boots for a grungier take."* This is stored in `session["outfit_suggestion"]`.

**Step 4:** The agent calls `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. The LLM receives the item details and outfit suggestion and generates a casual caption at temperature=0.9. Returns something like: *"found this faded band tee on depop for $22 and it was literally made for my baggy jeans era 🖤 vintage graphic tees are never not the move. full look details in comments"*. Stored in `session["fit_card"]`.

**Final output to user:**
- **Top listing panel:** `"Faded Band Tee — $22 | Size L | Good condition | Depop\nVintage-style bootleg tee with faded graphic. Slightly boxy fit. 100% cotton, soft and worn-in.\nTags: graphic tee, vintage, grunge, streetwear, band tee"`
- **Outfit idea panel:** The full `suggest_outfit` string above.
- **Fit card panel:** The Instagram-style caption above.

If `search_listings` had returned `[]` (e.g., query was "designer ballgown size XXS under $5"), the agent would have set `session["error"]` and the first panel would show: `"No listings found for 'designer ballgown' in size XXS under $5.00. Try broadening your search — remove the size filter or increase your budget."` with the other two panels empty.
