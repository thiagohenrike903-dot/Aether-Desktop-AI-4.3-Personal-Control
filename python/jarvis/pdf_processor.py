from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.pdf")

_MAX_PDF_BYTES = 10 * 1024 * 1024
_MAX_PDF_BASE64_CHARS = 14 * 1024 * 1024
_MAX_PDF_PAGES = 500
_MAX_TEXT_CHARS = 250_000


def _extract_document(doc: Any, file_name: str) -> dict[str, Any]:
    page_count = len(doc)
    if page_count > _MAX_PDF_PAGES:
        return {
            "ok": False,
            "error": f"O PDF excede o limite de {_MAX_PDF_PAGES} páginas.",
        }

    pages: list[dict[str, Any]] = []
    full_parts: list[str] = []
    remaining = _MAX_TEXT_CHARS
    total_chars = 0
    for page_num in range(page_count):
        text = doc[page_num].get_text()
        total_chars += len(text)
        included = text[:remaining] if remaining > 0 else ""
        if included:
            full_parts.append(f"\n--- Página {page_num + 1} ---\n{included}")
            remaining -= len(included)
        pages.append({
            "page": page_num + 1,
            "text": included,
            "char_count": len(text),
            "truncated": len(included) < len(text),
        })

    full_text = "".join(full_parts)
    return {
        "ok": True,
        "file": file_name,
        "pages": page_count,
        "total_chars": total_chars,
        "text": full_text,
        "truncated": total_chars > _MAX_TEXT_CHARS,
        "pages_detail": pages,
    }


async def extract_text(file_path: str) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        return {"ok": False, "error": "Arquivo não encontrado."}
    if path.suffix.lower() != ".pdf":
        return {"ok": False, "error": "O arquivo não é um PDF."}
    try:
        if path.stat().st_size > _MAX_PDF_BYTES:
            return {"ok": False, "error": "O PDF excede o limite de 10 MB."}
    except OSError as exc:
        return {"ok": False, "error": f"Não foi possível ler o PDF: {exc}"}
    try:
        import fitz

        def _extract() -> dict[str, Any]:
            with fitz.open(str(path)) as doc:
                return _extract_document(doc, path.name)

        return await asyncio.to_thread(_extract)
    except ImportError:
        return {"ok": False, "error": "PyMuPDF not installed. Run: pip install PyMuPDF"}
    except Exception as exc:
        return {"ok": False, "error": f"Erro ao processar PDF: {exc}"}


async def extract_text_bytes(data_base64: str, file_name: str = "documento.pdf") -> dict[str, Any]:
    """Extract text from a renderer upload without trusting an arbitrary path."""
    encoded = str(data_base64 or "").split(",", 1)[-1].strip()
    safe_name = Path(str(file_name or "documento.pdf")).name[:240] or "documento.pdf"
    if Path(safe_name).suffix.lower() != ".pdf":
        return {"ok": False, "error": "O arquivo não é um PDF."}
    if not encoded or len(encoded) > _MAX_PDF_BASE64_CHARS:
        return {"ok": False, "error": "O PDF está vazio ou excede o limite de 10 MB."}
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return {"ok": False, "error": "Conteúdo PDF base64 inválido."}
    if len(raw) > _MAX_PDF_BYTES:
        return {"ok": False, "error": "O PDF excede o limite de 10 MB."}
    if not raw.startswith(b"%PDF-"):
        return {"ok": False, "error": "O conteúdo enviado não possui assinatura de PDF."}

    try:
        import fitz

        def _extract() -> dict[str, Any]:
            with fitz.open(stream=raw, filetype="pdf") as doc:
                return _extract_document(doc, safe_name)

        return await asyncio.to_thread(_extract)
    except ImportError:
        return {"ok": False, "error": "PyMuPDF não está instalado."}
    except Exception as exc:
        return {"ok": False, "error": f"Erro ao processar PDF: {exc}"}


async def extract_tables(file_path: str) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        return {"ok": False, "error": "Arquivo não encontrado."}
    try:
        import fitz
        import json
        def _extract() -> dict[str, Any]:
            doc = fitz.open(str(path))
            tables: list[dict[str, Any]] = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                tabs = page.find_tables()
                for t in tabs:
                    tables.append({
                        "page": page_num + 1,
                        "rows": len(t.extract()),
                        "data": t.extract(),
                    })
            doc.close()
            return {
                "ok": True,
                "file": path.name,
                "tables_found": len(tables),
                "tables": tables,
            }
        return await asyncio.to_thread(_extract)
    except ImportError:
        return {"ok": False, "error": "PyMuPDF not installed."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def extract_images(file_path: str) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        return {"ok": False, "error": "Arquivo não encontrado."}
    try:
        import fitz
        import base64
        import io
        def _extract() -> dict[str, Any]:
            doc = fitz.open(str(path))
            images: list[dict[str, Any]] = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                for img_index, img in enumerate(page.get_images(full=True)):
                    xref = img[0]
                    base = doc.extract_image(xref)
                    img_bytes = base["image"]
                    img_b64 = base64.b64encode(img_bytes).decode()
                    images.append({
                        "page": page_num + 1,
                        "index": img_index,
                        "width": base.get("width", 0),
                        "height": base.get("height", 0),
                        "ext": base.get("ext", "png"),
                        "size": len(img_bytes),
                        "base64": img_b64[:200] + f"... ({len(img_bytes)} bytes)",
                    })
            doc.close()
            return {
                "ok": True,
                "file": path.name,
                "images_found": len(images),
                "images": images,
            }
        return await asyncio.to_thread(_extract)
    except ImportError:
        return {"ok": False, "error": "PyMuPDF not installed."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
