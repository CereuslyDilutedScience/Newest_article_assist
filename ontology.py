import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------
# LOAD LISTS
# ---------------------------------------------------------

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

PHRASE_DEFS = load_definitions("phrase_definitions.txt")
WORD_DEFS = load_definitions("word_definitions.txt")
SYNONYMS = load_synonyms("synonyms.txt")

# ---------------------------------------------------------
# NORMALIZATION (used only for internal matching)
# ---------------------------------------------------------

def normalize_term(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9\- ]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

# ---------------------------------------------------------
# BIOPORTAL CONFIG
# ---------------------------------------------------------

BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"
BIOPORTAL_API_KEY = "7e84a21d-3f8e-4837-b7a9-841fb4847ddf"

MAX_TERMS_PER_DOCUMENT = 1000
MAX_BIOPORTAL_LOOKUPS = 1000

# ---------------------------------------------------------
# BIOPORTAL LOOKUP (using ORIGINAL phrase)
# ---------------------------------------------------------

def lookup_term_bioportal(original_phrase: str):
    if not original_phrase.strip():
        return None

    params = {
        "q": original_phrase,   # ORIGINAL phrase, no normalization
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
# CASE‑INSENSITIVE INTERNAL LOOKUP HELPERS
# ---------------------------------------------------------

def lookup_internal_phrase(phrase: str):
    p = phrase.lower()
    for key, definition in PHRASE_DEFS.items():
        if p == key.lower():
            return definition
    return None

def lookup_internal_word(word: str):
    w = word.lower()
    for key, definition in WORD_DEFS.items():
        if w == key.lower():
            return definition
    return None

def apply_synonym_lookup(term: str):
    t = term.lower()
    for variant, canonical in SYNONYMS.items():
        if t == variant.lower():
            return canonical
    return t

# ---------------------------------------------------------
# SUBPHRASE GENERATION
# ---------------------------------------------------------

def generate_subphrases(words):
    n = len(words)
    subs = []
    for length in range(n - 1, 0, -1):  # longest → shortest
        for i in range(n - length + 1):
            sub = " ".join(words[i:i+length])
            subs.append(sub)
    return subs

# ---------------------------------------------------------
# MAIN ENTRYPOINT — FULL FALLBACK PIPELINE
# ---------------------------------------------------------

def extract_ontology_terms(extracted):
    results = {}
    unmatched_terms = []

    phrases = extracted.get("phrases", [])

    # Build candidate list (NO synonym application here)
    candidates = []
    for p in phrases:
        original = p["text"]
        normalized = normalize_term(original)
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

    # ⭐ THIS LOOP WAS MISSING ⭐
    for original, norm in final_candidates:

        # ---------------------------------------------
        # STEP 1 — FULL PHRASE
        # ---------------------------------------------
        phrase = original.strip()

        # Apply synonyms ONLY during lookup
        phrase_lookup = apply_synonym_lookup(phrase)

        # Internal phrase definitions (case‑insensitive)
        hit = lookup_internal_phrase(phrase_lookup)
        if hit:
            results[original] = {
                "source": "phrase_definition",
                "definition": hit
            }
            continue

        # BioPortal full phrase
        hit = lookup_term_bioportal(phrase)
        if hit:
            results[original] = {
                "source": "ontology",
                "definition": hit["definition"],
                "iri": hit.get("iri", "")
            }
            continue

        # ---------------------------------------------
        # STEP 2 — SUBPHRASES
        # ---------------------------------------------
        words = phrase.split()
        subphrases = generate_subphrases(words)

        found = False
        for sub in subphrases:

            sub_lookup = apply_synonym_lookup(sub)

            # Internal subphrase
            hit = lookup_internal_phrase(sub_lookup)
            if hit:
                results[original] = {
                    "source": "phrase_definition",
                    "definition": hit
                }
                found = True
                break

            # BioPortal subphrase
            hit = lookup_term_bioportal(sub)
            if hit:
                results[original] = {
                    "source": "ontology",
                    "definition": hit["definition"],
                    "iri": hit.get("iri", "")
                }
                found = True
                break

        if found:
            continue

        # ---------------------------------------------
        # STEP 3 — WORDS
        # ---------------------------------------------
        word_hits = []
        for w in words:
            wn = normalize_term(w)
            w_lookup = apply_synonym_lookup(w)

            # Internal word definition
            hit = lookup_internal_word(w_lookup)
            if hit:
                word_hits.append({
                    "word": w,
                    "source": "word_definition",
                    "definition": hit
                })
                continue

            # BioPortal word
            hit = lookup_term_bioportal(w)
            if hit:
                word_hits.append({
                    "word": w,
                    "source": "ontology",
                    "definition": hit["definition"],
                    "iri": hit.get("iri", "")
                })
                continue

        if word_hits:
            # Store word-level hits individually
            for entry in word_hits:
                results[entry["word"]] = entry

            # Also attach to the phrase
            results[original] = {
                "source": "word_fallback",
                "words": word_hits
            }
            continue

        # ---------------------------------------------
        # STEP 4 — NO MATCH
        # ---------------------------------------------
        unmatched_terms.append(original)

    results["_unmatched"] = unmatched_terms
    return results

