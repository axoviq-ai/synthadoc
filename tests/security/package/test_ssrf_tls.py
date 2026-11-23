# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Real-TLS proof that pinning the connection keeps certificate checks on the hostname.

The connection goes to the validated IP (127.0.0.1 here, allowed through
allow_private) while the certificate must still match the ORIGINAL hostname.
Needs ``cryptography`` to mint a throwaway CA; the lean CI job installs it.
"""
from __future__ import annotations

import asyncio
import datetime
import ipaddress
import ssl

import httpx
import pytest

pytest.importorskip("cryptography")

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID  # noqa: E402

from synthadoc.security.ssrf import UrlPolicy, guarded_client  # noqa: E402

HOSTNAME = "pinned.test"


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _validity(builder: x509.CertificateBuilder) -> x509.CertificateBuilder:
    now = datetime.datetime.now(datetime.timezone.utc)
    return builder.not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(
        now + datetime.timedelta(days=1))


def _make_ca():
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        _validity(x509.CertificateBuilder())
        .subject_name(_name("test-ca")).issuer_name(_name("test-ca"))
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _issue(ca_key, ca_cert, san: x509.GeneralName):
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        _validity(x509.CertificateBuilder())
        .subject_name(_name("server")).issuer_name(ca_cert.subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .add_extension(x509.SubjectAlternativeName([san]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                       critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def _pem(cert) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _key_pem(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


async def _serve(tmp_path, san: x509.GeneralName):
    ca_key, ca_cert = _make_ca()
    key, cert = _issue(ca_key, ca_cert, san)
    ca_file, cert_file, key_file = (tmp_path / n for n in ("ca.pem", "srv.pem", "srv.key"))
    ca_file.write_bytes(_pem(ca_cert))
    cert_file.write_bytes(_pem(cert))
    key_file.write_bytes(_key_pem(key))

    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(str(cert_file), str(key_file))

    async def handle(reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server_ctx)
    port = server.sockets[0].getsockname()[1]
    client_ctx = ssl.create_default_context(cafile=str(ca_file))
    return server, port, client_ctx


async def _resolve_to_loopback(host, port):
    return ["127.0.0.1"]


async def _get(client_ctx, port):
    policy = UrlPolicy(allow_private=True, ssl_context=client_ctx, total_timeout=10)
    async with guarded_client(policy, resolver=_resolve_to_loopback) as client:
        return await client.get(f"https://{HOSTNAME}:{port}/")


async def test_certificate_for_the_hostname_is_accepted_over_the_pinned_ip(tmp_path):
    server, port, client_ctx = await _serve(tmp_path, x509.DNSName(HOSTNAME))
    try:
        resp = await _get(client_ctx, port)
    finally:
        server.close()
        await server.wait_closed()
    assert resp.status_code == 200 and resp.text == "ok"


async def test_certificate_for_another_hostname_is_rejected(tmp_path):
    server, port, client_ctx = await _serve(tmp_path, x509.DNSName("other.test"))
    try:
        with pytest.raises(httpx.ConnectError):
            await _get(client_ctx, port)
    finally:
        server.close()
        await server.wait_closed()


async def test_certificate_valid_only_for_the_pinned_ip_is_rejected(tmp_path):
    # If verification ran against the IP instead of the hostname this would succeed.
    server, port, client_ctx = await _serve(
        tmp_path, x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    try:
        with pytest.raises(httpx.ConnectError):
            await _get(client_ctx, port)
    finally:
        server.close()
        await server.wait_closed()
