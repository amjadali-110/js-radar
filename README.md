# JS Radar — JavaScript Security Analysis Platform

<img width="1267" height="464" alt="Screenshot 2026-04-08 151543" src="https://github.com/user-attachments/assets/02d1d64c-93eb-4a74-a860-4065e07b2ee2" />

A self-hosted cross platform framework that crawls websites, downloads JavaScript files, and automatically extracts security-relevant intelligence: secrets, API endpoints, subdomains, cloud resources, IPs, emails, and more.

Built by **[Amjad Ali](https://www.linkedin.com/in/amjadali110/)**.

---

## What It Does

JS Radar takes a target URL, crawls the site, downloads every JavaScript file it finds, and runs a suite of extractors over the content. Results are stored in a SQLite database and surfaced through a REST API with a React dashboard.

**Extracted intelligence:**

| Category | Details |
|---|---|
| Secrets | API keys, tokens, credentials |
| API Endpoints | Paths, query parameters, endpoint+param combos |
| Subdomains | With live DNS reachability status (`active` / `inactive` / `unknown`) |
| Cloud Resources | S3, GCS, Azure Blob, Alibaba OSS, DigitalOcean, Cloudflare R2, IBM, Oracle, Tencent, Backblaze, Wasabi |
| IP Addresses | Hardcoded IPs found in JS source |
| Emails | Addresses from JS files and crawl output |
| URLs | All URLs discovered during crawl and JS analysis |
| App Store Links | Google Play / Apple App Store links |
| Documentation Links | Google Docs, Dropbox, OneDrive/SharePoint, MediaFire, Zoho, MEGA |
| Social Media Links | Twitter/X, LinkedIn, GitHub, Facebook, Instagram, and 12 more |
| Downloaded JS Files | Full source accessible via API |

---

## Quick Start

### Linux / macOS / Kali

```bash
chmod +x run.sh
./run.sh
```

The script auto-detects your OS and architecture, downloads and installs all required dependencies, creates a Python venv, builds the frontend, and starts both services.

**Requirements:** Python 3.8+, Node.js + npm, `curl`, `unzip`, `tar`

### Windows

```powershell
powershell -ep bypass
.\run.ps1
```

**Requirements:** Python 3.8+, Node.js + npm in PATH, Windows 10+ (for native `tar`)

### Android / Termux

```bash
chmod +x termux-run.sh
./termux-run.sh
```

Termux mode compiles all external dependencies, and uses `waitress` instead of gunicorn. Python and Node.js are auto-installed via `pkg` if missing.

> **Note:** `psutil` may fail to install on Termux — this is expected. RAM metrics will show as `0`; all other functionality works normally.

### Docker

```bash
docker compose up
```

Starts backend on `:3001` and frontend on `:3000`. Scanner binaries are downloaded automatically during the image build. Scan data is persisted via volume mounts to `./data/scans` and `./backend/instance`. The frontend container waits for the backend to pass its health check before starting.

---

Once running, open **http://localhost:3000** for the dashboard.  
The backend API is available at **http://localhost:3001**.

<img width="1908" height="1080" alt="image" src="https://github.com/user-attachments/assets/41c5f62c-d380-4950-8052-3a8b50690316" />

<img width="1897" height="1080" alt="image" src="https://github.com/user-attachments/assets/dc35d964-6bc5-4c5d-87df-bb1f44a687cc" />

<img width="1905" height="1080" alt="image" src="https://github.com/user-attachments/assets/44b51d6a-0c27-44c7-b7ac-890fefd2dbfb" />

---

## Scan Types

| Type | Description |
|---|---|
| `full` | Crawl target URL → discover JS files → download → analyze |
| `js_urls` | Provide a list of JS file URLs directly → download → analyze |
| `file` | Upload a single `.js` file → analyze (no crawling) |

<img width="1906" height="1080" alt="image" src="https://github.com/user-attachments/assets/bfcd3151-62a3-4308-9e52-4f1eb14ae2d9" />

---

## Scan Options

| Option | Default | Description |
|---|---|---|
| `parallel` | `3` | Max parallel download/analysis processes |
| `concurrency` | `2` | Crawling concurrency per process (`full` only) |
| `depth` | `1` | Crawl depth; `0` = infinite (`full` only) |
| `delay` | `0` | Seconds between requests to the same domain |
| `cookie` | — | Cookie string passed with all requests |
| `headers` | — | JSON array of custom request headers |

---

## Scan Lifecycle

```
pending  →  running  →  completed
                    ↘  failed
```

- **`pending`** — created, not yet started
- **`running`** — actively scanning; live stats updated every ~1 second
- **`completed`** — finished successfully
- **`failed`** — errored out, or stopped manually by user

Any scan that is not currently `running` can be re-started. Stopping a scan always transitions it to `failed`.

---

## Troubleshooting

**Backend fails to start**
```bash
lsof -i :3001            # check if port is already in use
rm -rf backend/venv && ./run.sh   # recreate the virtual environment
```

**Frontend build fails**
```bash
cd frontend && rm -rf node_modules && npm install && npm run build
```

**Scanner binaries missing**
```bash
rm -rf scanner/bin && ./run.sh   # re-download all binaries
```

---

## Architecture

```
js-discovery/
├── run.sh              # Linux / macOS startup script (auto-installs deps)
├── run.ps1             # Windows startup script (PowerShell)
├── termux-run.sh       # Android / Termux startup script
├── docker-compose.yml  # Docker deployment
│
├── backend/            # Flask REST API (Python)
│   ├── app.py          # App factory
│   ├── config.py       # Configuration
│   ├── models/         # SQLAlchemy models
│   ├── routes/         # API blueprints
│   ├── services/       # Scanner orchestration, result parsing
│   └── utils/          # Shared helpers
│
├── scanner/            # Core scanning engine (Python)
│   ├── js_scanner.py           # Main scanner CLI
│   ├── js_info_extractor.py    # Extracts IPs, emails, domains, cloud refs, links
│   ├── endpoint_extractor.py   # Extracts API endpoints and parameters
│   └── bin/                    # Auto-downloaded scanner binaries
│
├── frontend/           # React 18 dashboard
│   └── src/
│       ├── components/ # Reusable UI components
│       ├── pages/      # Dashboard, scan list, scan detail views
│       └── services/   # API client (Axios)
│
├── data/scans/         # Runtime scan output (gitignored)
└── docs/               # Documentation
    └── API_DOC.md      # Full REST API reference
```

**Tech stack:**

| Layer | Stack |
|---|---|
| Backend | Python 3.8+, Flask 3, SQLAlchemy, SQLite, Gunicorn / Waitress |
| Frontend | React 18, Tailwind CSS, Recharts, Axios |
| Scanner | Python, crawler, secrets, DNS |
| Container | Docker + Docker Compose |

---


## External Scanner Dependencies

Startup scripts automatically download the correct binary for your platform into `scanner/bin/`:

| Tool | Purpose |
|---|---|
| [gospider](https://github.com/jaeles-project/gospider) | Web crawler — discovers JS file URLs |
| [TruffleHog](https://github.com/trufflesecurity/trufflehog) | Secret detection in JS source |
| [dnsx](https://github.com/projectdiscovery/dnsx) | DNS resolution for subdomain reachability |

---

## Data Storage

Scan results are stored in two places:

- **SQLite database** — `backend/instance/js_discovery.db` — scan metadata and all extracted results
- **File system** — `data/scans/<scan_name>/` — raw JS files, extractor output, live progress stats

```
data/scans/<scan_name>/
├── downloaded-js/           # Raw JS files organized by origin
│   └── <origin>/
│       ├── <js_files>
│       ├── url_map.json     # Maps safe filenames back to original URLs
│       └── failed_downloads.json
├── js-extracted/            # Extractor JSON output per origin
│   └── <origin>/
│       ├── summary.json         # Always written — totals for this origin
│       ├── urls.json            # (written only when data found)
│       ├── domains.json
│       ├── emails.json
│       ├── ip_addresses.json
│       ├── cloud_buckets.json
│       ├── doc_links.json
│       ├── app_links.json
│       ├── social_links.json
│       ├── crawl_urls.json
│       ├── crawl_emails.json
│       ├── crawl_social_links.json
│       ├── crawl_app_links.json
│       ├── crawl_doc_links.json
│       └── crawl_cloud_buckets.json
├── js-endpoints/            # API endpoint extractor output per origin
│   └── <origin>/
│       └── endpoints.json
├── secrets/                 # Secret scanning raw output
│   └── <origin>/
│       └── secrets.json     # One JSON object per line, each a discovered secret
├── spider_output/           # Raw crawling output
├── failed_js_downloads.json # Top-level summary of all failed JS downloads
├── live_stats.json          # Real-time progress (updated every ~1s while running)
├── scan_info.txt            # Scan metadata
└── scan_report.txt          # Summary report
```
---

## API Documentation

For the full REST API reference — all 31 endpoints with request/response schemas, query parameters, field notes, and curl examples — see: **[docs/API_DOC.md](docs/API_DOC.md)**

