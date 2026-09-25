"""Model endpoints must be self-hosted until a provider passes review.

Sending a child's question to a third-party model provider is exactly what the
provider due-diligence gate exists for, so this refuses any endpoint that is not
on this machine or a private network. It is a technical backstop for that
policy, not a substitute for it.
"""
import ipaddress
from urllib.parse import urlsplit


class EndpointError(ValueError):
    pass


def require_private_endpoint(url: str) -> str:
    """Returns the URL without a trailing slash, or raises `EndpointError`."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise EndpointError("Model endpoints must be http(s) URLs with a host.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise EndpointError("Model endpoints must not carry credentials, a query or a fragment.")
    host = parts.hostname
    if host != "localhost":
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise EndpointError("Model endpoints must be localhost or a private IP address, not a hostname.") from None
        if not (address.is_loopback or address.is_private) or address.is_unspecified:
            raise EndpointError("Model endpoints must be on this machine or a private network.")
    return url.rstrip("/")
