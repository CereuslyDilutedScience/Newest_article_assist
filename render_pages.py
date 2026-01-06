import os
import tempfile
import fitz  # PyMuPDF

def render_pdf_pages(pdf_path, output_folder="/tmp/pages", dpi=150):
    """
    Render each page of the PDF as a PNG image using PyMuPDF (fitz).
    """

    unique_folder = next(tempfile._get_candidate_names())
    request_folder = os.path.join(output_folder, unique_folder)
    os.makedirs(request_folder, exist_ok=True)

    doc = fitz.open(pdf_path)

    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    images = []

    for i, page in enumerate(doc):
        page_number = i + 1

        try:
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # Page-level debug only (safe)
            print(f"[RENDER DEBUG] Page {page_number}")
            print(f"  PyMuPDF page rect: width={page.rect.width}, height={page.rect.height}")
            print(f"  Rendered PNG size: width={pix.width}, height={pix.height}")

            filename = f"page_{page_number}.png"
            filepath = os.path.join(request_folder, filename)
            pix.save(filepath)

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
