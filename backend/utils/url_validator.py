"""
SSRF-safe URL validation.

Blocks file://, gopher://, and all non-http(s) schemes.
Blocks private RFC-1918, loopback, link-local (169.254.x.x / AWS metadata),
and other non-routable addresses.
Legitimate public scan targets (external IPs / hostnames) are allowed through.
"""

import ipaddress
import re
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset(('http', 'https'))

_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # IPv4 private / special-use
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('127.0.0.0/8'),       # loopback
    ipaddress.ip_network('169.254.0.0/16'),    # link-local / AWS metadata (169.254.169.254)
    ipaddress.ip_network('0.0.0.0/8'),
    ipaddress.ip_network('100.64.0.0/10'),     # carrier-grade NAT
    ipaddress.ip_network('192.0.0.0/24'),
    ipaddress.ip_network('198.18.0.0/15'),     # benchmarking
    ipaddress.ip_network('198.51.100.0/24'),
    ipaddress.ip_network('203.0.113.0/24'),
    ipaddress.ip_network('240.0.0.0/4'),       # reserved
    ipaddress.ip_network('255.255.255.255/32'),
    # IPv6 private / special-use
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
    ipaddress.ip_network('fe80::/10'),
    ipaddress.ip_network('::/128'),
    ipaddress.ip_network('::ffff:0:0/96'),     # IPv4-mapped
]

_BLOCKED_HOSTNAMES = frozenset((
    'localhost',
    'localhost.localdomain',
    'ip6-localhost',
    'ip6-loopback',
    'broadcasthost',
    # Cloud metadata service hostnames
    'metadata.google.internal',
    'metadata.goog',
))

_DECIMAL_ONLY = re.compile(r'^\d+$')


def _is_blocked_ip(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_multicast:
            return True
        return any(ip in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        return True  # fail-safe: unknown → blocked


def validate_url(url: str) -> tuple[bool, str | None]:
    """Check a user-supplied URL for SSRF risks.

    Returns (True, None) when the URL is safe.
    Returns (False, reason) when it must be rejected.

    DNS failures are not treated as blocking — the scanner will surface them.
    """
    if not url or not isinstance(url, str):
        return False, 'URL is required'

    url = url.strip()

    try:
        parsed = urlparse(url)
    except Exception:
        return False, 'Malformed URL'

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False, (
            f"URL scheme '{parsed.scheme}' is not allowed. "
            'Only http and https are permitted.'
        )

    hostname = parsed.hostname
    if not hostname:
        return False, 'URL must contain a valid hostname'

    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return False, f"Hostname '{hostname}' is not allowed"

    # Decimal-encoded IP trick: http://2130706433/ == http://127.0.0.1/
    if _DECIMAL_ONLY.match(hostname):
        return False, 'Numeric-only hostnames are not allowed'

    # Raw IP address supplied — validate directly without DNS
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if _is_blocked_ip(str(ip_obj)):
            return False, (
                f"'{hostname}' is in a private or reserved address range "
                'and cannot be used as a scan target'
            )
        return True, None
    except ValueError:
        pass  # not a raw IP, proceed to DNS

    # Resolve hostname and verify every returned address is public
    try:
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        for _fam, _typ, _proto, _canon, sockaddr in addr_infos:
            resolved = sockaddr[0]
            if _is_blocked_ip(resolved):
                return False, (
                    f"Hostname '{hostname}' resolves to '{resolved}', "
                    'which is a private or reserved address. '
                    'Only public targets are allowed.'
                )
    except (socket.gaierror, socket.herror, OSError):
        pass  # DNS failure — let the scanner report the error

    return True, None


def validate_urls(urls: list[str]) -> tuple[bool, str | None]:
    """Validate a list of URLs. Stops and returns on first failure."""
    for url in urls:
        ok, err = validate_url(url)
        if not ok:
            return False, f"Invalid URL '{url}': {err}"
    return True, None
