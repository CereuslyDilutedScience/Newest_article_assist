import os
import tempfile
import fitz  # PyMuPDF

def render_pdf_pages(pdf_path, output_folder="/tmp/pages", dpi=150):

    """
    Render each page of the PDF as a PNG image using PyMuPDF (fitz).
    Returns a list of file paths to the rendered images.
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

    image_paths = []

    for i, page in enumerate(doc):
        try:
            # Render page to pixmap
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # Save as PNG
            filename = f"page_{i+1}.png"
            filepath = os.path.join(request_folder, filename)
            pix.save(filepath)

            # Return relative path so Cloud Run can serve it
            image_paths.append(f"static/pages/{unique_folder}/{filename}")

        except Exception as e:
            # Log the error but continue rendering other pages
            print(f"Error rendering page {i+1}: {e}", flush=True)
            continue

    return image_paths
