import requests
import re
from itertools import islice
import sys

# ---------------------------------------------------------
# CONFIG / LIMITS
# ---------------------------------------------------------

MAX_TERMS_PER_DOCUMENT = 300
OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"

# ---------------------------------------------------------
# COMMON WORD / PATTERN FILTERS
# ---------------------------------------------------------

COMMON_WORDS = {
    "the","and","for","with","from","that","this","were","have","been",
    "in","on","of","to","as","by","is","are","be","or","an","at","it",
    "we","was","using","used","use","our","their","these","those",
    "its","they","them","he","she","his","her","you","your","i",
    "into","onto","within","between","through","over","under","out",
    "up","down","off","than","then","also","such","each","both","via",
    "per","among","amid","despite","during","before","after","because"
}

# Scientific prefixes/suffixes for biological terms
SCI_PREFIXES = (
    "bio", "micro", "immuno", "neuro", "cyto", "geno", "patho",
    "chemo", "thermo", "myco", "entomo"
)

SCI_SUFFIXES = (
    "ase","itis","osis","emia","phage","phyte","coccus","viridae","aceae","ales",
    "bacteria","mycetes","mycotina","phyta","phyceae","mycota","archaea"
)

# Allowed lowercase biological terms
ALLOWED_LOWER = {
    "biofilm", "larvae", "pathogen", "pathogenic", "lipoprotein", "lipoproteins",
    "adhesion", "invasion", "dissemination", "strain", "strains",
    "protein", "proteins", "microorganism", "microorganisms", "enzyme",
    "bacteria", "fungi", "colony", "colonies",
    "pneumonia", "mastitis", "arthritis", "otitis", "media"
}

# ---------------------------------------------------------
# AUTHOR / CITATION DETECTION
# ---------------------------------------------------------

def looks_like_author_name(word: str) -> bool:
    """Detect capitalized author last names commonly found in citations."""
    if re.match(r"^[A-Z][a-z]+$", word):
        return True
    if re.match(r"^[A-Z][a-z]+,$", word):
        return True
    return False


def phrase_is_citation(phrase: str) -> bool:
    """Detect multi-word citation patterns."""
    lower = phrase.lower()

    if "et al" in lower:
        return True

    # Capitalized Lastname Lastname
    if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+$", phrase):
        return True

    # Lastname, YEAR
    if re.match(r"^[A-Z][a-z]+, \d{4}$", phrase):
        return True

    return False

# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------

def is_acronym(word: str) -> bool:
    """Detect standalone acronyms (PCR, ITS, etc.)."""
    return word.isupper() and len(word) >= 3


def clean_token(token: str) -> str:
    """Strip punctuation and control chars from a token."""
    token = token.strip().strip(".,;:()[]{}")
    token = token.replace("\u200b", "").replace("\u00ad", "").replace("\u2011", "")
    return token


def words_from_phrase_text(phrase_text: str):
    """Split phrase text into cleaned word tokens."""
    raw_parts = phrase_text.split()
    cleaned = []
    for p in raw_parts:
        t = clean_token(p)
        if t:
            cleaned.append(t)
    return cleaned

# ---------------------------------------------------------
# WORD-LEVEL CANDIDATE FILTER
# ---------------------------------------------------------

def is_candidate_single_word(raw_word: str) -> bool:
    """
    Decide if a single word is worth sending to OLS4.
    raw_word is the original token (case preserved).
    """
    if not raw_word:
        return False

    word_clean = re.sub(r"[^A-Za-z0-9\-]", "", raw_word)
    if not word_clean:
        return False

    if len(word_clean) < 3:
        return False

    lower = word_clean.lower()

    # Remove common words
    if lower in COMMON_WORDS:
        return False

    # Remove pure numbers
    if word_clean.isdigit():
        return False

    # Remove author names
    if looks_like_author_name(word_clean):
        return False

    # Remove standalone acronyms
    if is_acronym(word_clean):
        return False

    # Allow lowercase biological terms
    if word_clean.islower():
        if lower in ALLOWED_LOWER:
            return True
        if lower.startswith(SCI_PREFIXES):
            return True
        if lower.endswith(SCI_SUFFIXES):
            return True
        return False

    # Gene-like patterns (uvrC, rpoB, etc.)
    if re.match(r"^[A-Za-z]{2,6}\d*[A-Za-z]*$", word_clean):
        return True

    # Strain-like patterns (PG45, HB0801, XBY01)
    if re.match(r"^[A-Z]{1,4}\d{1,4}[A-Za-z0-9]*$", word_clean):
        return True

    # Family names (Mycoplasmataceae)
    if lower.endswith("aceae"):
        return True

    # Order names (Mollicutes, etc.)
    if lower.endswith("ales"):
        return True

    # Capitalized biological/taxonomic words
    if re.match(r"^[A-Z][a-z]+$", word_clean):
        return True

    # Broader scientific names
    if re.match(r"^[A-Z][a-zA-Z]+$", word_clean):
        return True

    # Protein-like words
    if lower.endswith("protein") or lower.endswith("proteins"):
        return True

    # Scientific prefixes/suffixes
    if lower.startswith(SCI_PREFIXES):
        return True
    if lower.endswith(SCI_SUFFIXES):
        return True

    return False

# ---------------------------------------------------------
# PHRASE-LEVEL FILTERING / N-GRAMS
# ---------------------------------------------------------

