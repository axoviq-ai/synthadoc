# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import re

# Matches the canonical ^[filename:start-end] citation marker format.
# Used in both the ingest pipeline (Pass 4) and lint checks (Check 5).
CITATION_RE = re.compile(r'\^\[([^\]:]+):(\d+)-(\d+)\]')

# Matches any ^[...] shape — used to detect malformed markers that were
# not captured by CITATION_RE (e.g. missing line numbers, extra colons).
MALFORMED_CITE_RE = re.compile(r'\^\[[^\]]*\]')
