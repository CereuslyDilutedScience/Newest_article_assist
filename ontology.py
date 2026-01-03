import requests
import re
from itertools import islice
import os
import sys

# ---------------------------------------------------------
# CONFIG / LIMITS
# ---------------------------------------------------------

MAX_TERMS_PER_DOCUMENT = 1000
OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"

# ---------------------------------------------------------
# COMMON WORD / PATTERN FILTERS
# ---------------------------------------------------------

COMMON_WORDS = set()

SCI_PREFIXES = (
    "bio", "micro", "immuno", "neuro", "cyto", "geno", "patho",
    "chemo", "thermo", "myco", "entomo"
)

SCI_SUFFIXES = (
    "ase","itis","osis","emia","phage","phyte","coccus","viridae","aceae","ales",
    "bacteria","mycetes","mycotina","phyta","phyceae","mycota","archaea"
)

ALLOWED_LOWER = set()
BANNED_TOKENS = set()

BIO_GENOME_CONTEXT = {
    "replication","stability","annotation","assembly"
}

# ---------------------------------------------------------
# AUTHOR / CITATION DETECTION
# ---------------------------------------------------------

def looks_like_author_name(word: str) -> bool:
    return False

def phrase_is_citation(phrase: str) -> bool:
    return False

# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------

def is_acronym(word: str) -> bool:
    return word.isupper() and len(word) >= 3

def clean_token(token: str) -> str:
    return token.strip()

def words_from_phrase_text(phrase_text: str):
    return [clean_token(t) for t in phrase_text.split() if clean_token(t)]

# ---------------------------------------------------------
# WORD-LEVEL CANDIDATE FILTER
# ---------------------------------------------------------

def is_candidate_single_word(raw_word: str) -> bool:
    w = raw_word.strip()
    if not w:
        return False

    lw = w.lower()

    if lw in COMMON_WORDS:
        return False

    if lw in BANNED_TOKENS:
        return False

    if len(lw) <= 2:
        return False

    if any(lw.startswith(p) for p in SCI_PREFIXES):
        return True
    if any(lw.endswith(s) for s in SCI_SUFFIXES):
        return True

    if is_acronym(w):
        return True

    return False

# ---------------------------------------------------------
# PHRASE-LEVEL FILTERING / N-GRAMS
# ---------------------------------------------------------

PROCEDURAL_PATTERNS = []

def phrase_is_procedural_or_metadata(phrase: str) -> bool:
    return False

def is_species_like(words) -> bool:
    return True

def is_candidate_phrase_full(phrase_text: str) -> bool:
    return False

def generate_ngrams(tokens, min_n=2, max_n=3):
    ngrams = []
    L = len(tokens)
    for n in range(min_n, max_n + 1):
        for i in range(L - n + 1):
            ngrams.append(" ".join(tokens[i:i+n]))
    return ngrams

def phrase_ngrams_for_ontology(phrase_text: str):
    """
    Basic n-gram generator for ontology lookup.
    """
    tokens = phrase_text.lower().strip().split()
    results = set()

    # unigrams
    for t in tokens:
        t_clean = t.strip(".,;:()[]{}")
        if len(t_clean) >= 3 and t_clean not in BANNED_TOKENS:
            results.add(t_clean)

    # bigrams
    for bg in generate_ngrams(tokens, min_n=2, max_n=2):
        bg_clean = bg.replace("  ", " ").strip()
        if len(bg_clean.replace(" ", "")) >= 5:
            results.add(bg_clean)

    return sorted(results)

# ---------------------------------------------------------
# OLS4 LOOKUP (Improved Ranking)
# ---------------------------------------------------------

BIO_ONTOLOGY_PREFIXES = {
    "go", "so", "pr", "chebi", "ncbitaxon", "envo", "obi", "eco"
}

def normalize_term(term: str) -> str:
    t = term.lower().strip()
    if t.endswith("proteins"):
        return t[:-1]
    if t.endswith("genomes"):
        return t[:-1]
    return t

def lookup_term_ols4(term: str):
    norm = normalize_term(term)
    params = {
        "q": norm,
        "queryFields": "label",
        "fields": "label,description,iri,ontology_prefix",
        "exact": "false"
    }

    try:
        r = requests.get(OLS4_SEARCH_URL, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()

        docs = data.get("response", {}).get("docs", [])
        if not docs:
            return None

        for d in docs:
            prefix = d.get("ontology_prefix", "").lower()
            if prefix and prefix in BIO_ONTOLOGY_PREFIXES:
                hit = {
                    "label": d.get("label", ""),
                    "definition": d.get("description", ""),
                    "iri": d.get("iri", "")
                }
                print("LOOKUP:", term, "=>", hit, flush=True)
                return hit

        return None

    except Exception as e:
        print("OLS4 lookup failed for", term, ":", e, flush=True)
        return None

# ---------------------------------------------------------
# MAIN ENTRYPOINT
# ---------------------------------------------------------

def extract_ontology_terms(pages_output):
    candidate_terms = set()

    for page in pages_output:
        for w in page.get("words", []):
            raw = w.get("text", "")
            if raw and is_candidate_single_word(raw):
                norm = normalize_term(raw)
                if len(norm) >= 3:
                    candidate_terms.add(norm)

        for phrase_obj in page.get("phrases", []):
            phrase_text = phrase_obj.get("text", "")
            if not phrase_text:
                continue

            for t in phrase_ngrams_for_ontology(phrase_text):
                norm = normalize_term(t)
                if len(norm) >= 3:
                    candidate_terms.add(norm)

    if MAX_TERMS_PER_DOCUMENT is not None and len(candidate_terms) > MAX_TERMS_PER_DOCUMENT:
        candidate_terms = set(islice(sorted(candidate_terms), MAX_TERMS_PER_DOCUMENT))

    print("CANDIDATE TERMS:", sorted(candidate_terms), flush=True)

    found_terms = {}
    for term in candidate_terms:
        hit = lookup_term_ols4(term)
        if hit:
            found_terms[term] = hit

    return found_terms
