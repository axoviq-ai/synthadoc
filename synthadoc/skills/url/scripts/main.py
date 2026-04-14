# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import tempfile
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta
from synthadoc.errors import DomainBlockedException


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# HTTP status codes that indicate bot/access blocking (not transient errors)
_BLOCKED_STATUSES = {403, 401, 429}


class UrlSkill(BaseSkill):
    meta = SkillMeta(name="url", description="Fetch and extract text from web URLs",
                     extensions=["https://", "http://"])

    async def extract(self, source: str) -> ExtractedContent:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=_HEADERS) as client:
            resp = await client.get(source)
            if resp.status_code in _BLOCKED_STATUSES:
                domain = urlparse(source).hostname or source
                raise DomainBlockedException(
                    domain=domain, url=source, status_code=resp.status_code
                )
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            is_pdf = "application/pdf" in content_type or source.lower().endswith(".pdf")
            if is_pdf:
                return self._extract_pdf_response(resp.content, source)
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return ExtractedContent(text=soup.get_text(separator="\n", strip=True),
                                source_path=source, metadata={"url": source})

    def _extract_pdf_response(self, content: bytes, source: str) -> ExtractedContent:
        """Write PDF bytes to a temp file and extract text via pypdf with pdfminer fallback.

        Truncated or malformed PDFs (PdfStreamError) are handled gracefully:
        pypdf is tried first; on failure pdfminer.six is tried; if both fail
        an empty ExtractedContent is returned so the job completes as 'skipped'
        rather than dying after 3 retries.
        """
        import logging
        import os
        import pypdf

        logging.getLogger("pypdf").setLevel(logging.ERROR)
        logger = logging.getLogger(__name__)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # --- pypdf attempt ---
            try:
                parts = []
                with open(tmp_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    num_pages = len(reader.pages)
                    for page in reader.pages:
                        t = page.extract_text()
                        if t:
                            parts.append(t)
                text = "\n".join(parts)
                if text.strip():
                    return ExtractedContent(text=text, source_path=source,
                                            metadata={"url": source, "pages": num_pages})
                # Empty yield — fall through to pdfminer
            except Exception as pypdf_err:
                logger.warning("pypdf failed for %s (%s) — trying pdfminer fallback", source, pypdf_err)

            # --- pdfminer fallback ---
            try:
                from pdfminer.high_level import extract_text as pdfminer_extract
                text = pdfminer_extract(tmp_path)
                num_pages = 0  # pdfminer doesn't report page count cheaply
                if text.strip():
                    return ExtractedContent(text=text, source_path=source,
                                            metadata={"url": source, "pages": num_pages})
            except Exception as pm_err:
                logger.warning("pdfminer fallback also failed for %s (%s)", source, pm_err)

            # Both extractors failed — return empty so IngestAgent skips gracefully
            logger.warning("PDF at %s could not be extracted (truncated or malformed) — skipping", source)
            return ExtractedContent(text="", source_path=source,
                                    metadata={"url": source, "pages": 0})
        finally:
            os.unlink(tmp_path)
