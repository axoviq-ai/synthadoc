"""Shared URL content-quality constants used by refresh_search_seeds.py and validate_seeds.py."""
from __future__ import annotations

import re

# URLs returning fewer than this many characters are treated as thin/unusable.
MIN_CONTENT_CHARS = 500

# WAF/CDN bot-challenge patterns — some hosts return HTTP 200 with a JS challenge
# or "Access Denied" body instead of real content.  Check against text[:1_000].
BOT_BLOCK_RE = re.compile(
    r"""
    (?:
        Incapsula\s+incident\s+ID
      | _cf_chl_opt
      | challenge-form
      | Ray\s+ID:\s+[0-9a-f]{16}
      | Access\s+Denied\b.*?(?:server|reference\s+\#)
      | enable\s+JavaScript\s+and\s+cookies
      | bot\s+or\s+(?:automated?\s+)?(?:request|traffic|crawler)
    )
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

# Login / paywall patterns — some sites serve a gate page as HTTP 200 instead of
# raising 401/403.  Check against text[:3_000].
LOGIN_WALL_RE = re.compile(
    r"""
    (?:
        please\s+(?:sign|log)\s*(?:-\s*)?in\b
      | (?:sign|log)\s*(?:-\s*)?in\s+(?:to\s+access|is\s+required|required)
      | you\s+(?:must|need\s+to)\s+(?:be\s+)?(?:signed|logged)\s*[-\s]?in
      | (?:this\s+)?(?:page|content|article|resource)\s+(?:is\s+)?(?:available\s+only|requires?)\s+(?:to\s+)?(?:subscribers?|members?|registered\s+users?)
      | (?:subscribe|subscription)\s+(?:to\s+access|required\s+to)
      | (?:access\s+denied|not\s+authorized\s+to\s+access)
      | authentication\s+required
      | \bpaywall\b
      | restricted\s+to\s+(?:subscribers?|members?|registered\s+users?)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
