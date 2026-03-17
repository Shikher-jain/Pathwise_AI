import pdfplumber


def extract_text(path: str) -> str:
    """Extract text from all pages in a PDF file.

    Raises:
        FileNotFoundError: If the PDF file does not exist.
        ValueError: If no readable text is extracted.
    """
    from pathlib import Path

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Resume file not found: {file_path}")

    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    extracted = text.strip()
    if not extracted:
        raise ValueError("No readable text found in uploaded resume")

    return extracted
