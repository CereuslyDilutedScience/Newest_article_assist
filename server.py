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
STATIC_PAGE_FOLDER = "static/pages"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_PAGE_FOLDER, exist_ok=True)

CLOUD_RUN_BASE = "https://comprehendase-backend-470914920668.us-east4.run.app"


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

    print(f"Saved file: {filename}")

    # 1. Extract layout + get OCR-cleaned PDF path
    cleaned_pdf, pages = extract_pdf_layout(filepath)

    # 2. Render images from the SAME PDF used for extraction
    image_paths = render_pdf_pages(cleaned_pdf, output_folder=STATIC_PAGE_FOLDER)

    # 3. Run ontology lookup
    ontology_hits = ontology.extract_ontology_terms(pages)

    # 4. Attach ontology hits
    for page_index, page in enumerate(pages):

        # Words
        for w in page["words"]:
            key = w["text"].lower().strip()
            if key in ontology_hits:
                w["term"] = ontology_hits[key]["label"]
                w["definition"] = ontology_hits[key]["definition"]

        # Phrases
        for phrase_obj in page["phrases"]:
            key = phrase_obj["text"].lower().strip()
            if key in ontology_hits:
                first_word = phrase_obj["words"][0]
                first_word["term"] = ontology_hits[key]["label"]
                first_word["definition"] = ontology_hits[key]["definition"]

                for w in phrase_obj["words"][1:]:
                    w["skip"] = True

        # Add image URL
        page["image_url"] = f"{CLOUD_RUN_BASE}/{image_paths[page_index]}"

    return jsonify({"pages": pages})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
