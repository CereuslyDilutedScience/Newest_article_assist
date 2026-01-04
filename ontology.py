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
    "introduction","discussion","conclusion","figure","table","supplementary",
    "supplement","dataset","section","chapter","page","value","values"
}

# Scientific prefixes and suffixes used as high-signal patterns.
# We will use these more permissively now for higher recall.
SCI_PREFIXES = (
    "bio","micro","immuno","neuro","cyto","geno","patho",
    "chemo","thermo","myco","entomo","viro","bacterio",
    "proto","phyto","toxo","onco","cardio","hepato"
)

SCI_SUFFIXES = (
    # Enzymes / proteins / genes / molecules
    "ase","ases","protein","proteins","enzyme","enzymes",
    "gen","gens","genome","genomes","omic","omics","ome","omes",
    # Microbes / taxa / morphology
    "itis","osis","oses","emia","emias","phage","phages",
    "coccus","cocci","bacter","bacteria","archaea",
    "viridae","aceae","ales","mycetes","mycotina","phyta","phyceae",
    # Cell / structure / tissue
    "plasm","plasma","cyte","cytes","blast","blasts","some","somes",
    "filament","filaments","granule","granules","membrane","membranes",
    # Processes / conditions
    "pathway","pathways","response","responses","signaling","signalling"
)

BANNED_TOKENS = {
    "figure","table","supplementary","supplement","dataset","analysis"
}

# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------

def is_acronym(word: str) -> bool:
    # e.g. DNA, RNA, PCR, IL-6, TNF
    w = word.strip()
    if len(w) < 2:
        return False
    # Allow letters, digits and hyphen, but require at least 2 uppercase letters
    if not re.fullmatch(r"[A-Za-z0-9\-]+", w):
        return False
    return sum(1 for c in w if c.isupper()) >= 2


def clean_token(token: str) -> str:
    # Strip common punctuation at edges, keep internal hyphens
    return token.strip().strip(".,;:()[]{}\"'")


def normalize_term(term: str) -> str:
    t = term.strip().lower()

    # Remove trailing plural forms for some common scientific words
    if t.endswith("proteins"):
        t = t[:-1]
    if t.endswith("genomes"):
        t = t[:-1]

    # Remove punctuation noise but keep spaces and hyphens
    t = re.sub(r"[^a-z0-9\- ]", "", t)

    # Collapse multiple spaces
    t = re.sub(r"\s+", " ", t).strip()

    return t


def core_alpha(token: str) -> str:
    """Return only alphabetic characters for structural checks."""
    return re.sub(r"[^A-Za-z]", "", token)


# ---------------------------------------------------------
# SPECIES NAME DETECTION (HIGH-RECALL FOR BIOLOGICAL TEXTS)
# ---------------------------------------------------------

def looks_like_species_name(tokens_raw):
    """
    Detect binomial species names like 'Mycoplasma bovis'.
    Uses raw tokens to preserve capitalization.
    """
    if len(tokens_raw) != 2:
        return False

    first_raw, second_raw = tokens_raw
    first = core_alpha(first_raw)
    second = core_alpha(second_raw)

    if not first or not second:
        return False

    # First word: Capitalized, alphabetic
    if not first[0].isupper():
        return False
    if not first.isalpha():
        return False

    # Second word: lowercase, alphabetic
    if not second.islower():
        return False
    if not second.isalpha():
        return False

    return True


def looks_like_abbrev_species(tokens_raw):
    """
    Detect abbreviated species like 'M. bovis', 'E. coli'.
    """
    if len(tokens_raw) != 2:
        return False

    first_raw, second_raw = tokens_raw
    first = first_raw.strip()
    second = core_alpha(second_raw)

    if not first or not second:
        return False

    # First token: single capital letter + period (e.g., "M.")
    if not (len(first) == 2 and first[0].isupper() and first[1] == "."):
        return False

    # Second token: lowercase species epithet
    if not second.islower():
        return False
    if not second.isalpha():
        return False

    return True


# ---------------------------------------------------------
# WORD-LEVEL CANDIDATE FILTER (HIGHER RECALL)
# ---------------------------------------------------------

def is_candidate_single_word(raw_word: str) -> bool:
    """
    High-recall filter for single-word candidates.

    Strategy:
    - Reject obvious stopwords / banned tokens
    - Accept:
        * scientific-looking words (prefix/suffix patterns)
        * acronyms (DNA, RNA, TNF-alpha, etc.)
        * longer alphabetic words (>= 5 chars) that are not common words
    """
    w_clean = clean_token(raw_word)
    if not w_clean:
        return False

    lw = w_clean.lower()

    if lw in COMMON_WORDS:
        return False
    if lw in BANNED_TOKENS:
        return False
    if len(lw) <= 2:
        return False

    # Strong scientific patterns first
    if any(lw.startswith(p) for p in SCI_PREFIXES):
        return True
    if any(lw.endswith(s) for s in SCI_SUFFIXES):
        return True

    # Acronyms like DNA, RNA, PCR, TNF-alpha
    if is_acronym(w_clean):
        return True

    # High-recall fallback: longer alphabetic words that are not common words
    alpha_core = core_alpha(w_clean).lower()
    if len(alpha_core) >= 5 and alpha_core not in COMMON_WORDS and alpha_core not in BANNED_TOKENS:
        return True

    return False


