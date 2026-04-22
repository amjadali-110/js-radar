"""
Scan API routes - /api/scans/*
"""

import re
import os
import json
import shutil
import threading
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse
from flask import Blueprint, request, jsonify, current_app
from backend.extensions import db, limiter
from backend.models.scan import Scan
from werkzeug.utils import secure_filename
from backend.services.scanner import (
    active_scans,
    run_scan_async,
    run_js_urls_scan_async,
    run_uploaded_file_scan_async,
)
from backend.services.parser import get_scan_directory, parse_scan_results, read_live_stats
from backend.utils.filename import safe_filename_to_url, safe_dirname_to_url
from backend.utils.url_validator import validate_urls

scans_bp = Blueprint('scans', __name__)


def _long_path(p):
    """On Windows, prefix path with \\\\?\\ to bypass the 260-char MAX_PATH limit."""
    s = str(p)
    if os.name == 'nt' and not s.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(s)
    return s


def paginate_list(items, page, per_page):
    """Paginate a list of items and return paginated response dict."""
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return {
        'data': items[start:end],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages
    }


def get_pagination_params():
    """Extract page and per_page from query params with defaults."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 200)  # cap max per page
    return max(1, page), max(1, per_page)


def get_filter_params():
    """Extract base_url and js_file filter params from query string."""
    base_url = request.args.get('base_url', '', type=str).strip().lower()
    js_file = request.args.get('js_file', '', type=str).strip().lower()
    return base_url, js_file


def _extract_base_url(url):
    """Extract base URL (scheme + host) from a full URL."""
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        pass
    match = re.match(r'^(https?://[^/]+)', url or '')
    return match.group(1) if match else ''


def filter_items(items, base_url_filter, js_file_filter, file_field='file'):
    """Filter items by base_url and js_file before pagination."""
    if not base_url_filter and not js_file_filter:
        return items

    filtered = []
    for item in items:
        item_file = item.get(file_field, '') or item.get('url', '') or ''
        item_base_url = item.get('base', '') or item.get('baseUrl', '') or _extract_base_url(item_file) or ''

        if base_url_filter and base_url_filter not in item_base_url.lower():
            continue
        if js_file_filter and js_file_filter not in item_file.lower():
            continue
        filtered.append(item)

    return filtered


def _count_failed_downloads(scan_dir):
    """Count total failed JS downloads from failed_downloads.json files"""
    failed_count = 0
    downloaded_js_dir = scan_dir / 'downloaded-js'
    if downloaded_js_dir.exists():
        for subdir in downloaded_js_dir.iterdir():
            if subdir.is_dir():
                failed_file = subdir / 'failed_downloads.json'
                if failed_file.exists():
                    try:
                        with open(_long_path(failed_file), 'r') as f:
                            data = json.load(f)
                        failed_count += len(data.get('failures', []))
                    except Exception:
                        pass
    return failed_count


def _enrich_with_live_stats(scan_dict, scan_name):
    """Inject live resource stats for a running scan"""
    scan_dir = get_scan_directory(scan_name)
    live = read_live_stats(scan_dir)
    if live:
        scan_dict['peak_ram_mb'] = live.get('peak_ram_mb', 0)
        scan_dict['current_ram_mb'] = live.get('current_ram_mb', 0)
        scan_dict['storage_mb'] = live.get('storage_mb', 0)
        scan_dict['completed_urls'] = live.get('completed_urls', 0)
        scan_dict['total_urls'] = live.get('total_urls', 0)
        scan_dict['js_downloaded'] = live.get('js_downloaded', 0)
        scan_dict['secrets_count'] = live.get('secrets_found', 0)
        scan_dict['endpoints_count'] = live.get('endpoints_found', 0)
        scan_dict['elapsed_seconds'] = live.get('elapsed_seconds', 0)
        scan_dict['files_count'] = live.get('js_downloaded', 0) + live.get('js_failed', 0)
        # Parse current results from disk for subdomains count
        results = parse_scan_results(scan_dir)
        scan_dict['subdomains_count'] = len(results.get('subdomains', []))
    return scan_dict


@scans_bp.route('/api/scans', methods=['GET'])
def get_scans():
    """Get all scans"""
    scans = Scan.query.order_by(Scan.created_at.desc()).all()
    result = []
    for scan in scans:
        d = scan.to_dict()
        if scan.status == 'running':
            _enrich_with_live_stats(d, scan.name)
        else:
            # Add failed downloads to files_count (DB stores only downloaded count)
            scan_dir = get_scan_directory(scan.name)
            d['files_count'] = (d.get('files_count', 0) or 0) + _count_failed_downloads(scan_dir)
        result.append(d)
    return jsonify(result)


@scans_bp.route('/api/scans', methods=['POST'])
@limiter.limit(lambda: current_app.config.get('RATELIMIT_SCAN_CREATE', '10 per minute'))
def create_scan():
    """Create a new scan"""
    is_multipart = request.content_type and 'multipart/form-data' in request.content_type
    data = request.form if is_multipart else (request.json or {})
    scan_type = (data.get('scan_type') or 'full').strip().lower()
    if scan_type not in {'full', 'js_urls', 'file'}:
        return jsonify({'error': 'Invalid scan_type'}), 400

    if not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400
    if scan_type in {'full', 'js_urls'} and not data.get('target_url'):
        return jsonify({'error': 'Name and target_url are required'}), 400

    # --- Numeric parameter bounds (server-side enforcement) ---
    cfg = current_app.config
    try:
        parallel = max(1, min(int(data.get('parallel', 3)), cfg.get('MAX_PARALLEL', 20)))
        concurrency = max(1, min(int(data.get('concurrency', 2)), cfg.get('MAX_CONCURRENCY', 10)))
        depth = max(1, min(int(data.get('depth', 1)), cfg.get('MAX_DEPTH', 5)))
        delay = max(0, min(int(data.get('delay', 0)), cfg.get('MAX_DELAY', 30)))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid numeric parameter value'}), 400

    # --- SSRF protection: validate all user-supplied URLs ---
    if scan_type in {'full', 'js_urls'}:
        raw_target = (data.get('target_url') or '').strip()
        candidate_urls = [u.strip() for u in raw_target.split('\n') if u.strip()]
        if not candidate_urls:
            return jsonify({'error': 'At least one URL is required'}), 400

        ok, err = validate_urls(candidate_urls)
        if not ok:
            return jsonify({'error': f'SSRF protection: {err}'}), 400

    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', str(data['name']))[:50]
    safe_name = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    target_value = (data.get('target_url') or '').strip()

    if scan_type == 'file':
        uploaded_file = request.files.get('js_file')
        if not uploaded_file or not uploaded_file.filename:
            return jsonify({'error': 'JavaScript file is required for file scan type'}), 400
        if not uploaded_file.filename.lower().endswith('.js'):
            return jsonify({'error': 'Only .js files are allowed'}), 400

        target_value = secure_filename(uploaded_file.filename) or 'uploaded.js'
        scan_dir = get_scan_directory(safe_name)
        upload_dir = scan_dir / 'downloaded-js' / 'uploaded_file'
        os.makedirs(_long_path(upload_dir), exist_ok=True)
        uploaded_file.save(_long_path(upload_dir / target_value))

    # --- Header format validation ---
    # Accept headers either as a JSON-encoded string ("[\"..\"]") or a raw list.
    raw_headers_input = data.get('headers') or None
    if isinstance(raw_headers_input, list):
        header_list_raw = raw_headers_input
        raw_headers = json.dumps(raw_headers_input)  # normalise to string for DB storage
    elif isinstance(raw_headers_input, str):
        raw_headers = raw_headers_input.strip() or None
        header_list_raw = None
    else:
        raw_headers = None
        header_list_raw = None

    if raw_headers:
        try:
            if header_list_raw is None:
                header_list_raw = json.loads(raw_headers)
            if not isinstance(header_list_raw, list):
                return jsonify({'error': 'headers must be a JSON array of strings'}), 400
            for h in header_list_raw:
                if not isinstance(h, str):
                    return jsonify({'error': 'Each header must be a string'}), 400
                if '\n' in h or '\r' in h or '\x00' in h:
                    return jsonify({'error': 'Header values must not contain newlines or null bytes'}), 400
                if h.strip().startswith('-'):
                    return jsonify({'error': f"Invalid header: '{h}'. Header names must not start with '-'"}), 400
                if not re.match(r"^[A-Za-z0-9!#$%&'*+\-.^_`|~][\w\-]*\s*:\s*.+$", h.strip()):
                    return jsonify({'error': f"Invalid header format: '{h}'. Expected 'Name: Value'"}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'headers must be valid JSON'}), 400

    scan = Scan(
        name=safe_name,
        target_url=target_value,
        description=str(data.get('description') or '')[:1000],
        parallel=parallel,
        concurrency=concurrency,
        depth=depth,
        delay=delay,
        cookie=(data.get('cookie') or '').strip() or None,
        headers=raw_headers,
        scan_type=scan_type,
    )

    db.session.add(scan)
    db.session.commit()

    return jsonify(scan.to_dict()), 201


@scans_bp.route('/api/scans/<scan_id>', methods=['GET'])
def get_scan(scan_id):
    """Get a specific scan"""
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    d = scan.to_dict()
    if scan.status == 'running':
        _enrich_with_live_stats(d, scan.name)
    else:
        # Add failed downloads to files_count (DB stores only downloaded count)
        scan_dir = get_scan_directory(scan.name)
        d['files_count'] = (d.get('files_count', 0) or 0) + _count_failed_downloads(scan_dir)
    return jsonify(d)


@scans_bp.route('/api/scans/<scan_id>/counts', methods=['GET'])
def get_scan_counts(scan_id):
    """Get result counts for a scan without returning full data"""
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)

    return jsonify({
        'secrets': len(results.get('secrets', [])),
        'endpoints': len(results.get('endpoints', [])),
        'parameters': 0,
        'cloud_resources': len(results.get('cloud_resources', [])),
        'subdomains': len(results.get('subdomains', [])),
        'ips': len(results.get('ips', [])),
        'files': len(results.get('files', [])) + _count_failed_downloads(scan_dir),
        'emails': len(results.get('emails', [])),
        'app_links': len(results.get('app_links', [])),
        'doc_links': len(results.get('doc_links', [])),
        'social_links': len(results.get('social_links', [])),
        'urls': len(results.get('urls', [])),
    })


@scans_bp.route('/api/scans/<scan_id>', methods=['DELETE'])
def delete_scan(scan_id):
    """Delete a scan"""
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404

    proc = active_scans.pop(scan_id, None)
    if proc:
        proc.terminate()

    scan_dir = get_scan_directory(scan.name)
    if scan_dir.exists():
        shutil.rmtree(_long_path(scan_dir), ignore_errors=True)

    db.session.delete(scan)
    db.session.commit()

    return jsonify({'message': 'Scan deleted'})


@scans_bp.route('/api/scans/<scan_id>/start', methods=['POST'])
@limiter.limit(lambda: current_app.config.get('RATELIMIT_SCAN_CREATE', '10 per minute'))
def start_scan(scan_id):
    """Start a scan"""
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404

    if scan.status == 'running':
        return jsonify({'error': 'Scan is already running'}), 400

    scan_type = scan.scan_type or 'full'
    app = current_app._get_current_object()
    if scan_type == 'full':
        target_urls = [url.strip() for url in scan.target_url.split('\n') if url.strip()]
        if not target_urls:
            return jsonify({'error': 'No valid URLs to scan'}), 400
        thread = threading.Thread(
            target=run_scan_async,
            args=(app, scan_id, scan.name, target_urls),
            kwargs={'cookie': scan.cookie, 'headers': scan.headers, 'depth': scan.depth, 'delay': scan.delay}
        )
    elif scan_type == 'js_urls':
        js_urls = [url.strip() for url in scan.target_url.split('\n') if url.strip()]
        if not js_urls:
            return jsonify({'error': 'No valid JavaScript URLs to analyze'}), 400
        thread = threading.Thread(
            target=run_js_urls_scan_async,
            args=(app, scan_id, scan.name, js_urls),
            kwargs={'cookie': scan.cookie, 'headers': scan.headers, 'parallel': scan.parallel}
        )
    else:
        scan_dir = get_scan_directory(scan.name)
        uploaded_dir = scan_dir / 'downloaded-js' / 'uploaded_file'
        has_js_file = uploaded_dir.exists() and any(uploaded_dir.glob('*.js'))
        if not has_js_file:
            return jsonify({'error': 'Uploaded JavaScript file not found'}), 400
        thread = threading.Thread(
            target=run_uploaded_file_scan_async,
            args=(app, scan_id, scan.name),
        )

    thread.daemon = True
    thread.start()

    return jsonify({'message': 'Scan started', 'scan': scan.to_dict()})


@scans_bp.route('/api/scans/<scan_id>/stop', methods=['POST'])
def stop_scan(scan_id):
    """Stop a running scan"""
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404

    proc = active_scans.pop(scan_id, None)
    if proc:
        proc.terminate()

    scan.status = 'failed'
    scan.error_message = 'Scan was stopped by user'
    scan.completed_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'message': 'Scan stopped', 'scan': scan.to_dict()})


@scans_bp.route('/api/scans/<scan_id>/input-urls', methods=['GET'])
def get_input_urls(scan_id):
    """Get the input URLs used for a scan"""
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404

    scan_dir = get_scan_directory(scan.name)
    input_urls_file = scan_dir / 'input_urls.txt'

    urls = []
    if input_urls_file.exists():
        with open(_long_path(input_urls_file), 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
    else:
        # Fallback: parse from target_url field in DB
        urls = [u.strip() for u in scan.target_url.split('\n') if u.strip()]

    return jsonify({'urls': urls, 'total': len(urls)})


@scans_bp.route('/api/scans/<scan_id>/failed-downloads', methods=['GET'])
def get_failed_downloads(scan_id):
    """Get failed JS downloads for a scan"""
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404

    scan_dir = get_scan_directory(scan.name)
    failed_items = []
    failed_id = 1

    # Read per-target failed_downloads.json files
    downloaded_js_dir = scan_dir / 'downloaded-js'
    if downloaded_js_dir.exists():
        for subdir in downloaded_js_dir.iterdir():
            if subdir.is_dir():
                failed_file = subdir / 'failed_downloads.json'
                if failed_file.exists():
                    try:
                        with open(_long_path(failed_file), 'r') as f:
                            data = json.load(f)
                        base_url = safe_dirname_to_url(subdir.name)
                        for failure in data.get('failures', []):
                            failed_items.append({
                                'id': failed_id,
                                'js_url': failure.get('js_url', ''),
                                'error': failure.get('error', ''),
                                'baseUrl': base_url
                            })
                            failed_id += 1
                    except Exception:
                        pass

    # Apply filters
    base_url_filter = request.args.get('base_url', '', type=str).strip().lower()
    js_file_filter = request.args.get('js_file', '', type=str).strip().lower()
    if base_url_filter or js_file_filter:
        filtered = []
        for item in failed_items:
            if base_url_filter and base_url_filter not in (item.get('baseUrl', '') or '').lower():
                continue
            if js_file_filter and js_file_filter not in (item.get('js_url', '') or '').lower():
                continue
            filtered.append(item)
        failed_items = filtered

    page, per_page = get_pagination_params()
    return jsonify(paginate_list(failed_items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/secrets', methods=['GET'])
def get_secrets(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    items = filter_items(results.get('secrets', []), base_url, js_file)
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/endpoints', methods=['GET'])
def get_endpoints(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    items = filter_items(results.get('endpoints', []), base_url, js_file)
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/parameters', methods=['GET'])
def get_parameters(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    page, per_page = get_pagination_params()
    return jsonify(paginate_list([], page, per_page))


@scans_bp.route('/api/scans/<scan_id>/cloud-resources', methods=['GET'])
def get_cloud_resources(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    source_filter = request.args.get('source', '', type=str).strip().lower()
    items = filter_items(results.get('cloud_resources', []), base_url, js_file)
    if source_filter:
        items = [item for item in items if item.get('source', 'js') == source_filter]
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/subdomains', methods=['GET'])
def get_subdomains(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    status_filter = request.args.get('status', '', type=str).strip().lower()
    items = filter_items(results.get('subdomains', []), base_url, js_file)
    if status_filter:
        items = [item for item in items if item.get('status', 'unknown') == status_filter]
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/subdomains/counts', methods=['GET'])
def get_subdomain_counts(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    items = results.get('subdomains', [])
    counts = {'active': 0, 'inactive': 0, 'unknown': 0, 'total': len(items)}
    for item in items:
        status = item.get('status', 'unknown')
        if status in ('active', 'inactive', 'unknown'):
            counts[status] += 1
        else:
            counts['unknown'] += 1
    return jsonify(counts)


@scans_bp.route('/api/scans/<scan_id>/ips', methods=['GET'])
def get_ips(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    items = filter_items(results.get('ips', []), base_url, js_file)
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/files', methods=['GET'])
def get_files(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    items = filter_items(results.get('files', []), base_url, js_file, file_field='url')
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/files/<path:file_path>', methods=['GET'])
def get_file_content(scan_id, file_path):
    """Get the content of a specific downloaded JS file"""
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404

    file_path = unquote(file_path)

    if '..' in file_path or file_path.startswith('/'):
        return jsonify({'error': 'Invalid file path'}), 400

    scan_dir = get_scan_directory(scan.name)
    downloaded_js_dir = scan_dir / 'downloaded-js'

    target_file = None
    if downloaded_js_dir.exists():
        # Load url_map for matching original URLs
        url_map = {}
        for subdir in downloaded_js_dir.iterdir():
            if subdir.is_dir():
                map_file = subdir / 'url_map.json'
                if map_file.exists():
                    try:
                        with open(_long_path(map_file), 'r') as f:
                            url_map.update(json.load(f))
                    except Exception:
                        pass

        for subdir in downloaded_js_dir.iterdir():
            if subdir.is_dir():
                for js_file in subdir.glob('*.js'):
                    url_name = safe_filename_to_url(js_file.name)
                    original_url = url_map.get(js_file.name, url_map.get(js_file.stem, ''))
                    if url_name == file_path or js_file.name == file_path or original_url == file_path:
                        target_file = js_file
                        break
                if target_file:
                    break

    if not target_file or not os.path.exists(_long_path(target_file)):
        return jsonify({'error': 'File not found'}), 404

    try:
        with open(_long_path(target_file), 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return jsonify({
            'content': content,
            'filename': target_file.name,
            'url': file_path,
            'size': os.path.getsize(_long_path(target_file))
        })
    except Exception as e:
        return jsonify({'error': f'Error reading file: {str(e)}'}), 500


@scans_bp.route('/api/scans/<scan_id>/emails', methods=['GET'])
def get_emails(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    source_filter = request.args.get('source', '', type=str).strip().lower()
    items = filter_items(results.get('emails', []), base_url, js_file)
    if source_filter:
        items = [item for item in items if item.get('source', 'js') == source_filter]
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/app-links', methods=['GET'])
def get_app_links(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    source_filter = request.args.get('source', '', type=str).strip().lower()
    items = filter_items(results.get('app_links', []), base_url, js_file)
    if source_filter:
        items = [item for item in items if item.get('source', 'js') == source_filter]
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/doc-links', methods=['GET'])
def get_doc_links(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    source_filter = request.args.get('source', '', type=str).strip().lower()
    items = filter_items(results.get('doc_links', []), base_url, js_file)
    if source_filter:
        items = [item for item in items if item.get('source', 'js') == source_filter]
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/social-links', methods=['GET'])
def get_social_links(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    source_filter = request.args.get('source', '', type=str).strip().lower()
    items = filter_items(results.get('social_links', []), base_url, js_file)
    if source_filter:
        items = [item for item in items if item.get('source', 'js') == source_filter]
    return jsonify(paginate_list(items, page, per_page))


@scans_bp.route('/api/scans/<scan_id>/urls', methods=['GET'])
def get_urls(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    page, per_page = get_pagination_params()
    base_url, js_file = get_filter_params()
    source_filter = request.args.get('source', '', type=str).strip().lower()
    items = filter_items(results.get('urls', []), base_url, js_file)
    if source_filter:
        items = [item for item in items if item.get('source', 'js') == source_filter]
    return jsonify(paginate_list(items, page, per_page))


def _get_source_counts(scan_id, result_key):
    """Helper to get js/crawl/total counts for any result category."""
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    items = results.get(result_key, [])
    counts = {'crawl': 0, 'js': 0, 'total': len(items)}
    for item in items:
        source = item.get('source', 'js')
        if source in ('crawl', 'js'):
            counts[source] += 1
        else:
            counts['js'] += 1
    return jsonify(counts)


@scans_bp.route('/api/scans/<scan_id>/emails/counts', methods=['GET'])
def get_email_counts(scan_id):
    return _get_source_counts(scan_id, 'emails')


@scans_bp.route('/api/scans/<scan_id>/app-links/counts', methods=['GET'])
def get_app_link_counts(scan_id):
    return _get_source_counts(scan_id, 'app_links')


@scans_bp.route('/api/scans/<scan_id>/doc-links/counts', methods=['GET'])
def get_doc_link_counts(scan_id):
    return _get_source_counts(scan_id, 'doc_links')


@scans_bp.route('/api/scans/<scan_id>/social-links/counts', methods=['GET'])
def get_social_link_counts(scan_id):
    return _get_source_counts(scan_id, 'social_links')


@scans_bp.route('/api/scans/<scan_id>/cloud-resources/counts', methods=['GET'])
def get_cloud_resource_counts(scan_id):
    return _get_source_counts(scan_id, 'cloud_resources')


@scans_bp.route('/api/scans/<scan_id>/urls/counts', methods=['GET'])
def get_url_counts(scan_id):
    scan = Scan.query.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    scan_dir = get_scan_directory(scan.name)
    results = parse_scan_results(scan_dir)
    items = results.get('urls', [])
    counts = {'crawl': 0, 'js': 0, 'total': len(items)}
    for item in items:
        source = item.get('source', 'js')
        if source in ('crawl', 'js'):
            counts[source] += 1
        else:
            counts['js'] += 1
    return jsonify(counts)
