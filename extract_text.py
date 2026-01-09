import pdfplumber
import subprocess
import tempfile
import os
import re

# --- LOAD LISTS ---
def load_list(path):
    with open(path, encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())


STOPWORDS = load_list("stopwords.txt")

# --- GARBAGE FILTER (KEPT EXACTLY AS IS) ---
def is_garbage_phrase(text):
    t = text.lower().strip()
    if not t:
        return True, "empty phrase"
    if "creative commons" in t or "attribution" in t:
        return True, "license text"
    if "doi" in t or "http" in t:
        return True, "DOI/URL"
    if "@" in t:
        return True, "email"
    return False, None

# --- OCR STEP ---
def ocr_pdf(input_path):
    try:
        import fitz
        doc = fitz.open(input_path)
        if any(page.get_text("text").strip() for page in doc):
            print("\n=== OCR SKIPPED: Embedded text detected ===")
            return None
        temp_dir = tempfile.gettempdir()
        unique_name = next(tempfile._get_candidate_names())
        cleaned_path = os.path.join(temp_dir, f"ocr_{unique_name}.pdf")
        print("\n=== OCR STEP ===")
        subprocess.run(["ocrmypdf", "--force-ocr", "--deskew", "--clean", input_path, cleaned_path], check=True)
        return cleaned_path
    except Exception as e:
        print(f"OCR FAILED: {e}")
        return None

# --- MAIN EXTRACTION FUNCTION ---
def extract_pdf_layout(pdf_path, render_metadata):
    print("\n=== STARTING EXTRACTION ===")
    cleaned_pdf = ocr_pdf(pdf_path)
    target_pdf = cleaned_pdf if cleaned_pdf else pdf_path
    all_words = []
    pages_output = []

    # --- EXTRACT WORDS ---
    with pdfplumber.open(target_pdf) as pdf:
        for page_index, page in enumerate(pdf.pages):
            meta = render_metadata[page_index]
            scale_x = meta["rendered_width"] / meta["pdf_width"]
            scale_y = meta["rendered_height"] / meta["pdf_height"]

            try:
                raw_words = page.extract_words(
                    use_text_flow=False,
                    keep_blank_chars=False,
                    x_tolerance=1,
                    y_tolerance=2,
                    extra_attrs=["fontname", "size"]
                ) or []
            except:
                raw_words = []

            normalized = []
            for w in raw_words:
                text = w.get("text", "")
                if not text:
                    continue
                normalized.append({
                    "text": text,
                    "x": float(w["x0"]) * scale_x,
                    "y": float(w["top"]) * scale_y,
                    "width": float(w["x1"] - w["x0"]) * scale_x,
                    "height": float(w["bottom"] - w["top"]) * scale_y,
                    "page": page_index + 1
                })

            # Sort by reading order
            normalized.sort(key=lambda w: (round(w["y"] / 5), w["x"]))

            # --- KEEP HYPHEN MERGING EXACTLY AS IS ---
            merged = []
            i = 0
            while i < len(normalized):
                current = normalized[i]
                if current["text"].endswith("-") and (i + 1) < len(normalized):
                    nxt = normalized[i + 1]
                    current["text"] = current["text"].rstrip("-") + nxt["text"]
                    merged.append(current)
                    i += 2
                else:
                    merged.append(current)
                    i += 1

            all_words.extend(merged)
            pages_output.append({
                "page_number": page_index + 1,
                "width": float(page.width),
                "height": float(page.height)
            })

    # --- SORT ALL WORDS GLOBALLY ---
    all_words.sort(key=lambda w: (w["page"], round(w["y"] / 5), w["x"]))


    # --- NEW GREEDY STOPWORD-BASED PHRASE EXTRACTION ---
    phrases = []
    max_len = 5
    n = len(all_words)
    i = 0

    while i < n:
        w = all_words[i]
        raw = w["text"]

        # Clean token for stopword check
        token = raw.lower().strip(".,;:()[]{}")

        # Skip stopwords entirely
        if token in STOPWORDS:
            i += 1
            continue

        # Start a new phrase
        phrase_words = [w]
        phrase_tokens = [token]

        # Expand right greedily
        j = i + 1
        while j < n and len(phrase_words) < max_len:
            nxt_raw = all_words[j]["text"]
            nxt_token = nxt_raw.lower().strip(".,;:()[]{}")

            if nxt_token in STOPWORDS:
                break  # stop expansion

            phrase_words.append(all_words[j])
            phrase_tokens.append(nxt_token)
            j += 1

        # Emit phrase (even if length 1)
        phrase_text = " ".join([pw["text"] for pw in phrase_words]).strip()
        phrase_text_clean = phrase_text.lower()

        rejected, reason = is_garbage_phrase(phrase_text_clean)
        if not rejected:
            phrases.append({
                "text": phrase_text,
                "words": phrase_words.copy()
            })

        # Move index to next word after phrase
        i = j

    return target_pdf, {
        "pages": pages_output,
        "words": all_words,
        "phrases": phrases
    }
