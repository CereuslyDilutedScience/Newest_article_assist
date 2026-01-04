import os
import tempfile
from pdf2image import convert_from_path

def render_pdf_pages(pdf_path, output_folder="static/pages", dpi=150):
    """
    Render each page of the PDF as a PNG image.
    Returns a list of file paths to the rendered images.
    """

    # Create a unique subfolder for this request
    unique_folder = next(tempfile._get_candidate_names())
    request_folder = os.path.join(output_folder, unique_folder)
    os.makedirs(request_folder, exist_ok=True)

    # Convert PDF pages to PIL images
    pages = convert_from_path(pdf_path, dpi=dpi)

    image_paths = []

    for i, page in enumerate(pages):
        filename = f"page_{i+1}.png"
        filepath = os.path.join(request_folder, filename)

        # Save page as PNG
        page.save(filepath, "PNG")

        # Return relative path so Cloud Run URL works
        image_paths.append(f"static/pages/{unique_folder}/{filename}")

    return image_paths
