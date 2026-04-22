# JS Discovery — API Docs

**Base URL:** `http://localhost:3001`  
**Content-Type:** `application/json` (all responses)

---

## Table of Contents

### System
1. [`GET /api/health`](#health-check-api) — Health Check

### Dashboard
2. [`GET /api/dashboard/stats`](#dashboard-stats-api) — Dashboard Statistics

### Scan Management
3. [`GET /api/scans`](#list-scans-api) — List All Scans
4. [`POST /api/scans`](#create-scan-api) — Create a New Scan
5. [`GET /api/scans/<scan_id>`](#get-scan-api) — Get Scan Details
6. [`DELETE /api/scans/<scan_id>`](#delete-scan-api) — Delete a Scan
7. [`POST /api/scans/<scan_id>/start`](#start-scan-api) — Start a Scan
8. [`POST /api/scans/<scan_id>/stop`](#stop-scan-api) — Stop a Running Scan
9. [`GET /api/scans/<scan_id>/counts`](#scan-counts-api) — Get Result Counts

### Scan Results
10. [`GET /api/scans/<scan_id>/secrets`](#secrets-api) — Discovered Secrets
11. [`GET /api/scans/<scan_id>/endpoints`](#endpoints-api) — Discovered API Endpoints
12. [`GET /api/scans/<scan_id>/parameters`](#parameters-api) — Parameters *(stub — always empty)*
13. [`GET /api/scans/<scan_id>/cloud-resources`](#cloud-resources-api) — Cloud Resources
14. [`GET /api/scans/<scan_id>/subdomains`](#subdomains-api) — Subdomains
15. [`GET /api/scans/<scan_id>/ips`](#ips-api) — IP Addresses
16. [`GET /api/scans/<scan_id>/emails`](#emails-api) — Email Addresses
17. [`GET /api/scans/<scan_id>/urls`](#urls-api) — Discovered URLs
18. [`GET /api/scans/<scan_id>/app-links`](#app-links-api) — App Store Links
19. [`GET /api/scans/<scan_id>/doc-links`](#doc-links-api) — Documentation Links
20. [`GET /api/scans/<scan_id>/social-links`](#social-links-api) — Social Media Links
21. [`GET /api/scans/<scan_id>/files`](#files-api) — Downloaded JS Files
22. [`GET /api/scans/<scan_id>/files/<file_path>`](#file-content-api) — Get JS File Content
23. [`GET /api/scans/<scan_id>/input-urls`](#input-urls-api) — Input URLs
24. [`GET /api/scans/<scan_id>/failed-downloads`](#failed-downloads-api) — Failed Downloads

### Count Sub-Resources
25. [`GET /api/scans/<scan_id>/subdomains/counts`](#subdomain-counts-api) — Subdomain Status Counts
26. [`GET /api/scans/<scan_id>/emails/counts`](#email-counts-api) — Email Source Counts
27. [`GET /api/scans/<scan_id>/app-links/counts`](#app-link-counts-api) — App Link Source Counts
28. [`GET /api/scans/<scan_id>/doc-links/counts`](#doc-link-counts-api) — Doc Link Source Counts
29. [`GET /api/scans/<scan_id>/social-links/counts`](#social-link-counts-api) — Social Link Source Counts
30. [`GET /api/scans/<scan_id>/cloud-resources/counts`](#cloud-resource-counts-api) — Cloud Resource Source Counts
31. [`GET /api/scans/<scan_id>/urls/counts`](#url-counts-api) — URL Source Counts

---

## Common Patterns

### Pagination

All result list endpoints support pagination via query parameters:

| Param | Type | Default | Max | Description |
|-------|------|---------|-----|-------------|
| `page` | integer | `1` | — | Page number (1-indexed) |
| `per_page` | integer | `50` | `200` | Results per page |

**Paginated response shape:**
```json
{
  "data": [...],
  "total": 142,
  "page": 1,
  "per_page": 50,
  "total_pages": 3
}
```

### Filtering

Most result list endpoints also support these optional filter query params:

| Param | Description |
|-------|-------------|
| `base_url` | Filter by origin (e.g. `https://example.com`) — case-insensitive substring match |
| `js_file` | Filter by JS file URL — case-insensitive substring match |

### Error Responses

All endpoints return errors in this format:

- **Code:** `404 Not Found`  
  **Content:** `{"error": "Scan not found"}`

- **Code:** `400 Bad Request`  
  **Content:** `{"error": "<error message>"}`

- **Code:** `500 Internal Server Error`  
  **Content:** `{"error": "<error message>"}`

---

## System

<hr>

### <a id="health-check-api"></a>Health Check API

Returns the service health status.

- **URL:** `/api/health`
- **Method:** `GET`
- **URL Params:** None
- **Data Params:** None

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "status": "healthy",
  "timestamp": "2026-04-16T10:00:00.000000+00:00"
}
```

**Sample Call:**
```bash
curl http://localhost:3001/api/health
```

---

## Dashboard

<hr>

### <a id="dashboard-stats-api"></a>Dashboard Statistics API

Returns aggregated platform-wide statistics and the 5 most recent scans.

- **URL:** `/api/dashboard/stats`
- **Method:** `GET`
- **URL Params:** None
- **Data Params:** None

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "total_scans": 12,
  "active_scans": 1,
  "completed_scans": 9,
  "failed_scans": 2,
  "total_secrets": 47,
  "total_endpoints": 318,
  "total_subdomains": 93,
  "total_cloud_resources": 24,
  "total_storage_mb": 152.4,
  "recent_scans": [
    {
      "id": "a1b2c3d4-...",
      "name": "example_com_20260416_100000",
      "target_url": "https://example.com",
      "status": "completed",
      ...
    }
  ]
}
```

**Sample Call:**
```bash
curl http://localhost:3001/api/dashboard/stats
```

---

## Scan Management

<hr>

### <a id="list-scans-api"></a>List All Scans API

Returns all scans ordered by creation date (newest first). Running scans are enriched with live resource stats.

- **URL:** `/api/scans`
- **Method:** `GET`
- **URL Params:** None
- **Data Params:** None

**Success Response:**
- **Code:** `200`
- **Content:**
```json
[
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "example_com_20260416_100000",
    "target_url": "https://example.com",
    "description": "Production site scan",
    "status": "completed",
    "scan_type": "full",
    "created_at": "2026-04-16T10:00:00Z",
    "started_at": "2026-04-16T10:00:05Z",
    "completed_at": "2026-04-16T10:03:21Z",
    "error_message": null,
    "parallel": 3,
    "concurrency": 2,
    "depth": 1,
    "delay": 0,
    "cookie": null,
    "headers": null,
    "peak_ram_mb": 124.5,
    "storage_mb": 8.2,
    "total_urls": 5,
    "successful_urls": 5,
    "failed_urls": 0,
    "js_downloaded": 38,
    "js_failed": 2,
    "secrets_count": 4,
    "endpoints_count": 62,
    "subdomains_count": 11,
    "ips_count": 3,
    "cloud_resources_count": 7,
    "emails_count": 2,
    "app_links_count": 1,
    "doc_links_count": 5,
    "social_links_count": 3,
    "urls_count": 94,
    "files_count": 40,
    "parameters_count": 0
  }
]
```

**Sample Call:**
```bash
curl http://localhost:3001/api/scans
```

---

### <a id="create-scan-api"></a>Create a New Scan API

Creates a new scan record (does **not** start it). Use the [Start Scan API](#start-scan-api) to begin execution.

- **URL:** `/api/scans`
- **Method:** `POST`
- **Content-Type:** `application/json` or `multipart/form-data` (required for `file` scan type)

**Data Params:**

| Param Name | Param Value | Required | Applies to |
|------------|-------------|----------|------------|
| `name` | Scan label (alphanumeric, `-`, `_`; max 50 chars after sanitization) | Yes | all |
| `scan_type` | `full` \| `js_urls` \| `file` (default: `full`) | No | all |
| `target_url` | Target URL(s) for `full`/`js_urls` scans — newline-separated for multiple | Yes (for `full`/`js_urls`) | `full`, `js_urls` |
| `js_file` | `.js` file to upload — `multipart/form-data` only | Yes (for `file`) | `file` |
| `description` | Human-readable description | No | all |
| `parallel` | Max parallel processes/threads (default: `3`) | No | `full`, `js_urls` |
| `concurrency` | Crawling concurrency per process (default: `2`) | No | `full` only |
| `depth` | Crawl depth; `0` = infinite (default: `1`) | No | `full` only |
| `delay` | Delay between requests to the same domain in **seconds** (default: `0`) | No | `full` only |
| `cookie` | Cookie string (e.g. `session=abc123`) | No | `full`, `js_urls` |
| `headers` | Custom headers as JSON array (e.g. `["X-Token: abc"]`) | No | `full`, `js_urls` |

**Scan Types:**

| Type | Description |
|------|-------------|
| `full` | Crawls the target URL, discovers JS files, downloads and analyzes them |
| `js_urls` | Directly downloads and analyzes a list of JavaScript file URLs |
| `file` | Analyzes a single uploaded `.js` file — no crawling |

**Success Response:**
- **Code:** `201`
- **Content:** Scan object (see [List All Scans](#list-scans-api) for shape)

**Error Response:**
- **Code:** `400`
- **Content:** `{"error": "Name is required"}` / `{"error": "Invalid scan_type"}` / etc.

**Sample Calls:**

Full crawl scan:
```bash
curl -X POST http://localhost:3001/api/scans \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_scan",
    "scan_type": "full",
    "target_url": "https://example.com",
    "description": "Full crawl of example.com",
    "parallel": 3,
    "concurrency": 2,
    "depth": 1
  }'
```

Direct JS URLs scan:
```bash
curl -X POST http://localhost:3001/api/scans \
  -H "Content-Type: application/json" \
  -d '{
    "name": "js_scan",
    "scan_type": "js_urls",
    "target_url": "https://example.com/app.js\nhttps://example.com/vendor.js",
    "parallel": 5
  }'
```

Uploaded JS file scan:
```bash
curl -X POST http://localhost:3001/api/scans \
  -F "name=local_file_scan" \
  -F "scan_type=file" \
  -F "js_file=@/path/to/bundle.js"
```

With cookie and custom headers:
```bash
curl -X POST http://localhost:3001/api/scans \
  -H "Content-Type: application/json" \
  -d '{
    "name": "auth_scan",
    "scan_type": "full",
    "target_url": "https://app.example.com",
    "cookie": "session=eyJhbGciOiJIUzI1NiJ9...",
    "headers": "[\"Authorization: Bearer eyJhbGciOiJIUzI1NiJ9...\"]"
  }'
```

---

### <a id="get-scan-api"></a>Get Scan Details API

Returns the full details of a single scan. Running scans include live resource stats.

- **URL:** `/api/scans/<scan_id>`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Success Response:**
- **Code:** `200`
- **Content:** Full scan object (see [List All Scans](#list-scans-api) for shape)

**For a running scan, additional live fields are injected (overriding DB values):**
```json
{
  "peak_ram_mb": 87.3,
  "current_ram_mb": 64.1,
  "storage_mb": 4.2,
  "completed_urls": 3,
  "total_urls": 5,
  "js_downloaded": 21,
  "secrets_count": 2,
  "endpoints_count": 34,
  "elapsed_seconds": 48,
  "files_count": 23,
  "subdomains_count": 5
}
```

> Live fields are read from `live_stats.json` on disk (written every ~1 second by the running process). If the file doesn't exist yet, none of the live fields are injected.

**Sample Call:**
```bash
curl http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### <a id="delete-scan-api"></a>Delete a Scan API

Deletes a scan, terminates it if running, and removes all associated result files from disk.

- **URL:** `/api/scans/<scan_id>`
- **Method:** `DELETE`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Success Response:**
- **Code:** `200`
- **Content:** `{"message": "Scan deleted"}`

**Sample Call:**
```bash
curl -X DELETE http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### <a id="start-scan-api"></a>Start a Scan API

Begins execution of a previously created scan. A scan can be started from any status **except** `running` — the only guard is `{"error": "Scan is already running"}` when it is currently active.

- **URL:** `/api/scans/<scan_id>/start`
- **Method:** `POST`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Data Params:** None

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "message": "Scan started",
  "scan": { ...scan object... }
}
```

**Error Response:**
- **Code:** `400`
- **Content:** `{"error": "Scan is already running"}`

**Sample Call:**
```bash
curl -X POST http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/start
```

---

### <a id="stop-scan-api"></a>Stop a Running Scan API

Terminates a running scan. Always sets the scan's status to `failed` with `error_message: "Scan was stopped by user"` — even if the scan was not currently running.

- **URL:** `/api/scans/<scan_id>/stop`
- **Method:** `POST`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Data Params:** None

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "message": "Scan stopped",
  "scan": { ...scan object... }
}
```

**Sample Call:**
```bash
curl -X POST http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/stop
```

---

### <a id="scan-counts-api"></a>Get Scan Result Counts API

Returns item counts for every result category without fetching the full data. Useful for summary views and badges.

- **URL:** `/api/scans/<scan_id>/counts`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "secrets": 4,
  "endpoints": 62,
  "parameters": 0,
  "cloud_resources": 7,
  "subdomains": 11,
  "ips": 3,
  "files": 40,
  "emails": 2,
  "app_links": 1,
  "doc_links": 5,
  "social_links": 3,
  "urls": 94
}
```

**Sample Call:**
```bash
curl http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/counts
```

---

## Scan Results

> All result endpoints below support [pagination](#pagination) and [filtering](#filtering) unless noted otherwise.

<hr>

### <a id="secrets-api"></a>Discovered Secrets API

Returns secrets discovered during JS analysis (API keys, tokens, credentials, etc.).

- **URL:** `/api/scans/<scan_id>/secrets`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:** `page`, `per_page`, `base_url`, `js_file`

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "type": "AWS",
      "value": "AKIAIOSFODNN7EXAMPLE",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "line": 0,
      "severity": "high"
    }
  ],
  "total": 4,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

> **Field notes:**
> - `value` — the raw/redacted secret string
> - `severity` — `"high"` if the secret was verified, `"medium"` otherwise
> - `line` — line number within the JS file (0 if unavailable)

**Sample Calls:**
```bash
# All secrets for a scan
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/secrets"

# Filter by origin
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/secrets?base_url=https://api.example.com"

# Filter by specific JS file
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/secrets?js_file=vendor.js"

# Paginated
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/secrets?page=2&per_page=25"
```

---

### <a id="endpoints-api"></a>Discovered API Endpoints API

Returns API endpoints, parameters, and endpoint-with-params extracted from JavaScript source code.

- **URL:** `/api/scans/<scan_id>/endpoints`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:** `page`, `per_page`, `base_url`, `js_file`

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "url": "/api/v1/users",
      "type": "Endpoint",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "line": 0
    }
  ],
  "total": 62,
  "page": 1,
  "per_page": 50,
  "total_pages": 2
}
```

> **`type` values:**
> - `"Endpoint"` — a plain path like `/api/v1/users`
> - `"Parameter"` — a standalone query parameter
> - `"Endpoint-Param"` — a path that includes query parameters (e.g. `/search?q=`)

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/endpoints"
```

---

### <a id="parameters-api"></a>Parameters API

> **Note:** This endpoint is a placeholder. Parameter extraction is not yet implemented — it always returns an empty list. The `parameters_count` field on scans is always `0`.

- **URL:** `/api/scans/<scan_id>/parameters`
- **Method:** `GET`

**Query Params:** `page`, `per_page`

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [],
  "total": 0,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/parameters"
```

---

### <a id="cloud-resources-api"></a>Cloud Resources API

Returns cloud service URLs and bucket references (AWS S3, GCS, Azure Blob, Firebase, etc.).

- **URL:** `/api/scans/<scan_id>/cloud-resources`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:**

| Param | Description |
|-------|-------------|
| `page` | Page number |
| `per_page` | Results per page |
| `base_url` | Filter by origin |
| `js_file` | Filter by JS file |
| `source` | Filter by source — `js` or `crawl` |

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "type": "S3 Bucket",
      "url": "https://my-bucket.s3.amazonaws.com",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "source": "js",
      "line": 0
    }
  ],
  "total": 7,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

> **`type` values (mapped):** `"S3 Bucket"`, `"Google Cloud"`, `"Azure Blob"`, `"Alibaba OSS"`, `"DigitalOcean Spaces"`
>
> **`type` values (raw key — unmapped providers):** `"ibm_cos"`, `"oracle_oci"`, `"tencent_cos"`, `"backblaze_b2"`, `"wasabi"`, `"cloudflare_r2"`
>
> The parser maps 5 providers to display names; the remaining 6 fall through as their raw snake_case key.

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/cloud-resources?source=js"
```

---

### <a id="subdomains-api"></a>Subdomains API

Returns subdomains discovered during JS analysis and crawling, with HTTP reachability status.

- **URL:** `/api/scans/<scan_id>/subdomains`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:**

| Param | Description |
|-------|-------------|
| `page` | Page number |
| `per_page` | Results per page |
| `base_url` | Filter by origin |
| `js_file` | Filter by JS file |
| `status` | Filter by reachability — `active`, `inactive`, or `unknown` |

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "subdomain": "api.example.com",
      "status": "active",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "line": 0
    }
  ],
  "total": 11,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

> **`status` values:** `"active"` (DNS resolves), `"inactive"` (DNS does not resolve), `"unknown"` (DNS resolve not available or timed out)

**Sample Calls:**
```bash
# All subdomains
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/subdomains"

# Only reachable subdomains
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/subdomains?status=active"
```

---

### <a id="ips-api"></a>IP Addresses API

Returns IP addresses found in JavaScript source code.

- **URL:** `/api/scans/<scan_id>/ips`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:** `page`, `per_page`, `base_url`, `js_file`

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "ip": "192.168.1.100",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "line": 0
    }
  ],
  "total": 3,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/ips"
```

---

### <a id="emails-api"></a>Email Addresses API

Returns email addresses found in JavaScript source code or during crawling.

- **URL:** `/api/scans/<scan_id>/emails`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:**

| Param | Description |
|-------|-------------|
| `page` | Page number |
| `per_page` | Results per page |
| `base_url` | Filter by origin |
| `js_file` | Filter by JS file |
| `source` | Filter by source — `js` or `crawl` |

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "email": "support@example.com",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "source": "js",
      "line": 0
    }
  ],
  "total": 2,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/emails"
```

---

### <a id="urls-api"></a>Discovered URLs API

Returns all URLs discovered during crawling and JS analysis.

- **URL:** `/api/scans/<scan_id>/urls`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:**

| Param | Description |
|-------|-------------|
| `page` | Page number |
| `per_page` | Results per page |
| `base_url` | Filter by origin |
| `js_file` | Filter by JS file |
| `source` | Filter by source — `js` or `crawl` |

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "url": "https://api.example.com/v1/products",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "source": "js",
      "line": 0
    }
  ],
  "total": 94,
  "page": 1,
  "per_page": 50,
  "total_pages": 2
}
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/urls?source=crawl&page=1&per_page=100"
```

---

### <a id="app-links-api"></a>App Store Links API

Returns links to mobile app store listings (Google Play, Apple App Store, etc.) found in JS files.

- **URL:** `/api/scans/<scan_id>/app-links`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:** `page`, `per_page`, `base_url`, `js_file`, `source` (`js` or `crawl`)

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "type": "Play Store",
      "url": "https://play.google.com/store/apps/details?id=com.example.app",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "source": "js",
      "line": 0
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

> **`type` values:** `"Play Store"`, `"App Store"`

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/app-links"
```

---

### <a id="doc-links-api"></a>Documentation Links API

Returns links to documentation sites (Swagger, ReadMe, GitBook, etc.) found in JS files.

- **URL:** `/api/scans/<scan_id>/doc-links`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:** `page`, `per_page`, `base_url`, `js_file`, `source` (`js` or `crawl`)

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "url": "https://docs.example.com/api",
      "type": "google_docs",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "source": "js",
      "line": 0
    }
  ],
  "total": 5,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

> **`type` values:** `"google_docs"`, `"mediafire"`, `"dropbox"`, `"onedrive_sharepoint"`, `"zoho"`, `"mega"`
>
> These are the raw service keys written by the extractor. The `"Documentation"` fallback in the parser is never reached because the extractor always writes a `type` key.

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/doc-links"
```

---

### <a id="social-links-api"></a>Social Media Links API

Returns social media profile links (Twitter/X, LinkedIn, GitHub, etc.) discovered during the scan.

- **URL:** `/api/scans/<scan_id>/social-links`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:** `page`, `per_page`, `base_url`, `js_file`, `source` (`js` or `crawl`)

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "type": "Twitter/X",
      "url": "https://twitter.com/example",
      "file": "https://example.com/app.js",
      "base": "https://example.com",
      "source": "js",
      "line": 0
    }
  ],
  "total": 3,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

> **`type` values:** `"Facebook"`, `"Instagram"`, `"Twitter/X"`, `"LinkedIn"`, `"YouTube"`, `"TikTok"`, `"Pinterest"`, `"Reddit"`, `"Snapchat"`, `"Telegram"`, `"WhatsApp"`, `"Discord"`, `"GitHub"`, `"Medium"`, `"Tumblr"`, `"Twitch"`, `"Vimeo"`

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/social-links"
```

---

### <a id="files-api"></a>Downloaded JS Files API

Returns a list of all JavaScript files downloaded during the scan.

- **URL:** `/api/scans/<scan_id>/files`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:** `page`, `per_page`, `base_url`, `js_file`

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "filename": "https://example.com/static/js/app.abc123.js",
      "url": "https://example.com/static/js/app.abc123.js",
      "baseUrl": "https://example.com",
      "size": "240.0 KB",
      "type": "JavaScript",
      "downloaded": true
    }
  ],
  "total": 40,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

> **Field notes:**
> - `baseUrl` — origin the JS was downloaded from (not `base`)
> - `size` — human-readable string: `"240.0 KB"` or `"512 B"` (not a raw byte count)
> - `type` — always `"JavaScript"`
> - `downloaded` — always `true` for successfully downloaded files

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/files"
```

---

### <a id="file-content-api"></a>Get JS File Content API

Returns the raw source content of a specific downloaded JavaScript file.

- **URL:** `/api/scans/<scan_id>/files/<file_path>`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |
| `file_path` | URL-encoded original JS file URL or filename | Yes |

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "content": "!function(e){var t={};function n(r){if(t[r])return t[r].exports...",
  "filename": "app.abc123.js",
  "url": "https://example.com/static/js/app.abc123.js",
  "size": 245760
}
```

**Error Responses:**
- **Code:** `400` — `{"error": "Invalid file path"}` (path traversal attempt blocked)
- **Code:** `404` — `{"error": "File not found"}`

> **Matching logic:** The route accepts three forms of `file_path` and resolves them in order:
> 1. The safe/encoded filename on disk (e.g. `app.abc123.js`)
> 2. The raw filename on disk
> 3. The original JS URL (looked up via `url_map.json`)

**Sample Calls:**
```bash
# By original JS URL (URL-encoded)
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/files/https%3A%2F%2Fexample.com%2Fstatic%2Fjs%2Fapp.abc123.js"

# By filename as returned in the /files list
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/files/app.abc123.js"
```

---

### <a id="input-urls-api"></a>Input URLs API

Returns the original list of target URLs that were provided when the scan was created.

- **URL:** `/api/scans/<scan_id>/input-urls`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "urls": [
    "https://example.com",
    "https://app.example.com"
  ],
  "total": 2
}
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/input-urls"
```

---

### <a id="failed-downloads-api"></a>Failed Downloads API

Returns a paginated list of JavaScript files that failed to download during the scan, along with the error reason.

- **URL:** `/api/scans/<scan_id>/failed-downloads`
- **Method:** `GET`

**URL Params:**

| Param Name | Param Value | Required |
|------------|-------------|----------|
| `scan_id` | UUID of the scan | Yes |

**Query Params:** `page`, `per_page`, `base_url`, `js_file`

**Success Response:**
- **Code:** `200`
- **Content:**
```json
{
  "data": [
    {
      "id": 1,
      "js_url": "https://example.com/static/js/chunk.abc.js",
      "error": "Connection timeout",
      "baseUrl": "https://example.com"
    }
  ],
  "total": 2,
  "page": 1,
  "per_page": 50,
  "total_pages": 1
}
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/failed-downloads"
```

---

## Count Sub-Resources

These endpoints return source breakdown counts (`js` vs `crawl`) without the full paginated payload.

<hr>

### <a id="subdomain-counts-api"></a>Subdomain Status Counts API

- **URL:** `/api/scans/<scan_id>/subdomains/counts`
- **Method:** `GET`

**Success Response:**
```json
{
  "active": 7,
  "inactive": 2,
  "unknown": 2,
  "total": 11
}
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/subdomains/counts"
```

---

### <a id="email-counts-api"></a>Email Source Counts API

- **URL:** `/api/scans/<scan_id>/emails/counts`
- **Method:** `GET`

**Success Response:**
```json
{ "crawl": 1, "js": 1, "total": 2 }
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/emails/counts"
```

---

### <a id="app-link-counts-api"></a>App Link Source Counts API

- **URL:** `/api/scans/<scan_id>/app-links/counts`
- **Method:** `GET`

**Success Response:**
```json
{ "crawl": 0, "js": 1, "total": 1 }
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/app-links/counts"
```

---

### <a id="doc-link-counts-api"></a>Doc Link Source Counts API

- **URL:** `/api/scans/<scan_id>/doc-links/counts`
- **Method:** `GET`

**Success Response:**
```json
{ "crawl": 2, "js": 3, "total": 5 }
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/doc-links/counts"
```

---

### <a id="social-link-counts-api"></a>Social Link Source Counts API

- **URL:** `/api/scans/<scan_id>/social-links/counts`
- **Method:** `GET`

**Success Response:**
```json
{ "crawl": 1, "js": 2, "total": 3 }
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/social-links/counts"
```

---

### <a id="cloud-resource-counts-api"></a>Cloud Resource Source Counts API

- **URL:** `/api/scans/<scan_id>/cloud-resources/counts`
- **Method:** `GET`

**Success Response:**
```json
{ "crawl": 1, "js": 6, "total": 7 }
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/cloud-resources/counts"
```

---

### <a id="url-counts-api"></a>URL Source Counts API

- **URL:** `/api/scans/<scan_id>/urls/counts`
- **Method:** `GET`

**Success Response:**
```json
{ "crawl": 33, "js": 61, "total": 94 }
```

**Sample Call:**
```bash
curl "http://localhost:3001/api/scans/a1b2c3d4-e5f6-7890-abcd-ef1234567890/urls/counts"
```

---

## Scan Lifecycle Example

Below is a complete end-to-end workflow using the API:

```bash
BASE=http://localhost:3001

# 1. Create a full crawl scan
SCAN=$(curl -s -X POST $BASE/api/scans \
  -H "Content-Type: application/json" \
  -d '{"name":"demo","scan_type":"full","target_url":"https://example.com","depth":1}')

SCAN_ID=$(echo $SCAN | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Created scan: $SCAN_ID"

# 2. Start the scan
curl -s -X POST $BASE/api/scans/$SCAN_ID/start

# 3. Poll status until complete
while true; do
  STATUS=$(curl -s $BASE/api/scans/$SCAN_ID | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])")
  echo "Status: $STATUS"
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 5
done

# 4. Fetch results
curl -s "$BASE/api/scans/$SCAN_ID/counts"
curl -s "$BASE/api/scans/$SCAN_ID/secrets"
curl -s "$BASE/api/scans/$SCAN_ID/endpoints?per_page=100"
curl -s "$BASE/api/scans/$SCAN_ID/subdomains?status=active"
curl -s "$BASE/api/scans/$SCAN_ID/cloud-resources"

# 5. Clean up
curl -s -X DELETE $BASE/api/scans/$SCAN_ID
```

---

## Scan Object Reference

Full shape of a scan object returned by the API:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Unique scan identifier |
| `name` | string | Auto-generated name: `<input>_YYYYMMDD_HHMMSS` |
| `target_url` | string | Input URL(s) or uploaded filename |
| `description` | string \| null | Optional description |
| `status` | string | `pending` \| `running` \| `completed` \| `failed` |
| `scan_type` | string | `full` \| `js_urls` \| `file` |
| `created_at` | ISO 8601 string | When the scan record was created |
| `started_at` | ISO 8601 string \| null | When execution began |
| `completed_at` | ISO 8601 string \| null | When execution finished |
| `error_message` | string \| null | Error detail if `status` is `failed` |
| `parallel` | integer | Max parallel processes (`full`/`js_urls`); stored but unused for `file` |
| `concurrency` | integer | Crawling concurrency per process (`full` only) |
| `depth` | integer | Crawl depth; `0` = infinite (`full` only) |
| `delay` | integer | Inter-request delay in **seconds** (`full` only) |
| `cookie` | string \| null | Cookie string sent with requests |
| `headers` | string \| null | JSON array of custom headers |
| `peak_ram_mb` | float | Peak RAM usage in MB |
| `storage_mb` | float | Disk usage of scan data in MB |
| `total_urls` | integer | Total input URLs processed |
| `successful_urls` | integer | URLs crawled successfully |
| `failed_urls` | integer | URLs that failed to crawl |
| `js_downloaded` | integer | JS files successfully downloaded |
| `js_failed` | integer | JS files that failed to download |
| `secrets_count` | integer | Number of secrets found |
| `endpoints_count` | integer | Number of API endpoints found |
| `subdomains_count` | integer | Number of subdomains discovered |
| `ips_count` | integer | Number of IP addresses found |
| `cloud_resources_count` | integer | Number of cloud resources found |
| `emails_count` | integer | Number of emails found |
| `app_links_count` | integer | Number of app store links found |
| `doc_links_count` | integer | Number of documentation links found |
| `social_links_count` | integer | Number of social media links found |
| `urls_count` | integer | Number of URLs discovered |
| `files_count` | integer | Total JS files (downloaded + failed) |
| `parameters_count` | integer | Always `0` — parameter extraction is not yet implemented |
