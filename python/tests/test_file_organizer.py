"""Tests for the file organizer module."""
import asyncio
import tempfile
from pathlib import Path

from jarvis.file_organizer import (
    categorize_file,
    organize_folder,
    clean_temp_files,
    undo_last_organization,
)


def test_categorize_file():
    assert categorize_file("documento.pdf") == "Documentos"
    assert categorize_file("foto.jpg") == "Imagens"
    assert categorize_file("video.mp4") == "Vídeos"
    assert categorize_file("musica.mp3") == "Música"
    assert categorize_file("code.py") == "Código"
    assert categorize_file("archive.zip") == "Arquivos"
    assert categorize_file("program.exe") == "Executáveis"
    assert categorize_file("font.ttf") == "Fontes"
    assert categorize_file("unknown.xyz") is None
    assert categorize_file("noext") is None


def test_categorize_special_extensions():
    assert categorize_file("doc.docx") == "Documentos"
    assert categorize_file("sheet.xlsx") == "Planilhas"
    assert categorize_file("text.txt") == "Textos"
    assert categorize_file("subtitle.srt") == "Legendas"
    assert categorize_file("model.stl") == "3D"


def test_organize_dry_run():
    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc.pdf").write_text("pdf content")
            (root / "image.jpg").write_text("image content")
            (root / "script.py").write_text("print('hello')")

            result = await organize_folder(str(root), by_type=True, dry_run=True)
            assert result["ok"] is True
            assert result["dry_run"] is True
            assert result["stats"]["total"] == 3
            assert result["stats"]["organized"] == 3
            assert len(result["moves"]) == 3
            assert (root / "doc.pdf").exists()
            assert (root / "image.jpg").exists()
            assert (root / "script.py").exists()
    asyncio.run(_run())


def test_organize_execute():
    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc.pdf").write_text("pdf content")
            (root / "image.jpg").write_text("image content")

            result = await organize_folder(str(root), by_type=True, dry_run=False)
            assert result["ok"] is True
            assert result["dry_run"] is False
            assert result["stats"]["executed"] == 2

            assert (root / "Documentos" / "doc.pdf").exists()
            assert (root / "Imagens" / "image.jpg").exists()
            assert not (root / "doc.pdf").exists()
            assert not (root / "image.jpg").exists()
    asyncio.run(_run())


def test_organize_undo():
    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc.pdf").write_text("pdf content")

            result = await organize_folder(str(root), by_type=True, dry_run=False)
            assert result["ok"] is True
            assert (root / "Documentos" / "doc.pdf").exists()

            undo = await undo_last_organization(str(root))
            assert undo["ok"] is True
            assert undo["restored"] == 1
            assert (root / "doc.pdf").exists()
            assert not (root / "Documentos" / "doc.pdf").exists()
    asyncio.run(_run())


def test_clean_temp_files():
    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "temp.tmp"
            f.write_text("temp content")

            result = await clean_temp_files(str(root), days_old=0, dry_run=True)
            assert result["ok"] is True
            assert result["total_files"] >= 1
            assert result["dry_run"] is True
            assert f.exists()

            result = await clean_temp_files(str(root), days_old=0, dry_run=False)
            assert result["ok"] is True
            assert not f.exists()
    asyncio.run(_run())
