import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------
# LOAD LISTS
# ---------------------------------------------------------

def load_list(path):
    with open(path, encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())

def load_definitions(path):
    defs = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "<TAB>" in line:
                term, definition = line.strip().split("<TAB>", 1)
                defs[term.lower()] = definition.strip()
    return defs

def load_synonyms(path):
    mapping = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "<-" in line:
                canonical, variants = line.strip().split("<-", 1)
                canonical = canonical.strip().lower()
                for variant in variants.split(","):
                    mapping[variant.strip().lower()] = canonical
    return mapping

STOPWORDS = load_list("stopwords.txt")
PHRASE_DEFS = load_definitions("phrase_definitions.txt")
WORD_DEFS = load_definitions("definitions.txt")
SYNONYMS = load_synonyms("synonyms.txt")

# ---------------------------------------------------------
# NORMALIZATION
# ---------------------------------------------------------

def normalize_term(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9\- ]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

def apply_synonyms(term: str) -> str:
    if term in SYNONYMS:
        return SYNONYMS[term]
    return term

# ---------------------------------------------------------
# BIOPORTAL CONFIG
# ---------------------------------------------------------

BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"
BIOPORTAL_API_KEY = "7e84a21d-3f8e-4837-b7a9-841fb4847ddf"

MAX_TERMS_PER_DOCUMENT = 1000
MAX_BIOPORTAL_LOOKUPS = 1000

# ---------------------------------------------------------
# BIOPORTAL LOOKUP
# ---------------------------------------------------------

def lookup_term_bioportal(term: str):
    norm = normalize_term(term)
    if not norm:
        return None

    params = {
        "q": norm,
        "apikey": BIOPORTAL_API_KEY,
        "require_exact_match": "false"
    }

    try:
        r = requests.get(BIOPORTAL_SEARCH_URL, params=params, timeout=3)
        r.raise_for_status()
        data = r.json()

        for item in data.get("collection", []):
            label = item.get("prefLabel") or item.get("label")
            defs = item.get("definition")
            definition = defs[0] if isinstance(defs, list) and defs else defs

            if label and definition:
                return {
                    "label": label,
                    "definition": definition,
                    "iri": item.get("@id", "")
                }

        return None

    except Exception:
        return None

# ---------------------------------------------------------
# MAIN ENTRYPOINT — MATCHING AGAINST DEFINITIONS + BIOPORTAL
# ---------------------------------------------------------

def extract_ontology_terms(extracted):
    results = {}
    unmatched_terms = []

    phrases = extracted.get("phrases", [])

    # Build normalized candidates
    candidates = []
    for p in phrases:
        original = p["text"]
        normalized = normalize_term(original)
        normalized = apply_synonyms(normalized)
        candidates.append((original, normalized))

    # Deduplicate by normalized form
    seen_norm = set()
    final_candidates = []
    for original, norm in candidates:
        if norm not in seen_norm:
            seen_norm.add(norm)
            final_candidates.append((original, norm))

    if len(final_candidates) > MAX_TERMS_PER_DOCUMENT:
        final_candidates = final_candidates[:MAX_TERMS_PER_DOCUMENT]

    # -----------------------------------------------------
    # LAYER 1 — PHRASE DEFINITIONS
    # -----------------------------------------------------
    for original, norm in final_candidates:
        if norm in PHRASE_DEFS:
            results[original] = {
                "source": "phrase_definition",
                "definition": PHRASE_DEFS[norm]
            }

    # -----------------------------------------------------
    # LAYER 2 — WORD DEFINITIONS
    # -----------------------------------------------------
    for original, norm in final_candidates:
        if original in results:
            continue  # phrase already matched

        words = original.split()
        for w in words:
            wn = normalize_term(w)
            wn = apply_synonyms(wn)

            if wn in STOPWORDS:
                continue

            if wn in WORD_DEFS:
                results[original] = {
                    "source": "word_definition",
                    "definition": WORD_DEFS[wn]
                }

                # Word-level key for precise highlighting
                results[w] = {
                    "source": "word_definition",
                    "definition": WORD_DEFS[wn]
                }
                break

    # -----------------------------------------------------
    # LAYER 3 — BIOPORTAL LOOKUP
    # -----------------------------------------------------
    to_lookup = []
    for original, norm in final_candidates:
        if original in results:
            continue

        if norm in STOPWORDS:
            continue

        to_lookup.append((original, norm))

    to_lookup = to_lookup[:MAX_BIOPORTAL_LOOKUPS]

    with ThreadPoolExecutor(max_workers=15) as executor:
        future_map = {
            executor.submit(lookup_term_bioportal, norm): (original, norm)
            for (original, norm) in to_lookup
        }

        for future in as_completed(future_map):
            original, norm = future_map[future]
            hit = future.result()

            if hit:
                results[original] = {
                    "source": "ontology",
                    "definition": hit["definition"],
                    "iri": hit.get("iri", "")
                }

                # If single word, also store word-level key
                if " " not in original.strip():
                    results[original.strip()] = {
                        "source": "ontology",
                        "definition": hit["definition"],
                        "iri": hit.get("iri", "")
                    }
            else:
                unmatched_terms.append(original)

    # Attach unmatched list for debugging
    results["_unmatched"] = unmatched_terms

    return results
