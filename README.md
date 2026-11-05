# Pulse Internet Speed Test

## Recommended architecture

The UI is a standalone HTML/CSS/JavaScript page. Browser-only measurement is viable when the page can reach suitable endpoints: `fetch()` can measure ping-like round trips, download bytes, and uploaded bytes. A dependable self-hosted test needs server endpoints that return uncached payloads and accept/discard upload bodies. A public speed-test service is another option, but its endpoint availability, CORS policy, server location, and capacity are outside your control.

For a meaningful test, avoid cached downloads, enable CORS only for the page origin when cross-origin, allow `OPTIONS` preflight if custom headers/methods are used, and plan for concurrent users and bandwidth costs. CDN/reverse-proxy rules must bypass caching on test routes. Results are estimates: server location/load, Wi-Fi, device CPU, browser scheduling, other traffic, and ISP routing all influence them. See [MDN's CORS guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) and [HTTP caching guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching).

## Run locally

Requires Python 3.9+; there are no third-party packages.

```sh
cd outputs
python3 speedtest_server.py
```

Open <http://127.0.0.1:8080/>. The server serves `speed-test.html` plus `/ping`, `/download`, and `/upload`. The page can also be opened directly, but a browser may block its requests from the `file:` origin; use the local server for the simplest setup.

## Configuration

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SPEEDTEST_HOST` | `127.0.0.1` | Listen address; keep local unless deploying behind a protected proxy. |
| `SPEEDTEST_PORT` | `8080` | Listen port. |
| `SPEEDTEST_ALLOWED_ORIGINS` | `*` | Comma-separated allowed page origins for CORS. Set this to your exact HTTPS origin for a cross-origin deployment. |
| `SPEEDTEST_MAX_UPLOAD` | `33554432` | Maximum accepted upload body in bytes. |
| `SPEEDTEST_MAX_DOWNLOAD` | `67108864` | Maximum generated download response in bytes. |
| `SPEEDTEST_MAX_CONCURRENT` | `4` | Concurrent transfer requests. Extra requests receive HTTP 503. |

Example for testing a separately hosted page:

```sh
SPEEDTEST_HOST=127.0.0.1 SPEEDTEST_PORT=8080 SPEEDTEST_ALLOWED_ORIGINS=https://your-site.example python3 speedtest_server.py
```

Host the page and test server on HTTPS for real users. If they use different origins, select **Configure** in the page and enter the test server base URL (no endpoint path). Put the Python demo behind a production web server or reverse proxy before public use; add TLS, abuse/rate protection, sensible connection timeouts, observability, and capacity appropriate to your expected traffic. Do not expose a public bandwidth endpoint without accounting for bandwidth and denial-of-service risk.

## How the readings work

- Ping: median of eight uncached `/ping` round trips.
- Jitter: average absolute change between adjacent ping samples.
- Download and upload: four parallel lanes, reporting total payload bits divided by elapsed wall-clock time. Transfers run for at least about three seconds and stop at bounded byte budgets.
- Stop aborts in-flight fetches. The server discards uploads and does not store test data.

The default page/server are self-hosted and have no external service dependency. The speed reflects the route to the configured test host, so choose a host near your users with enough network capacity.
