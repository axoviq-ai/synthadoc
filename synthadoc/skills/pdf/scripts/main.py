# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
import logging

import pypdf

from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

logger = logging.getLogger(__name__)

# pypdf logs benign structural warnings (e.g. incorrect startxref pointer) at WARNING
# level for many real-world PDFs. Suppress them so they don't pollute the console.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# If pypdf extracts fewer than this many characters per page on average,
# the PDF likely uses CJK fonts whose ToUnicode CMaps pypdf cannot decode.
# In that case we fall back to pdfminer.six which has better CJK support.
_MIN_CHARS_PER_PAGE = 50


def _build_pagemap(page_texts: list[str]) -> dict[int, int]:
    """Return {first_line_of_page: pdf_page_number} for each non-empty page.

    Line numbers are 1-based and reference the concatenated extracted text.
    Empty pages are skipped and do not advance the line counter.
    """
    pagemap: dict[int, int] = {}
    current_line = 1
    for page_num, text in enumerate(page_texts, start=1):
        if text:
            pagemap[current_line] = page_num
            current_line += text.count("\n") + 1
    return pagemap


class PdfSkill(BaseSkill):
    meta = SkillMeta(name="pdf", description="Extract text from PDF files", extensions=[".pdf"])

    async def extract(self, source: str) -> ExtractedContent:
        # pypdf and pdfminer are synchronous CPU-bound libraries; run them in a
        # thread pool so they do not block the asyncio event loop and starve
        # other coroutines (e.g. HTTP handlers, jobs list) while processing
        # large PDFs.
        text, num_pages, pagemap = await asyncio.to_thread(self._extract_pypdf, source)

        # Low yield → likely CJK fonts that pypdf cannot decode; try pdfminer fallback
        if num_pages > 0 and len(text.strip()) < num_pages * _MIN_CHARS_PER_PAGE:
            logger.debug(
                "pypdf yielded %d chars for %d page(s) in %s — trying pdfminer fallback",
                len(text.strip()), num_pages, source,
            )
            fallback = await asyncio.to_thread(self._extract_pdfminer, source)
            if len(fallback.strip()) > len(text.strip()):
                text = fallback
                pagemap = {1: 1}  # pdfminer has no page-level info

        return ExtractedContent(text=text, source_path=source,
                                metadata={"pages": num_pages, "page_boundaries": pagemap})

    def _extract_pypdf(self, source: str) -> tuple[str, int, dict[int, int]]:
        try:
            parts = []
            page_texts: list[str] = []
            with open(source, "rb") as f:
                reader = pypdf.PdfReader(f)
                num_pages = len(reader.pages)
                for page in reader.pages:
                    t = page.extract_text()
                    page_texts.append(t or "")
                    if t:
                        parts.append(t)
            pagemap = _build_pagemap(page_texts)
            return "\n".join(parts), num_pages, pagemap
        except (FileNotFoundError, IsADirectoryError):
            raise
        except Exception as exc:
            raise ValueError(
                f"Cannot read '{source}' as a PDF file: {exc}. "
                "Ensure the file is a valid PDF document."
            ) from exc

    def _extract_pdfminer(self, source: str) -> str:
        try:
            from pdfminer.high_level import extract_text
            return extract_text(source) or ""
        except Exception as exc:
            logger.debug("pdfminer fallback failed for %s: %s", source, exc)
            return ""