# Procedural / narrative / metadata patterns to remove entirely
PROCEDURAL_PATTERNS = [
    "were incubated", "cultures were", "incubated at",
    "listed as", "co-first", "were", "was", "to isolate",
    "important pathogen", "serious pneumonia", "an important",
    "the genome size", "genome size of", "gc content",
    "complete genome", "genome sequence", "sequence of",
    "international license", "volume", "issue", "e00001",
    "accession", "genbank", "samn", "cp0", "biosample",
    "bioproject", "biosystems"
]

def phrase_is_procedural_or_metadata(phrase: str) -> bool:
    """Remove procedural, narrative, accession, and metadata fragments."""
    lower = phrase.lower()
    for pat in PROCEDURAL_PATTERNS:
        if pat in lower:
            return True
    return False


def is_species_like(words) -> bool:
    """Case-insensitive species detection (two words, both non-trivial)."""
    if len(words) < 2:
        return False

    w1, w2 = words[0], words[1]

    if not w1.isalpha() or not w2.isalpha():
        return False

    if len(w1) < 3 or len(w2) < 3:
        return False

    if w1.lower() in COMMON_WORDS or w2.lower() in COMMON_WORDS:
        return False

    return True


def is_candidate_phrase_full(phrase_text: str) -> bool:
    """Decide if a multi-word phrase (as a whole) is worth querying."""
    if not phrase_text:
        return False

    if phrase_is_citation(phrase_text):
        return False

    if phrase_is_procedural_or_metadata(phrase_text):
        return False

    words = words_from_phrase_text(phrase_text)
    if len(words) < 2:
        return False

    # Remove author lists
    if all(looks_like_author_name(w) for w in words):
        return False

    # Species-like patterns
    if is_species_like(words):
        return True

    # Strain / serotype / subspecies
    lower = phrase_text.lower()
    if "strain" in lower or "serotype" in lower or "subspecies" in lower:
        return True

    # Biological multi-word phrases: keep only if at least one token is biological
    for w in words:
        wc = re.sub(r"[^A-Za-z0-9\-]", "", w)
        if len(wc) < 3:
            continue
        if wc.lower() in COMMON_WORDS:
            continue
        if is_candidate_single_word(wc):
            return True

    return False


def generate_ngrams(tokens, min_n=2, max_n=3):
    """Generate n-grams (as strings) from a list of tokens."""
    ngrams = []
    L = len(tokens)
    for n in range(min_n, max_n + 1):
        if L < n:
            continue
        for i in range(L - n + 1):
            ngram = " ".join(tokens[i:i+n])
            ngrams.append(ngram)
    return ngrams


def phrase_ngrams_for_ontology(phrase_text: str):
    """
    From a phrase, produce:
      - full phrase (if candidate)
      - 2-grams
      - 3-grams
    All filtered by strict Option-B rules.
    """
    results = []

    if is_candidate_phrase_full(phrase_text):
        results.append(phrase_text)

    tokens = words_from_phrase_text(phrase_text)
    if len(tokens) < 2:
        return results

    for ng in generate_ngrams(tokens, min_n=2, max_n=3):
        if phrase_is_procedural_or_metadata(ng):
            continue
        if phrase_is_citation(ng):
            continue

        words = words_from_phrase_text(ng)
        keep = False
        for w in words:
            wc = re.sub(r"[^A-Za-z0-9\-]", "", w)
            if len(wc) < 3:
                continue
            if wc.lower() in COMMON_WORDS:
                continue
            if is_candidate_single_word(wc):
                keep = True
                break

        if keep:
            results.append(ng)

    return results

# ---------------------------------------------------------
# OLS4 LOOKUP
# ---------------------------------------------------------

def lookup_term_ols4(term: str):
    """Query the OLS4 API for a scientific term."""
    params = {
        "q": term,
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

        term_lower = term.lower()

        # Stage 1: exact label match
        for doc in docs:
            label = doc.get("label", "")
            definition_list = doc.get("description") or []
            definition = definition_list[0].strip() if definition_list else ""
            if label and label.lower() == term_lower and definition:
                return {
                    "label": label,
                    "definition": definition,
                    "iri": doc.get("iri")
                }

        # Stage 2: label contains term
        for doc in docs:
            label = doc.get("label", "")
            definition_list = doc.get("description") or []
            definition = definition_list[0].strip() if definition_list else ""
            if not label:
                continue
            if term_lower not in label.lower():
                continue
            if definition:
                return {
                    "label": label,
                    "definition": definition,
                    "iri": doc.get("iri")
                }

        return None

    except Exception:
        return None

# ---------------------------------------------------------
# MAIN ENTRYPOINT
# ---------------------------------------------------------

def extract_ontology_terms(pages_output):
    """
    Given pages_output from extract_text.py, return:
      term -> { label, definition, iri }
    """
    candidate_terms = set()

    # 1. Collect candidates
    for page in pages_output:

        # Single words
        for w in page.get("words", []):
            raw = w.get("text", "")
            if raw and is_candidate_single_word(raw):
                candidate_terms.add(raw)

        # Phrases and n-grams
        for phrase_obj in page.get("phrases", []):
            phrase_text = phrase_obj.get("text", "")
            if not phrase_text:
                continue

            for t in phrase_ngrams_for_ontology(phrase_text):
                candidate_terms.add(t)

    # 2. Cap total terms
    if len(candidate_terms) > MAX_TERMS_PER_DOCUMENT:
        candidate_terms = set(islice(sorted(candidate_terms), MAX_TERMS_PER_DOCUMENT))

    print("CANDIDATE TERMS:", sorted(candidate_terms), file=sys.stdout, flush=True)

    # 3. Query OLS4
    found_terms = {}
    for term in sorted(candidate_terms):
        hit = lookup_term_ols4(term)
        if hit:
            found_terms[term] = hit

    return found_terms
