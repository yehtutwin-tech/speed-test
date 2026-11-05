"""Vercel entrypoint for the speed test.

Vercel loads the top-level ``app`` from this file and routes every request to
it. ``speedtest_server.py`` remains the dependency-free local server.
"""

from pathlib import Path
import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.requests import ClientDisconnect

from isp_lookup import isp_for_headers

ROOT = Path(__file__).resolve().parent
# Stay under Vercel's 4.5 MB request-body limit. The page sends 2 MB uploads.
PLATFORM_BODY_LIMIT = 4_500_000
MAX_UPLOAD = min(
    int(os.environ.get("SPEEDTEST_MAX_UPLOAD", str(3 * 1024 * 1024))),
    PLATFORM_BODY_LIMIT,
)
MAX_DOWNLOAD = int(os.environ.get("SPEEDTEST_MAX_DOWNLOAD", str(8 * 1024 * 1024)))
MAX_CONCURRENT = int(os.environ.get("SPEEDTEST_MAX_CONCURRENT", "8"))
# One random megabyte, repeated. Generated once so transfer time is not spent
# in os.urandom. application/octet-stream is outside Vercel's compression list.
PAYLOAD = os.urandom(1024 * 1024)

origins = [
    item.strip()
    for item in os.environ.get("SPEEDTEST_ALLOWED_ORIGINS", "*").split(",")
    if item.strip()
] or ["*"]

NO_STORE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "CDN-Cache-Control": "no-store",
    "Vercel-CDN-Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=600,
)
slots = asyncio.Semaphore(MAX_CONCURRENT)
slot_gate = asyncio.Lock()


def load_page() -> bytes:
    for path in (ROOT / "speed-test.html", Path.cwd() / "speed-test.html"):
        if path.is_file():
            return path.read_bytes()
    return b"speed-test.html is missing from the deployment bundle."


PAGE = load_page()
ICON_CACHE = {
    "Cache-Control": "public, max-age=86400",
    "Vercel-CDN-Cache-Control": "public, max-age=86400",
    "X-Content-Type-Options": "nosniff",
}


def load_asset(name: str) -> bytes:
    for path in (ROOT / name, Path.cwd() / name):
        if path.is_file():
            return path.read_bytes()
    return b""


FAVICON_ICO = load_asset("favicon.ico")
FAVICON_SVG = load_asset("favicon.svg")


def plain(body: bytes, status: int = 200) -> Response:
    return Response(body, status_code=status, media_type="text/plain", headers=NO_STORE)


async def acquire_slot() -> bool:
    # The gate makes the check-and-acquire atomic. Otherwise two requests can
    # both pass locked() and the loser blocks on acquire() until a slot frees.
    async with slot_gate:
        if slots.locked():
            return False
        await slots.acquire()
        return True


def iter_payload(size: int):
    remaining = size
    while remaining >= len(PAYLOAD):
        yield PAYLOAD
        remaining -= len(PAYLOAD)
    if remaining:
        yield PAYLOAD[:remaining]


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(PAGE, headers=NO_STORE)


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    if not FAVICON_ICO:
        return plain(b"not found", 404)
    return Response(FAVICON_ICO, media_type="image/x-icon", headers=ICON_CACHE)


@app.get("/favicon.svg", include_in_schema=False)
def favicon_svg():
    if not FAVICON_SVG:
        return plain(b"not found", 404)
    return Response(FAVICON_SVG, media_type="image/svg+xml", headers=ICON_CACHE)


@app.get("/ping")
def ping():
    return plain(b"ok")


@app.get("/network")
async def network(request: Request):
    isp = await asyncio.to_thread(isp_for_headers, request.headers)
    return JSONResponse({"isp": isp}, headers=NO_STORE)


@app.get("/download")
async def download(request: Request):
    raw = request.query_params.get("bytes", str(8 * 1024 * 1024))
    try:
        size = int(raw)
    except ValueError:
        size = 0
    if size < 1 or size > MAX_DOWNLOAD:
        return plain(b"invalid byte count", 413)
    if not await acquire_slot():
        return plain(b"test capacity busy", 503)

    async def body():
        try:
            for chunk in iter_payload(size):
                yield chunk
        finally:
            slots.release()

    headers = {**NO_STORE, "Content-Length": str(size)}
    return StreamingResponse(body(), media_type="application/octet-stream", headers=headers)


@app.post("/upload")
async def upload(request: Request):
    try:
        length = int(request.headers.get("content-length", "-1"))
    except ValueError:
        length = -1
    if length < 0 or length > MAX_UPLOAD:
        return plain(b"upload too large", 413)
    if not await acquire_slot():
        return plain(b"test capacity busy", 503)
    try:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_UPLOAD:
                return plain(b"upload too large", 413)
        if received != length:
            return plain(b"short upload", 400)
        return plain(b"ok")
    except ClientDisconnect:
        return plain(b"client closed", 400)
    finally:
        slots.release()
