import os
import tempfile
import fitz  # PyMuPDF

def render_pdf_pages(pdf_path, output_folder="/tmp/pages", dpi=150):
    """
    Render each page of the PDF as a PNG image using PyMuPDF (fitz).
    Returns:
        {
            "folder": unique_folder,
            "images": [
                {
                    "page": page_number,
                    "path": "static/pages/<folder>/page_<n>.png"
                },
                ...
            ]
        }
    """

    # Create a unique subfolder for this request
    unique_folder = next(tempfile._get_candidate_names())
    request_folder = os.path.join(output_folder, unique_folder)
    os.makedirs(request_folder, exist_ok=True)

    # Open PDF with PyMuPDF
    doc = fitz.open(pdf_path)

    # DPI → zoom factor conversion
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    images = []

    for i, page in enumerate(doc):
        page_number = i + 1

        try:
            # Render page to pixmap
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # Save as PNG
            filename = f"page_{page_number}.png"
            filepath = os.path.join(request_folder, filename)
            pix.save(filepath)

            # Return relative path so the frontend can load it
            images.append({
                "page": page_number,
                "path": f"static/pages/{unique_folder}/{filename}"
            })

        except Exception as e:
            print(f"Error rendering page {page_number}: {e}", flush=True)
            continue

    return {
        "folder": unique_folder,
        "images": images
    }
