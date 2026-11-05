# Pulse Internet Speed Test

## Recommended architecture

The UI is a standalone HTML/CSS/JavaScript page. Browser-only measurement is viable when the page can reach suitable endpoints: `fetch()` can measure ping-like round trips, download bytes, and uploaded bytes. A dependable self-hosted test needs server endpoints that return uncached payloads and accept/discard upload bodies. A public speed-test service is another option, but its endpoint availability, CORS policy, server location, and capacity are outside your control.

For a meaningful test, avoid cached downloads, enable CORS only for the page origin when cross-origin, allow `OPTIONS` preflight if custom headers/methods are used, and plan for concurrent users and bandwidth costs. CDN/reverse-proxy rules must bypass caching on test routes. Results are estimates: server location/load, Wi-Fi, device CPU, browser scheduling, other traffic, and ISP routing all influence them. See [MDN's CORS guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) and [HTTP caching guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching).

## Run locally

The dependency-free server needs Python 3.9+ and no third-party packages:

```sh
python3 speedtest_server.py
```

Open <http://127.0.0.1:8080/>. The server serves `speed-test.html` plus `/ping`, `/download`, and `/upload`. The page can also be opened directly, but a browser may block its requests from the `file:` origin; use the local server for the simplest setup.

To run the FastAPI app that Vercel deploys:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8080
```

## Configuration

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SPEEDTEST_HOST` | `127.0.0.1` | Listen address for `speedtest_server.py` only. Vercel assigns the host. |
| `SPEEDTEST_PORT` | `8080` | Listen port for `speedtest_server.py` only. |
| `SPEEDTEST_ALLOWED_ORIGINS` | `*` | Comma-separated allowed page origins for CORS. Set this to your exact HTTPS origin for a cross-origin deployment. |
| `SPEEDTEST_MAX_UPLOAD` | `33554432` locally, `3145728` on Vercel | Maximum accepted upload body in bytes. The Vercel app also clamps this to 4,500,000 bytes. |
| `SPEEDTEST_MAX_DOWNLOAD` | `67108864` locally, `8388608` on Vercel | Maximum generated download response in bytes. |
| `SPEEDTEST_MAX_CONCURRENT` | `4` locally, `8` on Vercel | Concurrent transfer requests on this process or function instance. Extra requests receive HTTP 503. |

```sh
SPEEDTEST_PORT=8080 python3 speedtest_server.py
```

Host the page and test server on HTTPS for real users. The page calls whatever host it was opened from, so serve the page and the `/ping`, `/download`, and `/upload` routes together. Put the dependency-free Python server behind a production web server or reverse proxy before public use; add TLS, abuse/rate protection, sensible connection timeouts, observability, and capacity appropriate to your expected traffic. Do not expose a public bandwidth endpoint without accounting for bandwidth and denial-of-service risk.

## Deploy to Vercel

`app.py` exports a FastAPI `app`. Vercel detects FastAPI from `requirements.txt`, bundles that file as one Python function, and sends every request to it. There is no build command and no output directory.

```sh
npx vercel
```

`vercel.json` keeps the function alive for up to 300 seconds (so a slow 8 MB download can finish) and ships `speed-test.html` inside the function bundle. The page and the API share the deployment origin, and the page measures that origin automatically.

On Vercel, set:

- `SPEEDTEST_ALLOWED_ORIGINS` to the site origin, such as `https://your-project.vercel.app`, once you leave the open default.
- The function region closest to the people you are measuring. Hobby projects have one region. Singapore (`sin1`) is the closest region to Myanmar.

The page posts 2 MB per upload so the body stays under Vercel’s 4.5 MB request limit. Downloads are streamed, which is what lets an 8 MB response through. Both transfer routes send `Cache-Control: no-store` and `Vercel-CDN-Cache-Control: no-store` so the CDN does not answer the test from cache.

`SPEEDTEST_MAX_CONCURRENT` applies to a single running instance. Vercel starts more instances as traffic grows, so this does not cap the whole project. Add a Vercel Firewall rate limit on `/download` and `/upload` before the URL is public. One test moves on the order of 90 MB, and Hobby includes 10 GB per month of transfer between the CDN and functions.

## How the readings work

- Ping: median of eight uncached `/ping` round trips.
- Jitter: average absolute change between adjacent ping samples.
- Download and upload: four parallel lanes, reporting total payload bits divided by elapsed wall-clock time. Transfers run for at least about three seconds and stop at bounded byte budgets.
- Stop aborts in-flight fetches. The server discards uploads and does not store test data.

The default page and server are self-hosted and have no external service dependency. The speed reflects the route to the host the page was opened from, so deploy that host near your users with enough network capacity.