# ---------------------------------------------------------
# PHRASE-LEVEL N-GRAMS (HIGHER RECALL)
# ---------------------------------------------------------

def generate_ngrams(tokens, min_n=2, max_n=3):
    ngrams = []
    L = len(tokens)
    for n in range(min_n, max_n + 1):
        for i in range(L - n + 1):
            ngrams.append(tokens[i:i+n])  # keep as list of tokens
    return ngrams


def phrase_ngrams_for_ontology(phrase_text: str):
    """
    Generate unigrams, bigrams, and some trigrams for ontology lookup.

    - Unigrams: all tokens >= 3 chars that are not banned
    - Species names: detect full and abbreviated binomials
    - Bigrams/trigrams: include if they look scientific (any token passes
      single-word candidate filter OR the phrase contains clear scientific patterns)
    """
    if not phrase_text:
        return []

    tokens_raw = phrase_text.strip().split()
    if not tokens_raw:
        return []

    tokens_lower = [t.lower() for t in tokens_raw]
    results = set()

    # Unigrams (high-recall, but still filtered a bit)
    for t_raw, t_low in zip(tokens_raw, tokens_lower):
        t_clean = clean_token(t_low)
        if len(t_clean) >= 3 and t_clean not in BANNED_TOKENS:
            results.add(t_clean)

    # Species detection on raw bigrams
    bigrams_raw = generate_ngrams(tokens_raw, min_n=2, max_n=2)
    for bg_tokens in bigrams_raw:
        if looks_like_species_name(bg_tokens) or looks_like_abbrev_species(bg_tokens):
            phrase = " ".join(bg_tokens)
            results.add(normalize_term(phrase))

    # Bigrams and trigrams (scientific-looking phrases)
    ngrams_tokens = generate_ngrams(tokens_lower, min_n=2, max_n=3)
    for ng_tokens in ngrams_tokens:
        joined_raw = " ".join(ng_tokens)
        joined_clean = clean_token(joined_raw)
        compact = joined_clean.replace(" ", "")

        # Minimum total length to avoid tiny phrases
        if len(compact) < 5:
            continue

        # Check if any component token is a strong candidate
        has_strong_component = any(is_candidate_single_word(tok) for tok in ng_tokens)

        # Also allow some common structural patterns like 'host cells', 'secreted proteins'
        has_scientific_suffix = any(core_alpha(tok).lower().endswith(s) for tok in ng_tokens for s in SCI_SUFFIXES)

        if has_strong_component or has_scientific_suffix:
            results.add(joined_clean)

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
# MAIN ENTRYPOINT (HIGH-RECALL)
# ---------------------------------------------------------

def extract_ontology_terms(pages_output):
    """
    High-recall ontology term extraction.

    Strategy:
    - Collect candidate terms from:
        * single words (using high-recall word filter)
        * phrase n-grams (including species names and scientific phrases)
    - Normalize terms
    - Limit the total number of candidates
    - Query OLS4 and keep only terms that return ontology hits
    """
    candidate_terms = set()

    for page in pages_output:

        # Single words
        for w in page.get("words", []):
            raw = w.get("text", "")
            if not raw:
                continue
            if is_candidate_single_word(raw):
                norm = normalize_term(raw)
                if len(norm) >= 3:
                    candidate_terms.add(norm)

        # Phrases → n-grams and species
        for phrase_obj in page.get("phrases", []):
            phrase_text = phrase_obj.get("text", "")
            if not phrase_text:
                continue

            for t in phrase_ngrams_for_ontology(phrase_text):
                norm = normalize_term(t)
                if len(norm) >= 3:
                    candidate_terms.add(norm)

    # Limit total terms (safety valve)
    if MAX_TERMS_PER_DOCUMENT and len(candidate_terms) > MAX_TERMS_PER_DOCUMENT:
        candidate_terms = set(islice(sorted(candidate_terms), MAX_TERMS_PER_DOCUMENT))

    print("CANDIDATE TERMS (high-recall):", sorted(candidate_terms), flush=True)

    # Lookup each term in OLS4
    found_terms = {}
    for term in candidate_terms:
        hit = lookup_term_ols4(term)
        if hit:
            found_terms[term] = hit

    return found_terms
