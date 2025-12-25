from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/extract", methods=["POST"])
def extract():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    pdf_file = request.files["file"]
    filename = secure_filename(pdf_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    pdf_file.save(filepath)

    # TODO: Replace with real extraction logic
    dummy_response = {
        "pages": [
            {
                "page_number": 1,
                "image_url": "/static/sample_page.png",
                "text": "This is placeholder reconstructed text from the backend."
            }
        ],
        "meta": {
            "title": "Sample Article Title",
            "authors": ["Author One", "Author Two"]
        }
    }

    return jsonify(dummy_response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
