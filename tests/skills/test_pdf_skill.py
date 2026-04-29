# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import MagicMock, patch


def _make_skill():
    from synthadoc.skills.pdf.scripts.main import PdfSkill
    return PdfSkill()


def _mock_reader(pages_text: list[str]) -> MagicMock:
    """Build a mock PdfReader whose pages return the given text strings."""
    pages = []
    for t in pages_text:
        p = MagicMock()
        p.extract_text.return_value = t
        pages.append(p)
    reader = MagicMock()
    reader.pages = pages
    return reader


# ── _extract_pypdf ────────────────────────────────────────────────────────────

def test_extract_pypdf_single_page_returns_text(tmp_path):
    """Success path: single page with text."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake")
    reader = _mock_reader(["Hello from page one."])
    with patch("synthadoc.skills.pdf.scripts.main.pypdf.PdfReader", return_value=reader):
        text, num_pages = _make_skill()._extract_pypdf(str(pdf_path))
    assert text == "Hello from page one."
    assert num_pages == 1


def test_extract_pypdf_multi_page_joins_with_newline(tmp_path):
    """Multiple pages are joined with newlines."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake")
    reader = _mock_reader(["Page one.", "Page two.", "Page three."])
    with patch("synthadoc.skills.pdf.scripts.main.pypdf.PdfReader", return_value=reader):
        text, num_pages = _make_skill()._extract_pypdf(str(pdf_path))
    assert text == "Page one.\nPage two.\nPage three."
    assert num_pages == 3


def test_extract_pypdf_skips_none_and_empty_pages(tmp_path):
    """Pages returning None or empty string are not included in output."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake")
    reader = _mock_reader(["Real text.", "", "More text."])
    with patch("synthadoc.skills.pdf.scripts.main.pypdf.PdfReader", return_value=reader):
        text, num_pages = _make_skill()._extract_pypdf(str(pdf_path))
    assert text == "Real text.\nMore text."
    assert num_pages == 3


def test_extract_pypdf_file_not_found_reraises(tmp_path):
    """FileNotFoundError is re-raised, not wrapped."""
    with pytest.raises(FileNotFoundError):
        _make_skill()._extract_pypdf(str(tmp_path / "missing.pdf"))


def test_extract_pypdf_corrupt_raises_value_error(tmp_path):
    """A corrupt/unreadable PDF raises ValueError with a descriptive message."""
    pdf_path = tmp_path / "bad.pdf"
    pdf_path.write_bytes(b"not a pdf")
    with patch("synthadoc.skills.pdf.scripts.main.pypdf.PdfReader",
               side_effect=Exception("bad stream")):
        with pytest.raises(ValueError, match="Cannot read"):
            _make_skill()._extract_pypdf(str(pdf_path))


# ── _extract_pdfminer ─────────────────────────────────────────────────────────

def test_extract_pdfminer_returns_text(tmp_path):
    """_extract_pdfminer returns the text from pdfminer.high_level.extract_text."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake")
    with patch("pdfminer.high_level.extract_text", return_value="pdfminer text"):
        result = _make_skill()._extract_pdfminer(str(pdf_path))
    assert result == "pdfminer text"


def test_extract_pdfminer_returns_empty_on_exception(tmp_path):
    """_extract_pdfminer returns '' when pdfminer raises, rather than propagating."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake")
    with patch("pdfminer.high_level.extract_text", side_effect=RuntimeError("broken")):
        result = _make_skill()._extract_pdfminer(str(pdf_path))
    assert result == ""


# ── extract() integration ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_returns_extracted_content_with_pages_metadata(tmp_path):
    """extract() returns ExtractedContent with pages in metadata."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake")
    reader = _mock_reader(["Hello world. " * 10])  # enough chars to skip pdfminer
    with patch("synthadoc.skills.pdf.scripts.main.pypdf.PdfReader", return_value=reader):
        result = await _make_skill().extract(str(pdf_path))
    assert "Hello world." in result.text
    assert result.metadata["pages"] == 1
    assert result.source_path == str(pdf_path)


@pytest.mark.asyncio
async def test_extract_uses_pdfminer_fallback_when_pypdf_yields_low_chars(tmp_path):
    """When pypdf yields < 50 chars/page, pdfminer fallback is tried if it yields more."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake")
    # pypdf yields almost nothing (3 chars for 1 page — below 50 threshold)
    reader = _mock_reader(["abc"])
    with patch("synthadoc.skills.pdf.scripts.main.pypdf.PdfReader", return_value=reader):
        with patch("pdfminer.high_level.extract_text",
                   return_value="Full CJK text from pdfminer. " * 5):
            result = await _make_skill().extract(str(pdf_path))
    assert "pdfminer" in result.text


@pytest.mark.asyncio
async def test_extract_does_not_call_pdfminer_when_pypdf_yields_enough(tmp_path):
    """When pypdf yields >= 50 chars/page, pdfminer is not called."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake")
    reader = _mock_reader(["A" * 100])  # 100 chars for 1 page — above threshold
    with patch("synthadoc.skills.pdf.scripts.main.pypdf.PdfReader", return_value=reader):
        with patch("pdfminer.high_level.extract_text") as mock_pdfminer:
            await _make_skill().extract(str(pdf_path))
    mock_pdfminer.assert_not_called()


@pytest.mark.asyncio
async def test_extract_keeps_pypdf_text_when_pdfminer_fallback_is_worse(tmp_path):
    """When pdfminer returns fewer chars than pypdf, pypdf result is kept."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake")
    reader = _mock_reader(["ab"])  # 2 chars — below threshold
    with patch("synthadoc.skills.pdf.scripts.main.pypdf.PdfReader", return_value=reader):
        with patch("pdfminer.high_level.extract_text", return_value="x"):  # even fewer
            result = await _make_skill().extract(str(pdf_path))
    assert result.text == "ab"
