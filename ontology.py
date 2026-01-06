import requests
import re
from itertools import islice
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

MAX_TERMS_PER_DOCUMENT = 500
MAX_BIOPORTAL_LOOKUPS = 300

BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"
BIOPORTAL_API_KEY = "7e84a21d-3f8e-4837-b7a9-841fb4847ddf"

# ---------------------------------------------------------
# BASIC NORMALIZATION
# ---------------------------------------------------------

def clean_token(t: str) -> str:
    return t.strip().strip(".,;:()[]{}\"'")

def normalize_term(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9\- ]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

def core_alpha(t: str) -> str:
    return re.sub(r"[^A-Za-z]", "", t)

# ---------------------------------------------------------
# SPECIES DETECTION
# ---------------------------------------------------------

def looks_like_species(tokens):
    if len(tokens) != 2:
        return False
    first, second = tokens
    first_alpha = core_alpha(first)
    second_alpha = core_alpha(second)
    if not first_alpha or not second_alpha:
        return False
    return first_alpha[0].isupper() and second_alpha.islower()

def looks_like_abbrev_species(tokens):
    if len(tokens) != 2:
        return False
    first, second = tokens
    return len(first) == 2 and first[0].isupper() and first[1] == "." and core_alpha(second).islower()

# ---------------------------------------------------------
# PHRASE-FIRST N-GRAM GENERATION
# ---------------------------------------------------------

def generate_ngrams(tokens, min_n=1, max_n=5):
    L = len(tokens)
    for n in range(min_n, max_n + 1):
        for i in range(L - n + 1):
            yield tokens[i:i+n]

def extract_scientific_phrases(phrase_text: str):
    """
    Phrase-first extraction:
    - Always include full phrase
    - Include 1–5 word n-grams
    - Allow acronyms, hyphens, numbers
    - Keep species names
    """
    if not phrase_text:
        return []

    tokens_raw = phrase_text.split()
    tokens_clean = [clean_token(t) for t in tokens_raw]
    tokens_norm = [normalize_term(t) for t in tokens_clean]

    results = set()

    # 1) Full phrase (always included)
    full_norm = normalize_term(phrase_text)
    if full_norm:
        results.add(full_norm)

    # 2) Species names
    for ng in generate_ngrams(tokens_raw, 2, 2):
        if looks_like_species(ng) or looks_like_abbrev_species(ng):
            results.add(normalize_term(" ".join(ng)))

    # 3) N-grams (1–5 words)
    for ng in generate_ngrams(tokens_norm, 1, 5):
        joined = " ".join(ng)
        compact = joined.replace(" ", "")

        # Skip extremely short junk
        if len(compact) < 3:
            continue

        # Allow acronyms, hyphens, numbers
        results.add(joined)

    return sorted(results)

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
# MAIN EXTRACTION ENTRYPOINT
# ---------------------------------------------------------

def extract_ontology_terms(extracted):
    """
    extracted = {
        "words": [...],
        "phrases": [...]
    }
    """

    candidate_terms = set()

    # --- PHRASE-FIRST EXTRACTION ---
    for phrase_obj in extracted.get("phrases", []):
        text = phrase_obj.get("text", "")
        for t in extract_scientific_phrases(text):
            if t:
                candidate_terms.add(t)

    # --- FALLBACK: SINGLE WORDS (VERY PERMISSIVE) ---
    for w in extracted.get("words", []):
        raw = w.get("text", "")
        norm = normalize_term(raw)
        if norm and len(norm) >= 3:
            candidate_terms.add(norm)

    # Limit
    candidate_terms = sorted(candidate_terms)
    if len(candidate_terms) > MAX_TERMS_PER_DOCUMENT:
        candidate_terms = candidate_terms[:MAX_TERMS_PER_DOCUMENT]

    print("CANDIDATE TERMS:", candidate_terms, flush=True)
    return candidate_terms

# ---------------------------------------------------------
# PARALLEL LOOKUP
# ---------------------------------------------------------

def process_terms(candidate_terms):
    found_terms = {}
    terms_to_lookup = candidate_terms[:MAX_BIOPORTAL_LOOKUPS]

    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_term = {
            executor.submit(lookup_term_bioportal, term): term
            for term in terms_to_lookup
        }

        for future in as_completed(future_to_term):
            term = future_to_term[future]
            hit = future.result()
            if hit:
                found_terms[term] = hit

    return found_terms
