from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os

from extract_text import extract_pdf_layout
from render_pages import render_pdf_pages
from ontology import (
    generate_ngrams,
    is_candidate_phrase,
    lookup_term_ols4
)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Allow up to 50 MB uploads
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

UPLOAD_FOLDER = "uploads"
STATIC_PAGE_FOLDER = "static/pages"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_PAGE_FOLDER, exist_ok=True)


@app.route("/extract", methods=["POST"])
def extract():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    # Save uploaded PDF
    pdf_file = request.files["file"]
    filename = secure_filename(pdf_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    pdf_file.save(filepath)

    # 1. Extract text + coordinates
    pages = extract_pdf_layout(filepath)

    # 2. Render page images
    image_paths = render_pdf_pages(filepath, output_folder=STATIC_PAGE_FOLDER)

    # 3. Annotate terms using ontology
    for page_index, page in enumerate(pages):
        words = page["words"]
        word_texts = [w["text"] for w in words]

        # Generate n-grams (3-word, 2-word, 1-word)
        ngrams = generate_ngrams(word_texts, max_n=3)

        used_indices = set()

        for start, end, phrase in ngrams:
            # Skip if these words were already matched by a larger phrase
            if any(i in used_indices for i in range(start, end)):
                continue

            # Skip if phrase is not a scientific candidate
            if not is_candidate_phrase(phrase):
                continue

            # Lookup in OLS4
            definition = lookup_term_ols4(phrase)
            if not definition:
                continue

            # Mark indices as used
            for i in range(start, end):
                used_indices.add(i)

            # Attach definition to the FIRST word in the phrase
            words[start]["definition"] = definition["definition"]
            words[start]["term"] = phrase

            # Mark the rest of the words as part of the phrase
            for i in range(start + 1, end):
                words[i]["skip"] = True

        # Attach image URL for this page
        page["image_url"] = "/" + image_paths[page_index]

    return jsonify({"pages": pages})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
