from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import time

from extract_text import extract_pdf_layout
from render_pages import render_pdf_pages
import ontology

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://cereuslydilutedscience.github.io"}})

UPLOAD_FOLDER = "uploads"
STATIC_PAGE_FOLDER = "/tmp/pages"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_PAGE_FOLDER, exist_ok=True)

CLOUD_RUN_BASE = "https://comprehendase-backend-470914920668.us-east4.run.app"


# ---------------------------------------------------------
# Serve rendered page images
# ---------------------------------------------------------
@app.route("/static/pages/<path:filename>")
def serve_page_image(filename):
    return send_from_directory("/tmp/pages", filename)


# ---------------------------------------------------------
# Main extraction endpoint
# ---------------------------------------------------------
@app.route("/extract", methods=["POST", "OPTIONS"])
def extract():
    if request.method == "OPTIONS":
        return '', 204

    start_time = time.time()
    print("Received request")

    # Validate upload
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    pdf_file = request.files["file"]
    filename = secure_filename(pdf_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    pdf_file.save(filepath)

    print(f"Saved file: {filename}")

    # -----------------------------------------------------
    # 1. Extract layout (GLOBAL words + phrases)
    # -----------------------------------------------------
    render_result = render_pdf_pages(filepath)
    render_metadata = render_result["images"]

    target_pdf, extracted = extract_pdf_layout(filepath, render_metadata)
    pages_meta = extracted["pages"]
    all_words = extracted["words"]
    all_phrases = extracted["phrases"]

    print(f"Extraction complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 2. Render images from the SAME PDF used for extraction
    # -----------------------------------------------------
    render_result = render_pdf_pages(target_pdf, output_folder=STATIC_PAGE_FOLDER)
    image_folder = render_result["folder"]
    image_list = render_result["images"]

    print(f"Rendering complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 3. Ontology + definitions lookup (UNIFIED)
    # -----------------------------------------------------
    unified_hits = ontology.extract_ontology_terms({
        "words": all_words,
        "phrases": all_phrases
    })

    print(f"Ontology + definitions lookup complete — {time.time() - start_time:.2f}s")

    # -----------------------------------------------------
    # 4. Attach definitions to phrases and individual words
    # -----------------------------------------------------

    # Phrase-level definitions (phrase_definition, word_fallback, ontology)
    for phrase_obj in all_phrases:
        key = phrase_obj["text"].strip()
        hit = unified_hits.get(key)

        if not hit:
            continue

        # CASE 1 — phrase_definition or ontology (single definition)
        if "definition" in hit:
            for w in phrase_obj["words"]:
                w["definition"] = hit["definition"]
                w["source"] = hit["source"]

        # CASE 2 — word_fallback (multiple word-level hits)
        elif hit.get("source") == "word_fallback":
            word_hits = hit.get("words", [])
            # Attach definitions only to the matching words
            for entry in word_hits:
                target_word = entry["word"]
                for w in phrase_obj["words"]:
                    if w["text"].strip().lower() == target_word.lower():
                        w["definition"] = entry["definition"]
                        w["source"] = entry["source"]

    # Word-level definitions (word_definition OR ontology)
    for w in all_words:
        key = w["text"].strip()
        hit = unified_hits.get(key)

        if not hit:
            continue

        # Direct word-level definition
        if hit.get("source") in ("word_definition", "ontology"):
            w["definition"] = hit["definition"]
            w["source"] = hit["source"]

    # -----------------------------------------------------
    # 5. Attach image URLs to page metadata
    # -----------------------------------------------------
    for page in pages_meta:
        page_number = page["page_number"]
        match = next((img for img in image_list if img["page"] == page_number), None)

        if match:
            page["image_url"] = f"{CLOUD_RUN_BASE}/{match['path']}"
        else:
            page["image_url"] = None

    # -----------------------------------------------------
    # 6. Return unified output
    # -----------------------------------------------------
    print(f"Finished all processing — {time.time() - start_time:.2f}s")

    return jsonify({
        "pages": pages_meta,
        "words": all_words,
        "phrases": all_phrases
    })


# ---------------------------------------------------------
# Run locally
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
