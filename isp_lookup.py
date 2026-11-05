"""Resolve a visitor ISP from the public address on the request.

The name comes from the address registry. Vercel supplies the visitor IP, not
the provider, so this asks a public lookup and caches the result.
"""

from ipaddress import ip_address
from json import loads
from threading import Lock
from time import monotonic
from urllib.request import Request, urlopen

_CACHE = {}
_LOCK = Lock()
_OK_TTL = 6 * 60 * 60
_MISS_TTL = 5 * 60
_MAX = 512


def client_ip(headers) -> str | None:
    if not headers:
        return None
    for name in ("x-vercel-forwarded-for", "x-real-ip", "x-forwarded-for"):
        raw = headers.get(name)
        if not raw:
            continue
        for part in str(raw).split(","):
            candidate = part.strip().strip('"')
            if candidate.startswith("[") and "]" in candidate:
                candidate = candidate[1:candidate.index("]")]
            elif candidate.count(":") == 1 and candidate.rsplit(":", 1)[-1].isdigit():
                candidate = candidate.rsplit(":", 1)[0]
            try:
                parsed = ip_address(candidate)
            except ValueError:
                continue
            if parsed.is_global:
                return str(parsed)
    return None


def _fetch(url: str) -> dict | None:
    request = Request(
        url,
        headers={"User-Agent": "PulseSpeedTest/1.0", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=3.5) as response:
            if getattr(response, "status", 200) != 200:
                return None
            body = response.read(65536)
    except Exception:
        return None
    try:
        data = loads(body.decode())
    except (ValueError, UnicodeError):
        return None
    return data if isinstance(data, dict) else None


def _name_from(data: dict) -> str | None:
    if data.get("success") is False or data.get("status") == "fail":
        return None
    connection = data.get("connection") if isinstance(data.get("connection"), dict) else {}
    for value in (connection.get("isp"), connection.get("org"), data.get("isp"), data.get("org")):
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    return None


def lookup_isp(ip: str) -> str | None:
    now = monotonic()
    with _LOCK:
        hit = _CACHE.get(ip)
        if hit and hit[0] > now:
            return hit[1]
    name = None
    for url in (
        f"https://ipwho.is/{ip}?fields=connection",
        f"http://ip-api.com/json/{ip}?fields=status,isp",
    ):
        data = _fetch(url)
        if not data:
            continue
        name = _name_from(data)
        if name:
            break
    with _LOCK:
        _CACHE[ip] = (monotonic() + (_OK_TTL if name else _MISS_TTL), name)
        if len(_CACHE) > _MAX:
            oldest = min(_CACHE, key=lambda key: _CACHE[key][0])
            _CACHE.pop(oldest, None)
    return name


def isp_for_headers(headers) -> str | None:
    ip = client_ip(headers)
    if not ip:
        return None
    return lookup_isp(ip)
