import requests
import re
from itertools import islice

# ---------------------------------------------------------
# CONFIG / LIMITS
# ---------------------------------------------------------

MAX_TERMS_PER_DOCUMENT = 1000
OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"

# ---------------------------------------------------------
# COMMON WORD / PATTERN FILTERS
# ---------------------------------------------------------

COMMON_WORDS = {
    "the","and","for","with","from","that","this","were","was","are","but",
    "into","onto","between","among","after","before","during","under","over",
    "using","used","based","data","study","analysis","results","methods",
    "introduction","discussion","conclusion","figure","table","supplementary"
}

SCI_PREFIXES = (
    "bio","micro","immuno","neuro","cyto","geno","patho",
    "chemo","thermo","myco","entomo","viro","bacterio"
)

SCI_SUFFIXES = (
    "ase","itis","osis","emia","phage","phyte","coccus","viridae","aceae","ales",
    "bacteria","mycetes","mycotina","phyta","phyceae","mycota","archaea",
    "genome","protein","enzyme","lipid","membrane","operon"
)

BANNED_TOKENS = {
    "figure","table","supplementary","supplement","dataset","analysis"
}

# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------

def is_acronym(word: str) -> bool:
    return word.isupper() and len(word) >= 3

def clean_token(token: str) -> str:
    return token.strip().strip(".,;:()[]{}")

def normalize_term(term: str) -> str:
    t = term.lower().strip()

    # Remove trailing plural forms
    if t.endswith("proteins"):
        return t[:-1]
    if t.endswith("genomes"):
        return t[:-1]

    # Remove punctuation noise
    t = re.sub(r"[^a-z0-9\- ]", "", t)

    return t

# ---------------------------------------------------------
# WORD-LEVEL CANDIDATE FILTER
# ---------------------------------------------------------

def is_candidate_single_word(raw_word: str) -> bool:
    w = clean_token(raw_word)
    if not w:
        return False

    lw = w.lower()

    if lw in COMMON_WORDS:
        return False
    if lw in BANNED_TOKENS:
        return False
    if len(lw) <= 2:
        return False

    # Scientific prefixes/suffixes
    if any(lw.startswith(p) for p in SCI_PREFIXES):
        return True
    if any(lw.endswith(s) for s in SCI_SUFFIXES):
        return True

    # Acronyms like DNA, RNA, PCR
    if is_acronym(w):
        return True

    return False

# ---------------------------------------------------------
# PHRASE-LEVEL N-GRAMS
# ---------------------------------------------------------

def generate_ngrams(tokens, min_n=2, max_n=3):
    ngrams = []
    L = len(tokens)
    for n in range(min_n, max_n + 1):
        for i in range(L - n + 1):
            ngrams.append(" ".join(tokens[i:i+n]))
    return ngrams

def phrase_ngrams_for_ontology(phrase_text: str):
    """
    Generate unigrams and bigrams for ontology lookup.
    """
    tokens = phrase_text.lower().strip().split()
    results = set()

    # Unigrams
    for t in tokens:
        t_clean = clean_token(t)
        if len(t_clean) >= 3 and t_clean not in BANNED_TOKENS:
            results.add(t_clean)

    # Bigrams
    for bg in generate_ngrams(tokens, min_n=2, max_n=2):
        bg_clean = clean_token(bg)
        if len(bg_clean.replace(" ", "")) >= 5:
            results.add(bg_clean)

    return sorted(results)

# ---------------------------------------------------------
# OLS4 LOOKUP
# ---------------------------------------------------------

BIO_ONTOLOGY_PREFIXES = {
    "go","so","pr","chebi","ncbitaxon","envo","obi","eco"
}

def lookup_term_ols4(term: str):
    norm = normalize_term(term)
    if not norm:
        return None

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

        # Prefer biological ontologies
        for d in docs:
            prefix = d.get("ontology_prefix", "").lower()
            if prefix in BIO_ONTOLOGY_PREFIXES:
                return {
                    "label": d.get("label", ""),
                    "definition": d.get("description", ""),
                    "iri": d.get("iri", "")
                }

        # Fallback: return first result
        d = docs[0]
        return {
            "label": d.get("label", ""),
            "definition": d.get("description", ""),
            "iri": d.get("iri", "")
        }

    except Exception as e:
        print("OLS4 lookup failed for", term, ":", e, flush=True)
        return None

# ---------------------------------------------------------
# MAIN ENTRYPOINT
# ---------------------------------------------------------

def extract_ontology_terms(pages_output):
    candidate_terms = set()

    # Collect candidate terms from words + phrases
    for page in pages_output:

        # Single words
        for w in page.get("words", []):
            raw = w.get("text", "")
            if raw and is_candidate_single_word(raw):
                norm = normalize_term(raw)
                if len(norm) >= 3:
                    candidate_terms.add(norm)

        # Phrases → n-grams
        for phrase_obj in page.get("phrases", []):
            phrase_text = phrase_obj.get("text", "")
            if not phrase_text:
                continue

            for t in phrase_ngrams_for_ontology(phrase_text):
                norm = normalize_term(t)
                if len(norm) >= 3:
                    candidate_terms.add(norm)

    # Limit total terms
    if MAX_TERMS_PER_DOCUMENT and len(candidate_terms) > MAX_TERMS_PER_DOCUMENT:
        candidate_terms = set(islice(sorted(candidate_terms), MAX_TERMS_PER_DOCUMENT))

    print("CANDIDATE TERMS:", sorted(candidate_terms), flush=True)

    # Lookup each term
    found_terms = {}
    for term in candidate_terms:
        hit = lookup_term_ols4(term)
        if hit:
            found_terms[term] = hit

    return found_terms
