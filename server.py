from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import time

from extract_text import extract_pdf_layout
from render_pages import render_pdf_pages
from ontology import (
    generate_ngrams,
    is_candidate_phrase,
    lookup_term_ols4
)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://cereuslydilutedscience.github.io"}})

# Allow up to 50 MB uploads
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

UPLOAD_FOLDER = "uploads"
STATIC_PAGE_FOLDER = "static/pages"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_PAGE_FOLDER, exist_ok=True)

# Base URL of your Cloud Run service
CLOUD_RUN_BASE = "https://comprehendase-470914920668.us-east4.run.app"

# Serve rendered page images
@app.route("/static/pages/<path:filename>")
def serve_page_image(filename):
    return send_from_directory(STATIC_PAGE_FOLDER, filename)


@app.route("/extract", methods=["POST", "OPTIONS"])
def extract():
    if request.method == "OPTIONS":
        return '', 204

    start_time = time.time()
    print("Received request")

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    pdf_file = request.files["file"]
    filename = secure_filename(pdf_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    pdf_file.save(filepath)
    print(f"Saved file: {filename} — {time.time() - start_time:.2f}s")

    pages = extract_pdf_layout(filepath)
    print(f"Extracted layout — {time.time() - start_time:.2f}s")

    image_paths = render_pdf_pages(filepath, output_folder=STATIC_PAGE_FOLDER)
    print(f"Rendered pages — {time.time() - start_time:.2f}s")

    for page_index, page in enumerate(pages):
        print(f"Annotating page {page_index} — {time.time() - start_time:.2f}s")
        words = page["words"]
        word_texts = [w["text"] for w in words]

        ngrams = generate_ngrams(word_texts, max_n=3)
        used_indices = set()

        for start, end, phrase in ngrams:
            if any(i in used_indices for i in range(start, end)):
                continue
            if not is_candidate_phrase(phrase):
                continue

            print(f"Looking up: {phrase}")
            definition = lookup_term_ols4(phrase)
            if not definition:
                continue

            for i in range(start, end):
                used_indices.add(i)

            words[start]["definition"] = definition["definition"]
            words[start]["term"] = phrase

            for i in range(start + 1, end):
                words[i]["skip"] = True

        # Return full Cloud Run URL for images
        page["image_url"] = f"{CLOUD_RUN_BASE}/{image_paths[page_index]}"

    print(f"Finished all processing — {time.time() - start_time:.2f}s")
    return jsonify({"pages": pages})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
