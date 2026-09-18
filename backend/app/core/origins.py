"""Allowed-origin normalisation (FR-107).

One canonical form, ``scheme://host[:port]``, so a registered origin and the ``Origin`` header a
browser sends meet as exact strings. The tenant resolver (step B2) must normalise the header with
this same function; a second implementation would let the two drift apart.
"""

import ipaddress
import re
from urllib.parse import urlsplit

import idna

MAX_ORIGIN_LENGTH = 255

_DEFAULT_PORTS = {"https": 443, "http": 80}
# Plain http is accepted only for local development; a deployed site must use https.
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
_DNS_LABEL = re.compile(r"\A(?!-)[a-z0-9-]{1,63}(?<!-)\Z")


def normalize_origin(raw: str) -> str:
    """Return the canonical form of ``raw``, or raise ``ValueError`` saying what to fix."""
    value = raw.strip()
    if not value:
        raise ValueError("Origin is empty.")
    if len(value) > 2 * MAX_ORIGIN_LENGTH:
        # Bounds the parsing work; the canonical form is length-checked at the end, because
        # punycode conversion can make a host longer than the text the user typed.
        raise ValueError(f"Origin is longer than {MAX_ORIGIN_LENGTH} characters.")
    if value.lower() == "null":
        raise ValueError("The 'null' origin cannot be registered.")
    if "*" in value:
        raise ValueError("Wildcards are not supported; register each origin separately.")
    if "\\" in value or any(ch.isspace() for ch in value):
        raise ValueError("Origin contains invalid characters.")

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise ValueError("Origin must start with https:// (or http:// for localhost).")
    if not parts.netloc:
        raise ValueError("Origin has no host, e.g. https://www.example.com.")
    if parts.path not in ("", "/") or parts.query or parts.fragment or value.endswith(("?", "#")):
        raise ValueError("An origin is scheme and host only, without a path, query or fragment.")
    if "@" in parts.netloc:
        raise ValueError("Origin must not contain a username or password.")

    try:
        port = parts.port
    except ValueError:
        raise ValueError("Origin has an invalid port.") from None
    if port == 0:
        raise ValueError("Origin has an invalid port.")

    host = _normalize_host(parts.hostname or "")
    if scheme == "http" and host not in _LOOPBACK_HOSTS:
        raise ValueError("Origin must use https://; plain http:// is only allowed for localhost.")

    origin = f"{scheme}://{host}"
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        origin = f"{origin}:{port}"
    if len(origin) > MAX_ORIGIN_LENGTH:
        raise ValueError(f"Origin is longer than {MAX_ORIGIN_LENGTH} characters.")
    return origin


def _normalize_host(hostname: str) -> str:
    if not hostname:
        raise ValueError("Origin has no host, e.g. https://www.example.com.")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        return f"[{address.compressed}]" if address.version == 6 else address.compressed

    try:
        # Browsers send internationalised hosts as punycode computed with UTS-46. The stdlib
        # "idna" codec implements IDNA2003, which maps ß to ss: it would store
        # https://faß.example as https://fass.example — an origin the real site never sends, and
        # one an unrelated fass.example would match.
        ascii_host = idna.encode(hostname, uts46=True, transitional=False).decode("ascii").lower()
    except idna.IDNAError:
        raise ValueError("Origin host is not a valid domain name.") from None
    labels = ascii_host.split(".")
    if not all(_DNS_LABEL.match(label) for label in labels):
        raise ValueError("Origin host is not a valid domain name.")
    return ascii_host


_PREVIEW_DOMAIN_SUFFIXES = (
    ".vercel.app",
    ".netlify.app",
    ".pages.dev",
    ".amplifyapp.com",
    ".up.railway.app",
)

_TUNNEL_DOMAIN_SUFFIXES = (
    ".ngrok.io",
    ".ngrok-free.app",
    ".loca.lt",
    ".trycloudflare.com",
)


def is_preview_origin(raw_origin: str) -> bool:
    """Check if an origin is an ephemeral preview domain (e.g. *.vercel.app)."""
    try:
        parts = urlsplit(raw_origin.strip())
        host = (parts.hostname or "").lower()
        return any(host.endswith(suffix) for suffix in _PREVIEW_DOMAIN_SUFFIXES)
    except (ValueError, AttributeError):
        return False


def is_private_or_loopback_origin(raw_origin: str) -> bool:
    """Check if an origin is localhost, a loopback IP, private RFC1918/RFC4193 network,
    or an ephemeral tunnel (ngrok, etc.). These must NEVER be auto-bound as production domains.
    """
    try:
        parts = urlsplit(raw_origin.strip())
        host = (parts.hostname or "").lower()
        if host in _LOOPBACK_HOSTS:
            return True
        if any(host.endswith(suffix) for suffix in _TUNNEL_DOMAIN_SUFFIXES):
            return True
        try:
            addr = ipaddress.ip_address(host)
            return addr.is_loopback or addr.is_private or addr.is_link_local
        except ValueError:
            pass
        return False
    except (ValueError, AttributeError):
        return True


def get_origin_aliases(canonical_origin: str) -> list[str]:
    """Return a list of canonical origin strings including automatic apex/www sibling alias.

    e.g. https://sweets.com -> [https://sweets.com, https://www.sweets.com]
         https://www.sweets.com -> [https://www.sweets.com, https://sweets.com]
    """
    try:
        parts = urlsplit(canonical_origin)
        scheme = parts.scheme.lower()
        hostname = (parts.hostname or "").lower()
        port = parts.port

        if not hostname or hostname in _LOOPBACK_HOSTS or is_private_or_loopback_origin(canonical_origin):
            return [canonical_origin]

        try:
            ipaddress.ip_address(hostname)
            return [canonical_origin]
        except ValueError:
            pass

        port_suffix = f":{port}" if port and port != _DEFAULT_PORTS.get(scheme) else ""

        if hostname.startswith("www."):
            apex = hostname[4:]
            if "." in apex:
                sibling = f"{scheme}://{apex}{port_suffix}"
                return [canonical_origin, sibling]
        elif "." in hostname and not is_preview_origin(canonical_origin):
            sibling = f"{scheme}://www.{hostname}{port_suffix}"
            return [canonical_origin, sibling]

        return [canonical_origin]
    except (ValueError, AttributeError):
        return [canonical_origin]

