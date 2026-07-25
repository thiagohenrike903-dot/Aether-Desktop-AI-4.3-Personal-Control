"""Projects and a bounded local document library with source citations."""
from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import html
import importlib.util
import io
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
import zipfile
from array import array
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .config import settings
from . import workspace

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "projects.sqlite3"
_SEMANTIC_MODEL: Any = None
_SEMANTIC_MODEL_ID: str | None = None
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_BASE64_CHARS = MAX_DOCUMENT_BYTES * 4 // 3 + 512
MAX_DOCUMENT_TEXT = 1_000_000
MAX_FOLDER_FILES = 100
MAX_FOLDER_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5_000
MAX_ARCHIVE_MEMBER_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_XML_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 200
CHUNK_CHARS = 1_800
CHUNK_OVERLAP = 200

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".csv",
    ".tsv",
    ".txt",
    ".md",
    ".rst",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".yaml",
    ".yml",
    ".toml",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    instructions  TEXT NOT NULL DEFAULT '',
    root_path     TEXT,
    archived      INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS project_documents (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    name          TEXT NOT NULL,
    source_type   TEXT NOT NULL,
    source_uri    TEXT,
    mime_type     TEXT NOT NULL,
    text          TEXT NOT NULL,
    status        TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_project_documents_project
ON project_documents(project_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS document_chunks (
    id            TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL,
    project_id    TEXT NOT NULL,
    chunk_index   INTEGER NOT NULL,
    text          TEXT NOT NULL,
    location_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_document_chunks_project
ON document_chunks(project_id, document_id, chunk_index);
CREATE TABLE IF NOT EXISTS document_versions (
    id                 TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL,
    document_id        TEXT NOT NULL,
    content_hash       TEXT NOT NULL,
    version_group      TEXT NOT NULL,
    version_number     INTEGER NOT NULL,
    duplicate_of       TEXT,
    source_modified_ns INTEGER,
    source_size        INTEGER,
    indexed_at         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_document_versions_hash
ON document_versions(project_id, content_hash);
CREATE INDEX IF NOT EXISTS ix_document_versions_group
ON document_versions(project_id, version_group, version_number DESC);
CREATE TABLE IF NOT EXISTS library_index_state (
    project_id          TEXT PRIMARY KEY,
    semantic_enabled    INTEGER NOT NULL DEFAULT 0,
    semantic_model_id   TEXT,
    last_indexed_at     REAL,
    updated_at          REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS document_embeddings (
    chunk_id            TEXT PRIMARY KEY,
    document_id         TEXT NOT NULL,
    project_id          TEXT NOT NULL,
    model_id            TEXT NOT NULL,
    dimensions          INTEGER NOT NULL,
    vector_blob         BLOB NOT NULL,
    updated_at          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_document_embeddings_project
ON document_embeddings(project_id, document_id);
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _version_group(name: str, source_uri: str | None) -> str:
    source = str(source_uri or "").strip()
    if source:
        return hashlib.sha256(source.casefold().encode("utf-8")).hexdigest()
    normalized = re.sub(r"\s+", " ", Path(str(name or "")).name.casefold()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as connection:
        connection.executescript(_SCHEMA)
        # Existing 4.2 documents did not have explicit version rows.  A hash of
        # the extracted text preserves useful duplicate/version semantics
        # without requiring access to the original file during migration.
        legacy = connection.execute(
            """
            SELECT d.id, d.project_id, d.name, d.source_uri, d.text,
                   d.metadata_json, d.updated_at
            FROM project_documents d
            LEFT JOIN document_versions v ON v.document_id = d.id
            WHERE v.document_id IS NULL
            """
        ).fetchall()
        for row in legacy:
            metadata = json.loads(row["metadata_json"] or "{}")
            digest = str(
                metadata.get("content_hash")
                or hashlib.sha256(str(row["text"]).encode("utf-8")).hexdigest()
            )
            group = _version_group(row["name"], row["source_uri"])
            version = connection.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1
                FROM document_versions
                WHERE project_id = ? AND version_group = ?
                """,
                (row["project_id"], group),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO document_versions (
                    id, project_id, document_id, content_hash, version_group,
                    version_number, duplicate_of, source_modified_ns,
                    source_size, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    row["project_id"],
                    row["id"],
                    digest,
                    group,
                    version,
                    metadata.get("source_modified_ns"),
                    metadata.get("source_size"),
                    row["updated_at"],
                ),
            )
        connection.commit()


_init_db()


def _public_project(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "instructions": row["instructions"],
        "root_path": row["root_path"],
        "archived": bool(row["archived"]),
        "document_count": row["document_count"] if "document_count" in row.keys() else 0,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_projects(
    *,
    archived: bool | None = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    where = "" if archived is None else "WHERE p.archived = ?"
    values: list[Any] = [] if archived is None else [int(archived)]
    values.append(max(1, min(int(limit), 1_000)))
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT p.*, COUNT(d.id) AS document_count
            FROM projects p
            LEFT JOIN project_documents d ON d.project_id = p.id
            {where}
            GROUP BY p.id
            ORDER BY p.updated_at DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
    return [_public_project(row) for row in rows]


def get_project(project_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT p.*, COUNT(d.id) AS document_count
            FROM projects p
            LEFT JOIN project_documents d ON d.project_id = p.id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (project_id,),
        ).fetchone()
    return _public_project(row) if row else None


def _validate_project_root(root_path: str) -> str:
    selected_workspace = workspace.get_root()
    if selected_workspace is None:
        raise ValueError(
            "Selecione um workspace antes de associar uma pasta ao projeto."
        )
    workspace_root = Path(selected_workspace).expanduser().resolve()
    candidate = Path(root_path).expanduser().resolve()
    if not candidate.is_dir():
        raise ValueError("A pasta raiz do projeto não existe.")
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError(
            "A pasta raiz do projeto precisa estar dentro do workspace selecionado."
        ) from exc
    return str(candidate)


def create_project(
    name: str,
    *,
    description: str = "",
    instructions: str = "",
    root_path: str | None = None,
) -> dict[str, Any]:
    name = str(name or "").strip()
    if not name:
        raise ValueError("O nome do projeto é obrigatório.")
    resolved_root: str | None = None
    if root_path:
        resolved_root = _validate_project_root(root_path)
    project_id = str(uuid.uuid4())
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO projects
                (id, name, description, instructions, root_path, archived, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                project_id,
                name[:240],
                str(description or "")[:20_000],
                str(instructions or "")[:50_000],
                resolved_root,
                now,
                now,
            ),
        )
        connection.commit()
    item = get_project(project_id)
    assert item is not None
    return item


def update_project(project_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    current = get_project(project_id)
    if current is None:
        raise KeyError(project_id)
    allowed = {"name", "description", "instructions", "root_path", "archived"}
    clean = {key: value for key, value in changes.items() if key in allowed}
    if "name" in clean:
        clean["name"] = str(clean["name"] or "").strip()[:240]
        if not clean["name"]:
            raise ValueError("O nome do projeto é obrigatório.")
    for field, limit in (("description", 20_000), ("instructions", 50_000)):
        if field in clean:
            clean[field] = str(clean[field] or "")[:limit]
    if "root_path" in clean:
        if clean["root_path"]:
            clean["root_path"] = _validate_project_root(str(clean["root_path"]))
        else:
            clean["root_path"] = None
    if "archived" in clean:
        clean["archived"] = int(bool(clean["archived"]))
    if clean:
        assignments = ", ".join(f"{field} = ?" for field in clean)
        with _LOCK, _connect() as connection:
            connection.execute(
                f"UPDATE projects SET {assignments}, updated_at = ? WHERE id = ?",
                [*clean.values(), time.time(), project_id],
            )
            connection.commit()
    item = get_project(project_id)
    assert item is not None
    return item


def delete_project(project_id: str) -> bool:
    if get_project(project_id) is None:
        return False
    with _LOCK, _connect() as connection:
        document_ids = [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM project_documents WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        ]
        for document_id in document_ids:
            connection.execute(
                "DELETE FROM document_chunks WHERE document_id = ?",
                (document_id,),
            )
        connection.execute(
            "DELETE FROM project_documents WHERE project_id = ?",
            (project_id,),
        )
        result = connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        connection.commit()
    return result.rowcount > 0


def capabilities() -> dict[str, Any]:
    try:
        import fitz  # noqa: F401
        pdf_available = True
    except ImportError:
        pdf_available = False
    try:
        import pytesseract  # noqa: F401
        ocr_import = True
    except ImportError:
        ocr_import = False
    semantic = semantic_capability()
    return {
        "formats": sorted(SUPPORTED_EXTENSIONS),
        "pdf": {"available": pdf_available},
        "ocr": {
            "available": bool(ocr_import and shutil.which("tesseract")),
            "engine": "tesseract" if ocr_import and shutil.which("tesseract") else None,
        },
        "docx": {"available": True, "engine": "stdlib_zip"},
        "xlsx": {"available": True, "engine": "stdlib_zip"},
        "xls": {
            "available": False,
            "reason": "O formato binário .xls exige uma dependência opcional.",
        },
        "folders": {
            "available": True,
            "max_files": MAX_FOLDER_FILES,
            "max_bytes": MAX_FOLDER_BYTES,
            "workspace_scoped": True,
        },
        "semantic_index": semantic,
        "limits": {
            "document_bytes": MAX_DOCUMENT_BYTES,
            "document_text_chars": MAX_DOCUMENT_TEXT,
            "base64_chars": MAX_BASE64_CHARS,
            "archive_entries": MAX_ARCHIVE_ENTRIES,
            "archive_member_bytes": MAX_ARCHIVE_MEMBER_BYTES,
            "archive_total_bytes": MAX_ARCHIVE_TOTAL_BYTES,
            "archive_xml_bytes": MAX_ARCHIVE_XML_BYTES,
            "archive_compression_ratio": MAX_ARCHIVE_COMPRESSION_RATIO,
        },
    }


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _strip_markup(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _open_bounded_archive(raw: bytes, label: str) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{label} inválido ou corrompido.") from exc
    try:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ValueError(
                f"{label} excede o limite de {MAX_ARCHIVE_ENTRIES} itens internos."
            )
        total = 0
        for info in entries:
            if info.flag_bits & 0x1:
                raise ValueError(f"{label} contém um item interno criptografado.")
            size = max(0, int(info.file_size))
            compressed = max(0, int(info.compress_size))
            if size > MAX_ARCHIVE_MEMBER_BYTES:
                raise ValueError(f"{label} contém um item interno grande demais.")
            total += size
            if total > MAX_ARCHIVE_TOTAL_BYTES:
                raise ValueError(f"{label} expande além do limite seguro.")
            if size and (
                compressed == 0
                or size / max(1, compressed) > MAX_ARCHIVE_COMPRESSION_RATIO
            ):
                raise ValueError(f"{label} possui uma taxa de compressão insegura.")
    except Exception:
        archive.close()
        raise
    return archive


def _read_archive_xml(
    archive: zipfile.ZipFile,
    name: str,
    remaining_budget: list[int],
    *,
    required: bool = True,
) -> bytes | None:
    try:
        info = archive.getinfo(name)
    except KeyError:
        if required:
            raise
        return None
    if info.file_size > remaining_budget[0]:
        raise ValueError("O conteúdo XML interno excede o limite seguro.")
    with archive.open(info, "r") as stream:
        value = stream.read(info.file_size + 1)
    if len(value) != info.file_size or len(value) > remaining_budget[0]:
        raise ValueError("O conteúdo XML interno excede o tamanho declarado.")
    remaining_budget[0] -= len(value)
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", value, flags=re.IGNORECASE):
        raise ValueError("O documento contém declarações XML não permitidas.")
    return value


def _extract_docx(raw: bytes) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    try:
        with _open_bounded_archive(raw, "DOCX") as archive:
            xml = _read_archive_xml(
                archive,
                "word/document.xml",
                [MAX_ARCHIVE_XML_BYTES],
            )
    except KeyError as exc:
        raise ValueError("DOCX inválido ou corrompido.") from exc
    assert xml is not None
    root = ElementTree.fromstring(xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        value = "".join(
            node.text or ""
            for node in paragraph.iter(f"{namespace}t")
        ).strip()
        if value:
            paragraphs.append(value)
    text = "\n".join(paragraphs)
    return text, [{"text": text, "section": "document"}], {"paragraphs": len(paragraphs)}


def _column_name(number: int) -> str:
    output = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        output = chr(65 + remainder) + output
    return output or "A"


def _extract_xlsx(raw: bytes) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    archive = _open_bounded_archive(raw, "XLSX")
    with archive:
        xml_budget = [MAX_ARCHIVE_XML_BYTES]
        shared: list[str] = []
        shared_xml = _read_archive_xml(
            archive,
            "xl/sharedStrings.xml",
            xml_budget,
            required=False,
        )
        if shared_xml is not None:
            shared_root = ElementTree.fromstring(shared_xml)
            for item in shared_root:
                shared.append("".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")))
        sheet_names = sorted(
            name
            for name in archive.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        )
        sections: list[dict[str, Any]] = []
        all_text: list[str] = []
        for sheet_index, sheet_name in enumerate(sheet_names, start=1):
            sheet_xml = _read_archive_xml(
                archive,
                sheet_name,
                xml_budget,
            )
            assert sheet_xml is not None
            root = ElementTree.fromstring(sheet_xml)
            rows: list[str] = []
            max_columns = 1
            for row in (node for node in root.iter() if node.tag.endswith("}row")):
                values: list[str] = []
                for cell in (node for node in row if node.tag.endswith("}c")):
                    cell_type = cell.attrib.get("t")
                    value_node = next(
                        (node for node in cell if node.tag.endswith("}v")),
                        None,
                    )
                    value = value_node.text if value_node is not None else ""
                    if cell_type == "s" and value:
                        try:
                            value = shared[int(value)]
                        except (ValueError, IndexError):
                            pass
                    values.append(str(value or ""))
                max_columns = max(max_columns, len(values))
                rows.append("\t".join(values))
            text = "\n".join(rows)
            label = f"Planilha {sheet_index}"
            all_text.append(f"--- {label} ---\n{text}")
            sections.append({
                "text": text,
                "sheet": label,
                "cell_range": f"A1:{_column_name(max_columns)}{max(1, len(rows))}",
            })
    return "\n".join(all_text), sections, {"sheets": len(sections)}


def _extract_delimited(
    raw: bytes,
    delimiter: str,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    decoded = _decode_text(raw)
    rows = list(csv.reader(io.StringIO(decoded), delimiter=delimiter))
    rendered = "\n".join("\t".join(row) for row in rows)
    columns = max((len(row) for row in rows), default=1)
    location = {
        "text": rendered,
        "sheet": "Tabela",
        "cell_range": f"A1:{_column_name(columns)}{max(1, len(rows))}",
    }
    return rendered, [location], {"rows": len(rows), "columns": columns}


def _extract_pdf(raw: bytes) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    try:
        import fitz
    except ImportError as exc:
        raise ValueError("PyMuPDF não está instalado; PDF indisponível.") from exc
    ocr_available = False
    pytesseract = None
    if shutil.which("tesseract"):
        try:
            import pytesseract as imported_pytesseract
            from PIL import Image  # noqa: F401
            pytesseract = imported_pytesseract
            ocr_available = True
        except ImportError:
            pass
    sections: list[dict[str, Any]] = []
    ocr_used = False
    with fitz.open(stream=raw, filetype="pdf") as document:
        if len(document) > 500:
            raise ValueError("O PDF excede o limite de 500 páginas.")
        for index, page in enumerate(document):
            text = page.get_text().strip()
            page_ocr = False
            if len(text) < 40 and ocr_available and pytesseract is not None:
                try:
                    from PIL import Image
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    image = Image.frombytes(
                        "RGB",
                        (pixmap.width, pixmap.height),
                        pixmap.samples,
                    )
                    extracted = pytesseract.image_to_string(image).strip()
                    if extracted:
                        text = extracted
                        page_ocr = True
                        ocr_used = True
                except Exception:
                    page_ocr = False
            sections.append({
                "text": text,
                "page": index + 1,
                "ocr": page_ocr,
            })
    full_text = "\n".join(
        f"--- Página {section['page']} ---\n{section['text']}"
        for section in sections
    )
    return full_text, sections, {
        "pages": len(sections),
        "ocr": {"available": ocr_available, "used": ocr_used},
    }


def extract(
    raw: bytes,
    name: str,
    mime_type: str | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("O documento excede o limite de 20 MB.")
    extension = Path(name).suffix.lower()
    if extension == ".pdf" or mime_type == "application/pdf":
        result = _extract_pdf(raw)
    elif extension == ".docx":
        result = _extract_docx(raw)
    elif extension == ".xlsx":
        result = _extract_xlsx(raw)
    elif extension == ".csv":
        result = _extract_delimited(raw, ",")
    elif extension == ".tsv":
        result = _extract_delimited(raw, "\t")
    elif extension in {".html", ".htm"}:
        text = _strip_markup(_decode_text(raw))
        result = (text, [{"text": text, "section": "page"}], {})
    elif extension in SUPPORTED_EXTENSIONS or str(mime_type or "").startswith("text/"):
        text = _decode_text(raw)
        result = (text, [{"text": text, "section": "document"}], {})
    else:
        raise ValueError(f"Formato não suportado: {extension or mime_type or 'desconhecido'}.")
    text, sections, metadata = result
    if len(text) > MAX_DOCUMENT_TEXT:
        text = text[:MAX_DOCUMENT_TEXT]
        metadata["text_truncated"] = True
        remaining = MAX_DOCUMENT_TEXT
        bounded: list[dict[str, Any]] = []
        for section in sections:
            if remaining <= 0:
                break
            copy = dict(section)
            copy["text"] = str(copy.get("text") or "")[:remaining]
            remaining -= len(copy["text"])
            bounded.append(copy)
        sections = bounded
    else:
        metadata["text_truncated"] = False
    return text, sections, metadata


def _chunks(sections: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    output: list[tuple[str, dict[str, Any]]] = []
    for section in sections:
        text = str(section.get("text") or "").strip()
        location = {key: value for key, value in section.items() if key != "text"}
        start = 0
        while start < len(text):
            end = min(len(text), start + CHUNK_CHARS)
            if end < len(text):
                split = text.rfind("\n", start, end)
                if split > start + CHUNK_CHARS // 2:
                    end = split
            chunk = text[start:end].strip()
            if chunk:
                output.append((chunk, location))
            if end >= len(text):
                break
            start = max(start + 1, end - CHUNK_OVERLAP)
    return output


def import_bytes(
    project_id: str,
    *,
    raw: bytes,
    name: str,
    mime_type: str | None = None,
    source_type: str = "upload",
    source_uri: str | None = None,
    source_modified_ns: int | None = None,
    source_size: int | None = None,
) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise KeyError(project_id)
    safe_name = Path(str(name or "documento")).name[:240] or "documento"
    actual_mime = (
        str(mime_type or "").strip()
        or mimetypes.guess_type(safe_name)[0]
        or "application/octet-stream"
    )
    content_hash = hashlib.sha256(raw).hexdigest()
    group = _version_group(safe_name, source_uri)
    with _LOCK, _connect() as connection:
        duplicate = connection.execute(
            """
            SELECT v.document_id
            FROM document_versions v
            JOIN project_documents d ON d.id = v.document_id
            WHERE v.project_id = ? AND v.content_hash = ?
            ORDER BY d.updated_at DESC
            LIMIT 1
            """,
            (project_id, content_hash),
        ).fetchone()
    if duplicate is not None:
        existing = get_document(
            project_id,
            str(duplicate["document_id"]),
            include_text=False,
        )
        if existing is not None:
            existing["duplicate"] = True
            existing["duplicate_of"] = existing["id"]
            return existing
    text, sections, metadata = extract(raw, safe_name, actual_mime)
    document_id = str(uuid.uuid4())
    now = time.time()
    chunks = _chunks(sections)
    status = "ready" if text.strip() else "empty"
    metadata = {
        **metadata,
        "bytes": len(raw),
        "chunks": len(chunks),
        "content_hash": content_hash,
        "source_modified_ns": source_modified_ns,
        "source_size": source_size if source_size is not None else len(raw),
    }
    with _LOCK, _connect() as connection:
        version_number = int(connection.execute(
            """
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM document_versions
            WHERE project_id = ? AND version_group = ?
            """,
            (project_id, group),
        ).fetchone()[0])
        metadata["version_group"] = group
        metadata["version_number"] = version_number
        connection.execute(
            """
            INSERT INTO project_documents (
                id, project_id, name, source_type, source_uri, mime_type,
                text, status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                project_id,
                safe_name,
                source_type,
                source_uri,
                actual_mime,
                text,
                status,
                json.dumps(metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        for chunk_index, (chunk_text, location) in enumerate(chunks):
            connection.execute(
                """
                INSERT INTO document_chunks
                    (id, document_id, project_id, chunk_index, text, location_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    document_id,
                    project_id,
                    chunk_index,
                    chunk_text,
                    json.dumps(location, ensure_ascii=False),
                ),
            )
        connection.execute(
            """
            INSERT INTO document_versions (
                id, project_id, document_id, content_hash, version_group,
                version_number, duplicate_of, source_modified_ns,
                source_size, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                project_id,
                document_id,
                content_hash,
                group,
                version_number,
                source_modified_ns,
                source_size if source_size is not None else len(raw),
                now,
            ),
        )
        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        connection.commit()
    item = get_document(project_id, document_id, include_text=False)
    assert item is not None
    if _semantic_enabled(project_id):
        try:
            _build_embeddings(project_id, document_id=document_id)
        except (ImportError, OSError, ValueError):
            # The lexical index remains valid. Status exposes the local model
            # failure instead of failing a successful document import.
            pass
    return item


def import_base64(
    project_id: str,
    *,
    data_base64: str,
    name: str,
    mime_type: str | None = None,
) -> dict[str, Any]:
    encoded = str(data_base64 or "").split(",", 1)[-1].strip()
    if not encoded or len(encoded) > (MAX_DOCUMENT_BYTES * 4 // 3 + 16):
        raise ValueError("Conteúdo vazio ou acima do limite.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Conteúdo base64 inválido.") from exc
    return import_bytes(
        project_id,
        raw=raw,
        name=name,
        mime_type=mime_type,
        source_type="upload",
    )


def import_path(project_id: str, path_value: str, *, name: str | None = None) -> dict[str, Any]:
    source_path = Path(path_value).expanduser()
    if source_path.is_symlink():
        raise ValueError("Links simbólicos não podem ser importados ou indexados.")
    path = source_path.resolve()
    if not path.is_file():
        raise ValueError("O arquivo não existe.")
    project = get_project(project_id)
    if project is None:
        raise KeyError(project_id)
    workspace_root = workspace.get_root()
    allowed_roots: list[Path] = []
    if workspace_root is not None:
        allowed_workspace = Path(workspace_root).resolve()
        allowed_roots.append(allowed_workspace)
        if project.get("root_path"):
            candidate_root = Path(str(project["root_path"])).resolve()
            try:
                candidate_root.relative_to(allowed_workspace)
            except ValueError:
                # Ignore roots created by older, less restrictive versions.
                pass
            else:
                allowed_roots.append(candidate_root)
    if not any(
        path == root or root in path.parents
        for root in allowed_roots
    ):
        raise ValueError(
            "O caminho precisa estar na pasta do projeto ou no workspace; "
            "use data_base64 para um arquivo escolhido fora deles."
        )
    if workspace._is_sensitive(path):
        raise ValueError("Arquivos sensíveis não podem ser importados ou indexados.")
    source_stat = path.stat()
    if source_stat.st_size > MAX_DOCUMENT_BYTES:
        raise ValueError("O documento excede o limite de 20 MB.")
    with path.open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("O documento excede o limite de 20 MB.")
    return import_bytes(
        project_id,
        raw=raw,
        name=name or path.name,
        source_type="file",
        source_uri=str(path),
        source_modified_ns=source_stat.st_mtime_ns,
        source_size=source_stat.st_size,
    )


def import_page_text(
    project_id: str,
    *,
    url: str,
    title: str,
    text: str,
) -> dict[str, Any]:
    body = str(text or "").encode("utf-8")
    return import_bytes(
        project_id,
        raw=body,
        name=(title.strip()[:220] or "Página") + ".html",
        mime_type="text/html",
        source_type="page",
        source_uri=url,
    )


def _validate_workspace_folder(folder: str) -> Path:
    root = workspace.get_root()
    if root is None:
        raise ValueError("Selecione um workspace antes de importar uma pasta.")
    candidate = Path(folder).expanduser().resolve()
    if not candidate.is_dir():
        raise ValueError("A pasta não existe.")
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("A pasta importada precisa estar dentro do workspace.") from exc
    return candidate


def import_folder(project_id: str, folder: str) -> dict[str, Any]:
    root = _validate_workspace_folder(folder)
    imported: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    total_bytes = 0
    examined = 0
    truncated = False
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in workspace.IGNORED_NAMES for part in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        if workspace._is_sensitive(path):
            examined += 1
            blocked.append({
                "path": relative,
                "reason": "Arquivo sensível bloqueado; o conteúdo não foi indexado.",
            })
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        examined += 1
        try:
            size = path.stat().st_size
        except OSError as exc:
            errors.append({"path": str(path), "error": str(exc)})
            continue
        if len(imported) >= MAX_FOLDER_FILES or total_bytes + size > MAX_FOLDER_BYTES:
            truncated = True
            break
        try:
            imported.append(import_path(project_id, str(path)))
            total_bytes += size
        except (OSError, ValueError) as exc:
            errors.append({
                "path": relative,
                "error": str(exc),
            })
    return {
        "ok": bool(imported) or not errors,
        "folder": str(root),
        "imported": imported,
        "imported_count": len(imported),
        "errors": errors,
        "blocked": blocked,
        "blocked_count": len(blocked),
        "examined": examined,
        "total_bytes": total_bytes,
        "truncated": truncated,
        "limits": {
            "max_files": MAX_FOLDER_FILES,
            "max_bytes": MAX_FOLDER_BYTES,
        },
    }


def _public_document(row: sqlite3.Row, *, include_text: bool = False) -> dict[str, Any]:
    item = {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "source_type": row["source_type"],
        "source_uri": row["source_uri"],
        "mime_type": row["mime_type"],
        "status": row["status"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_text:
        item["text"] = row["text"]
    return item


def list_documents(project_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
    if get_project(project_id) is None:
        raise KeyError(project_id)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM project_documents
            WHERE project_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (project_id, max(1, min(int(limit), 2_000))),
        ).fetchall()
    return [_public_document(row) for row in rows]


def get_document(
    project_id: str,
    document_id: str,
    *,
    include_text: bool = True,
) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM project_documents
            WHERE project_id = ? AND id = ?
            """,
            (project_id, document_id),
        ).fetchone()
    return _public_document(row, include_text=include_text) if row else None


def delete_document(project_id: str, document_id: str) -> bool:
    with _LOCK, _connect() as connection:
        connection.execute(
            "DELETE FROM document_embeddings WHERE project_id = ? AND document_id = ?",
            (project_id, document_id),
        )
        connection.execute(
            "DELETE FROM document_chunks WHERE project_id = ? AND document_id = ?",
            (project_id, document_id),
        )
        connection.execute(
            "DELETE FROM document_versions WHERE project_id = ? AND document_id = ?",
            (project_id, document_id),
        )
        result = connection.execute(
            "DELETE FROM project_documents WHERE project_id = ? AND id = ?",
            (project_id, document_id),
        )
        connection.commit()
    return result.rowcount > 0


def semantic_capability() -> dict[str, Any]:
    model_value = str(os.getenv("AETHER_LOCAL_EMBEDDING_MODEL") or "").strip()
    model_path: Path | None = None
    if model_value:
        try:
            candidate = Path(model_value).expanduser().resolve()
            if candidate.exists():
                model_path = candidate
        except OSError:
            model_path = None
    dependencies = bool(
        importlib.util.find_spec("sentence_transformers")
        and importlib.util.find_spec("numpy")
    )
    available = bool(dependencies and model_path)
    return {
        "available": available,
        "entirely_local": True,
        "downloads_models": False,
        "dependencies_available": dependencies,
        "model_configured": model_path is not None,
        "model_id": (
            hashlib.sha256(str(model_path).encode("utf-8")).hexdigest()[:16]
            if model_path else None
        ),
        "reason": (
            None
            if available
            else (
                "Configure AETHER_LOCAL_EMBEDDING_MODEL com uma pasta local."
                if dependencies
                else "Instale as dependências opcionais do índice semântico."
            )
        ),
    }


def _load_semantic_model() -> tuple[Any, str]:
    global _SEMANTIC_MODEL, _SEMANTIC_MODEL_ID
    capability = semantic_capability()
    if not capability["available"]:
        raise ValueError(str(capability["reason"]))
    model_path = Path(
        str(os.environ["AETHER_LOCAL_EMBEDDING_MODEL"])
    ).expanduser().resolve()
    model_id = str(capability["model_id"])
    if _SEMANTIC_MODEL is not None and _SEMANTIC_MODEL_ID == model_id:
        return _SEMANTIC_MODEL, model_id
    from sentence_transformers import SentenceTransformer

    try:
        model = SentenceTransformer(str(model_path), local_files_only=True)
    except TypeError:
        # Older releases do not accept local_files_only, but a resolved local
        # filesystem path cannot be interpreted as a remote model identifier.
        model = SentenceTransformer(str(model_path))
    _SEMANTIC_MODEL = model
    _SEMANTIC_MODEL_ID = model_id
    return model, model_id


def _semantic_enabled(project_id: str) -> bool:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT semantic_enabled FROM library_index_state
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
    return bool(row and row["semantic_enabled"])


def _build_embeddings(
    project_id: str,
    *,
    document_id: str | None = None,
) -> dict[str, Any]:
    model, model_id = _load_semantic_model()
    clauses = ["project_id = ?"]
    values: list[Any] = [project_id]
    if document_id:
        clauses.append("document_id = ?")
        values.append(document_id)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id, document_id, text
            FROM document_chunks
            WHERE {' AND '.join(clauses)}
            ORDER BY document_id, chunk_index
            LIMIT 10000
            """,
            values,
        ).fetchall()
    texts = [str(row["text"]) for row in rows]
    vectors = (
        model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        if texts else []
    )
    now = time.time()
    with _LOCK, _connect() as connection:
        if document_id:
            connection.execute(
                "DELETE FROM document_embeddings WHERE project_id = ? AND document_id = ?",
                (project_id, document_id),
            )
        else:
            connection.execute(
                "DELETE FROM document_embeddings WHERE project_id = ?",
                (project_id,),
            )
        for row, vector in zip(rows, vectors):
            values_array = array("f", (float(item) for item in vector))
            connection.execute(
                """
                INSERT INTO document_embeddings (
                    chunk_id, document_id, project_id, model_id,
                    dimensions, vector_blob, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["document_id"],
                    project_id,
                    model_id,
                    len(values_array),
                    values_array.tobytes(),
                    now,
                ),
            )
        connection.execute(
            """
            INSERT INTO library_index_state (
                project_id, semantic_enabled, semantic_model_id,
                last_indexed_at, updated_at
            ) VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                semantic_enabled = 1,
                semantic_model_id = excluded.semantic_model_id,
                last_indexed_at = excluded.last_indexed_at,
                updated_at = excluded.updated_at
            """,
            (project_id, model_id, now, now),
        )
        connection.commit()
    return {
        "ok": True,
        "project_id": project_id,
        "document_id": document_id,
        "chunks_indexed": len(rows),
        "model_id": model_id,
        "entirely_local": True,
    }


def set_semantic_index(project_id: str, enabled: bool) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise KeyError(project_id)
    if enabled:
        return _build_embeddings(project_id)
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO library_index_state (
                project_id, semantic_enabled, semantic_model_id,
                last_indexed_at, updated_at
            ) VALUES (?, 0, NULL, NULL, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                semantic_enabled = 0, updated_at = excluded.updated_at
            """,
            (project_id, now),
        )
        connection.commit()
    return {
        "ok": True,
        "project_id": project_id,
        "enabled": False,
        "entirely_local": True,
    }


def _semantic_scores(project_id: str, query: str) -> dict[str, float]:
    if not _semantic_enabled(project_id):
        return {}
    model, model_id = _load_semantic_model()
    query_vector = array(
        "f",
        (
            float(item)
            for item in model.encode(
                [query],
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0]
        ),
    )
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT chunk_id, dimensions, vector_blob
            FROM document_embeddings
            WHERE project_id = ? AND model_id = ?
            """,
            (project_id, model_id),
        ).fetchall()
    output: dict[str, float] = {}
    for row in rows:
        vector = array("f")
        vector.frombytes(row["vector_blob"])
        if len(vector) != len(query_vector) or len(vector) != row["dimensions"]:
            continue
        output[str(row["chunk_id"])] = sum(
            left * right for left, right in zip(query_vector, vector)
        )
    return output


def list_versions(project_id: str, document_id: str | None = None) -> list[dict[str, Any]]:
    if get_project(project_id) is None:
        raise KeyError(project_id)
    clause = "AND v.document_id = ?" if document_id else ""
    values: list[Any] = [project_id]
    if document_id:
        values.append(document_id)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT v.*, d.name
            FROM document_versions v
            LEFT JOIN project_documents d ON d.id = v.document_id
            WHERE v.project_id = ? {clause}
            ORDER BY v.version_group, v.version_number DESC, v.indexed_at DESC
            LIMIT 1000
            """,
            values,
        ).fetchall()
    return [
        {
            "id": row["id"],
            "document_id": row["document_id"],
            "name": row["name"],
            "content_hash": row["content_hash"],
            "version_group": row["version_group"],
            "version_number": row["version_number"],
            "duplicate_of": row["duplicate_of"],
            "source_modified_ns": row["source_modified_ns"],
            "source_size": row["source_size"],
            "indexed_at": row["indexed_at"],
        }
        for row in rows
    ]


def find_duplicates(project_id: str) -> dict[str, Any]:
    versions = list_versions(project_id)
    by_hash: dict[str, list[dict[str, Any]]] = {}
    by_group: dict[str, list[dict[str, Any]]] = {}
    for item in versions:
        by_hash.setdefault(item["content_hash"], []).append(item)
        by_group.setdefault(item["version_group"], []).append(item)
    exact = [
        {"content_hash": digest, "documents": items}
        for digest, items in by_hash.items()
        if len({item["document_id"] for item in items}) > 1
    ]
    version_groups = [
        {
            "version_group": group,
            "versions": sorted(
                items,
                key=lambda item: item["version_number"],
                reverse=True,
            ),
        }
        for group, items in by_group.items()
        if len(items) > 1
    ]
    return {
        "ok": True,
        "project_id": project_id,
        "exact_duplicates": exact,
        "exact_duplicate_groups": len(exact),
        "version_groups": version_groups,
        "version_group_count": len(version_groups),
    }


def index_status(project_id: str) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise KeyError(project_id)
    documents = list_documents(project_id, limit=2_000)
    stale: list[dict[str, Any]] = []
    ready = 0
    for item in documents:
        if item["source_type"] != "file" or not item.get("source_uri"):
            ready += 1
            continue
        path = Path(str(item["source_uri"]))
        metadata = item["metadata"]
        try:
            file_stat = path.stat()
        except OSError:
            stale.append({
                "document_id": item["id"],
                "name": item["name"],
                "reason": "source_missing",
            })
            continue
        if (
            metadata.get("source_modified_ns") != file_stat.st_mtime_ns
            or metadata.get("source_size") != file_stat.st_size
        ):
            stale.append({
                "document_id": item["id"],
                "name": item["name"],
                "reason": "source_changed",
            })
        else:
            ready += 1
    with _LOCK, _connect() as connection:
        state = connection.execute(
            "SELECT * FROM library_index_state WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        chunks = connection.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        embeddings = connection.execute(
            "SELECT COUNT(*) FROM document_embeddings WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
    return {
        "ok": True,
        "project_id": project_id,
        "status": "stale" if stale else "ready",
        "documents": len(documents),
        "ready_documents": ready,
        "stale_documents": stale,
        "chunks": chunks,
        "semantic": {
            **semantic_capability(),
            "enabled": bool(state and state["semantic_enabled"]),
            "model_id": state["semantic_model_id"] if state else None,
            "embeddings": embeddings,
            "last_indexed_at": state["last_indexed_at"] if state else None,
        },
    }


def _reindex_document(project_id: str, document: dict[str, Any]) -> dict[str, Any]:
    if document["source_type"] != "file" or not document.get("source_uri"):
        return {"document_id": document["id"], "state": "skipped_non_file"}
    source_path = Path(str(document["source_uri"])).expanduser()
    if source_path.is_symlink():
        return {"document_id": document["id"], "state": "source_unavailable"}
    path = source_path.resolve()
    if not path.is_file() or workspace._is_sensitive(path):
        return {"document_id": document["id"], "state": "source_unavailable"}
    root = workspace.get_root()
    if root is None:
        return {"document_id": document["id"], "state": "workspace_unavailable"}
    try:
        path.relative_to(Path(root).resolve())
    except ValueError:
        return {"document_id": document["id"], "state": "outside_workspace"}
    file_stat = path.stat()
    metadata = document["metadata"]
    if (
        metadata.get("source_modified_ns") == file_stat.st_mtime_ns
        and metadata.get("source_size") == file_stat.st_size
    ):
        return {"document_id": document["id"], "state": "unchanged"}
    if file_stat.st_size > MAX_DOCUMENT_BYTES:
        return {"document_id": document["id"], "state": "too_large"}
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    text, sections, extracted = extract(raw, document["name"], document["mime_type"])
    chunks = _chunks(sections)
    now = time.time()
    group = _version_group(document["name"], str(path))
    with _LOCK, _connect() as connection:
        duplicate = connection.execute(
            """
            SELECT document_id FROM document_versions
            WHERE project_id = ? AND content_hash = ? AND document_id != ?
            ORDER BY indexed_at DESC LIMIT 1
            """,
            (project_id, digest, document["id"]),
        ).fetchone()
        version = int(connection.execute(
            """
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM document_versions
            WHERE project_id = ? AND version_group = ?
            """,
            (project_id, group),
        ).fetchone()[0])
        next_metadata = {
            **extracted,
            "bytes": len(raw),
            "chunks": len(chunks),
            "content_hash": digest,
            "source_modified_ns": file_stat.st_mtime_ns,
            "source_size": file_stat.st_size,
            "version_group": group,
            "version_number": version,
        }
        connection.execute(
            """
            UPDATE project_documents
            SET text = ?, status = ?, metadata_json = ?, updated_at = ?
            WHERE id = ? AND project_id = ?
            """,
            (
                text,
                "ready" if text.strip() else "empty",
                json.dumps(next_metadata, ensure_ascii=False),
                now,
                document["id"],
                project_id,
            ),
        )
        connection.execute(
            "DELETE FROM document_chunks WHERE document_id = ?",
            (document["id"],),
        )
        connection.execute(
            "DELETE FROM document_embeddings WHERE document_id = ?",
            (document["id"],),
        )
        for index, (chunk_text, location) in enumerate(chunks):
            connection.execute(
                """
                INSERT INTO document_chunks
                    (id, document_id, project_id, chunk_index, text, location_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), document["id"], project_id, index,
                    chunk_text, json.dumps(location, ensure_ascii=False),
                ),
            )
        connection.execute(
            """
            INSERT INTO document_versions (
                id, project_id, document_id, content_hash, version_group,
                version_number, duplicate_of, source_modified_ns,
                source_size, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), project_id, document["id"], digest, group,
                version, duplicate["document_id"] if duplicate else None,
                file_stat.st_mtime_ns, file_stat.st_size, now,
            ),
        )
        connection.commit()
    if _semantic_enabled(project_id):
        _build_embeddings(project_id, document_id=document["id"])
    return {
        "document_id": document["id"],
        "state": "reindexed",
        "version_number": version,
        "duplicate_of": duplicate["document_id"] if duplicate else None,
        "chunks": len(chunks),
    }


def reindex_project(project_id: str) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise KeyError(project_id)
    results = [
        _reindex_document(project_id, document)
        for document in list_documents(project_id, limit=2_000)
    ]
    counts: dict[str, int] = {}
    for item in results:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    return {
        "ok": True,
        "project_id": project_id,
        "results": results,
        "summary": counts,
        "status": index_status(project_id),
    }


_STOP_WORDS = {
    "a", "as", "o", "os", "de", "da", "do", "das", "dos", "e", "em",
    "para", "por", "que", "um", "uma", "the", "and", "of", "to", "in",
}


def _terms(query: str) -> list[str]:
    return [
        token
        for token in re.findall(r"\w{2,}", query.lower(), flags=re.UNICODE)
        if token not in _STOP_WORDS
    ][:30]


def search(project_id: str, query: str, *, limit: int = 8) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise KeyError(project_id)
    query = str(query or "").strip()
    terms = _terms(query)
    if not terms:
        return {
            "ok": True,
            "query": query,
            "answer": None,
            "grounded": False,
            "results": [],
            "citations": [],
        }
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id AS chunk_id, c.document_id, c.chunk_index, c.text,
                c.location_json, d.name, d.source_uri, d.source_type,
                d.metadata_json
            FROM document_chunks c
            JOIN project_documents d ON d.id = c.document_id
            WHERE c.project_id = ?
            """,
            (project_id,),
        ).fetchall()
    try:
        semantic_scores = _semantic_scores(project_id, query)
    except (ImportError, OSError, ValueError):
        semantic_scores = {}
    ranked: list[tuple[float, sqlite3.Row]] = []
    for row in rows:
        lowered = row["text"].lower()
        counts = [lowered.count(term) for term in terms]
        semantic_score = max(0.0, semantic_scores.get(str(row["chunk_id"]), 0.0))
        if not any(counts) and semantic_score < 0.25:
            continue
        coverage = sum(1 for count in counts if count) / len(terms)
        frequency = sum(counts) / max(1, len(lowered.split()))
        lexical_score = coverage * 0.8 + min(frequency * 10, 0.2)
        score = (
            lexical_score * 0.7 + min(semantic_score, 1.0) * 0.3
            if semantic_scores
            else lexical_score
        )
        ranked.append((score, row))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    results: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    for score, row in ranked[:max(1, min(int(limit), 30))]:
        location = json.loads(row["location_json"] or "{}")
        citation = {
            "document_id": row["document_id"],
            "name": row["name"],
            "source_uri": row["source_uri"],
            "href": (
                row["source_uri"]
                or f"/projects/{project_id}/documents/{row['document_id']}"
            ),
            "chunk": row["chunk_index"],
            "quality": "document",
            **location,
        }
        item = {
            "document_id": row["document_id"],
            "name": row["name"],
            "title": f"{row['name']} · trecho {row['chunk_index'] + 1}",
            "excerpt": row["text"][:1_200],
            "text": row["text"][:1_200],
            "quality": "document",
            "score": round(score, 6),
            "search_mode": "hybrid_local" if semantic_scores else "lexical_local",
            "citation": citation,
        }
        results.append(item)
        citations.append(citation)
    return {
        "ok": True,
        "query": query,
        "answer": None,
        "grounded": bool(results),
        "search_mode": "hybrid_local" if semantic_scores else "lexical_local",
        "semantic_enabled": _semantic_enabled(project_id),
        "results": results,
        "citations": citations,
    }
