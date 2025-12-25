import fitz  # PyMuPDF

def extract_pdf_layout(pdf_path):
    """
    Extract words and their coordinates from each page of the PDF.
    Returns a list of pages, each containing a list of word dictionaries.
    """

    doc = fitz.open(pdf_path)
    pages_output = []

    for page_index, page in enumerate(doc):
        words_raw = page.get_text("words")  
        # PyMuPDF returns: [x0, y0, x1, y1, "word", block_no, line_no, word_no]

        words = []
        for w in words_raw:
            x0, y0, x1, y1, text, block, line, word_no = w

            words.append({
                "text": text,
                "x": float(x0),
                "y": float(y0),
                "width": float(x1 - x0),
                "height": float(y1 - y0),
                "block": int(block),
                "line": int(line),
                "word_no": int(word_no)
            })

        pages_output.append({
            "page_number": page_index + 1,
            "width": page.rect.width,
            "height": page.rect.height,
            "words": words
        })

    doc.close()
    return pages_output
