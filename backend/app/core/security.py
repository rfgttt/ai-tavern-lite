from __future__ import annotations

import hmac
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit


class UnsafeOutboundURLError(ValueError):
    """Raised when an outbound URL can reach a non-public destination."""


@dataclass(frozen=True)
class ValidatedOutboundURL:
    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".arpa",
)


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # is_global rejects loopback, private, link-local, multicast, reserved,
    # unspecified, documentation and other non-routable ranges.
    return bool(address.is_global)


def validate_outbound_url(
    raw_url: str,
    *,
    allow_private_hosts: bool = False,
    allowed_hosts: tuple[str, ...] = (),
) -> ValidatedOutboundURL:
    """Validate an LLM base URL and resolve it before any outbound request.

    This is an application-layer SSRF guard. Production deployments should also
    apply network egress rules so the application container cannot reach cloud
    metadata or private infrastructure.
    """
    url = str(raw_url or "").strip()
    if not url:
        raise UnsafeOutboundURLError("Base URL 不能为空")

    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeOutboundURLError("Base URL 仅允许 http 或 https")
    if parsed.username or parsed.password:
        raise UnsafeOutboundURLError("Base URL 不允许包含用户名或密码")
    if not parsed.hostname:
        raise UnsafeOutboundURLError("Base URL 缺少有效主机名")

    hostname = parsed.hostname.rstrip(".").lower()
    if len(hostname) > 253:
        raise UnsafeOutboundURLError("Base URL 主机名过长")
    if hostname == "localhost" or hostname.endswith(_BLOCKED_HOST_SUFFIXES):
        if not allow_private_hosts:
            raise UnsafeOutboundURLError("Base URL 不允许指向本机或内部域名")

    if allowed_hosts:
        normalized_allowlist = {item.rstrip(".").lower() for item in allowed_hosts if item.strip()}
        if hostname not in normalized_allowlist:
            raise UnsafeOutboundURLError("Base URL 主机不在生产环境允许列表中")

    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as error:
        raise UnsafeOutboundURLError("Base URL 端口无效") from error

    try:
        literal_address = ipaddress.ip_address(hostname)
        addresses = {literal_address}
    except ValueError:
        try:
            resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise UnsafeOutboundURLError("Base URL 域名无法解析") from error
        addresses = set()
        for item in resolved:
            try:
                addresses.add(ipaddress.ip_address(item[4][0]))
            except ValueError:
                continue

    if not addresses:
        raise UnsafeOutboundURLError("Base URL 未解析到有效地址")

    if not allow_private_hosts:
        blocked = sorted(str(address) for address in addresses if not _is_public_address(address))
        if blocked:
            raise UnsafeOutboundURLError("Base URL 解析到了非公网地址，已拒绝连接")

    return ValidatedOutboundURL(
        url=url,
        hostname=hostname,
        port=port,
        addresses=tuple(sorted(str(address) for address in addresses)),
    )


def secure_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
