# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest


@pytest.fixture
def fake_public_dns(monkeypatch):
    """Let URL-skill tests use made-up hostnames with respx.

    Resolves every name to a public address (no real DNS) and turns off
    connection pinning so respx routes written against the hostname still match.
    Pinning itself is covered in tests/security/package.
    """
    from synthadoc.security import ssrf

    async def resolve(host, port):
        return ["93.184.216.34"]

    def unpinned(self, target, headers):
        return target.url, {k: v for k, v in headers.items() if k.lower() != "host"}, {}

    monkeypatch.setattr(ssrf, "_system_resolver", resolve)
    monkeypatch.setattr(ssrf.GuardedClient, "_pin", unpinned)
