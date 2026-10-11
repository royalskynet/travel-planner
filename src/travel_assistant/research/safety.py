from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    pass


Resolver = Callable[[str, int], Iterable[object]]


def _default_resolver(host: str, port: int) -> Iterable[object]:
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def _addresses(records: Iterable[object]) -> list[str]:
    values: list[str] = []
    for record in records:
        if isinstance(record, str):
            values.append(record)
            continue
        try:
            values.append(record[4][0])  # getaddrinfo tuple
        except (IndexError, TypeError):
            raise UnsafeUrlError(
                "resolver returned an invalid address record"
            ) from None
    return values


def validate_public_https_url(
    url: str, *, resolver: Resolver = _default_resolver
) -> str:
    try:
        parsed = urlparse(url)
        port = parsed.port or 443
    except ValueError as exc:
        raise UnsafeUrlError("invalid URL") from exc
    if parsed.scheme != "https":
        raise UnsafeUrlError("only HTTPS URLs are allowed")
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise UnsafeUrlError("URL must have a host and no embedded credentials")
    if parsed.fragment:
        raise UnsafeUrlError("URL fragments are not allowed for service endpoints")
    try:
        literal = ipaddress.ip_address(parsed.hostname.strip("[]"))
        addresses = [str(literal)]
    except ValueError:
        try:
            addresses = _addresses(resolver(parsed.hostname, port))
        except (OSError, socket.gaierror) as exc:
            raise UnsafeUrlError("host could not be resolved") from exc
    if not addresses:
        raise UnsafeUrlError("host did not resolve to an address")
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise UnsafeUrlError("resolver returned a non-IP address") from exc
        if not address.is_global:
            raise UnsafeUrlError(
                "private, loopback, link-local, reserved, or multicast targets are blocked"
            )
    return url
