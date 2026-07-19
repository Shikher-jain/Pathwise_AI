"""Extract raw text from PDF or DOCX resume."""
import io


def parse_resume(file_bytes: bytes, filename: str) -> str:
    """
    file_bytes: raw bytes of the uploaded file
    filename: original filename (used to detect type)
    Returns: plain text string
    """
    ext = filename.lower().split(".")[-1]

    if ext == "pdf":
        return _parse_pdf(file_bytes)
    elif ext in ("docx", "doc"):
        return _parse_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Upload PDF or DOCX.")


def _parse_pdf(file_bytes: bytes) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except Exception as e:
        raise RuntimeError(f"PDF parsing failed: {e}")


def _parse_docx(file_bytes: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())
        return text.strip()
    except Exception as e:
        raise RuntimeError(f"DOCX parsing failed: {e}")
