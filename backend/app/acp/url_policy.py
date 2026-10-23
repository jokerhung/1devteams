"""Validate origins and pin each connection to validated DNS results, retaining Host/TLS SNI."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

import httpx


class URLPolicyError(ValueError):
    pass


def completion_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/") + "/chat/completions", parts.query, "")
    )


class URLPolicy:
    def __init__(self, http_hosts: set[str] | None = None, private_hosts: set[str] | None = None) -> None:
        self.http_hosts = http_hosts or set()
        self.private_hosts = private_hosts or set()

    async def validate(self, value: str) -> tuple[httpx.URL, list[str]]:
        try:
            url = httpx.URL(value)
            if url.scheme not in ("https", "http") or not url.host or url.userinfo or url.fragment:
                raise URLPolicyError("Invalid API URL")
            if any(
                re.search(r"key|token|secret|password|credential|authorization", key, re.IGNORECASE)
                for key in url.params
            ):
                raise URLPolicyError("API credentials must be supplied in headers, not URL queries")
            host = url.host.lower().rstrip(".")
            if url.scheme == "http" and host not in self.http_hosts:
                raise URLPolicyError("HTTP API host is not allowed")
            results = await asyncio.get_running_loop().getaddrinfo(
                host,
                url.port or (443 if url.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            ips = list(dict.fromkeys(item[4][0] for item in results))
            if not ips:
                raise URLPolicyError("API host has no addresses")
            for address in ips:
                ip = ipaddress.ip_address(address)
                if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                    ip = ip.ipv4_mapped
                if (
                    ip.is_link_local
                    or ip in ipaddress.ip_network("fd00:ec2::254/128")
                    or ip.is_multicast
                    or ip.is_unspecified
                ):
                    raise URLPolicyError("Metadata/link-local API address is forbidden")
                if not ip.is_global and host not in self.private_hosts:
                    raise URLPolicyError("Private API host is not allowed")
            return url, ips
        except (httpx.InvalidURL, OSError) as error:
            raise URLPolicyError("API host validation failed") from error


class PinnedTransport(httpx.AsyncHTTPTransport):
    def __init__(self, origin: str, policy: URLPolicy) -> None:
        super().__init__(trust_env=False, retries=0)
        self.origin = httpx.URL(origin)
        self.policy = policy

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if (request.url.scheme, request.url.host, request.url.port) != (
            self.origin.scheme,
            self.origin.host,
            self.origin.port,
        ):
            raise URLPolicyError("Cross-origin credential forwarding forbidden")
        url, addresses = await self.policy.validate(str(request.url))
        headers = request.headers.copy()
        headers["Host"] = request.url.netloc.decode("ascii")
        extensions = dict(request.extensions)
        extensions["sni_hostname"] = request.url.host
        pinned = httpx.Request(
            request.method,
            url.copy_with(host=addresses[0]),
            headers=headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await super().handle_async_request(pinned)
