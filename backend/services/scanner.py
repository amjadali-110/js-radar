"""
Scan execution service - runs scans in background threads
"""

import os
import re
import sys
import json
import subprocess
import tempfile
import urllib.request
import urllib.error
import ssl
import hashlib
import gzip
from pathlib import Path
from urllib.parse import urlparse
import zlib
import socket
import time
from datetime import datetime, timezone
from flask import current_app
from backend.extensions import db
from backend.models.scan import Scan
from backend.services.parser import get_scan_directory, parse_scan_results, calculate_directory_size_mb
from backend.utils.url_validator import validate_url as _ssrf_validate_url
try:
    import psutil
except Exception:
    psutil = None

# Active scan processes
active_scans = {}


def _long_path(p):
    """On Windows, prefix path with \\\\?\\ to bypass the 260-char MAX_PATH limit."""
    s = str(p)
    if os.name == 'nt' and not s.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(s)
    return s


def _safe_js_filename(source):
    safe = source
    for ch in ['/', ':', '?', '&', '=', '#', '%', '*', '<', '>', '|', '"', "'", ' ']:
        safe = safe.replace(ch, '_')
    if len(safe) > 80:
        safe = safe[:67] + '_' + hashlib.md5(source.encode('utf-8')).hexdigest()[:12]
    if not safe.endswith('.js'):
        safe += '.js'
    return safe


def _write_live_stats(scan_dir, current_ram_mb, peak_ram_mb, storage_mb=0):
    """Write live_stats.json so the frontend can pick up RAM/storage stats.

    Uses atomic write (write-to-temp then rename) to avoid the frontend
    reading a partially-written file on both Linux and Windows.
    """
    if not scan_dir:
        return
    try:
        scan_dir = Path(scan_dir)
        live_stats_file = scan_dir / 'live_stats.json'
        # Read existing live stats to preserve fields written by other code
        existing = {}
        if os.path.exists(_long_path(live_stats_file)):
            try:
                with open(_long_path(live_stats_file), 'r') as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing['current_ram_mb'] = round(current_ram_mb, 2)
        # Never let peak go down — keep the highest value seen across all subprocesses
        existing['peak_ram_mb'] = round(max(peak_ram_mb, existing.get('peak_ram_mb', 0)), 2)
        if storage_mb:
            existing['storage_mb'] = round(storage_mb, 2)
        # Atomic write: write to temp file in same directory then rename
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(scan_dir), suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(existing, f, indent=2)
            # On Windows, os.rename fails if dest exists; os.replace works on both
            os.replace(tmp_path, str(live_stats_file))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    except Exception:
        pass


def _calculate_dir_size_mb(directory):
    """Return total size of all files under *directory* in MB.

    Delegates to calculate_directory_size_mb from parser which uses _long_path
    for Windows MAX_PATH safety.
    """
    return calculate_directory_size_mb(directory)


def _get_process_tree_rss(tracked):
    """Get total RSS of a process and all its children (recursive).

    Returns MB. Works on both Linux and Windows via psutil.
    """
    total = 0
    try:
        total += tracked.memory_info().rss
        for child in tracked.children(recursive=True):
            try:
                total += child.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    return total / (1024 * 1024)


def _run_subprocess(app, cmd, cwd, scan_id, scan_dir=None):
    # On Windows, pipe buffers are small (~4-8 KB).  If stdout/stderr are
    # connected to PIPE but nobody drains them, the child blocks once the
    # buffer is full — causing the scan to hang indefinitely.
    #
    # Fix: drain stdout/stderr in background threads (via communicate() in a
    # thread) while we continue polling for RAM stats.
    import threading

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        cwd=str(cwd)
    )
    active_scans[scan_id] = process
    peak_ram_mb = 0.0
    current_ram_mb = 0.0
    tracked = None
    if psutil:
        try:
            tracked = psutil.Process(process.pid)
            try:
                current_ram_mb = _get_process_tree_rss(tracked)
                peak_ram_mb = current_ram_mb
            except Exception:
                pass
        except Exception:
            tracked = None

    # Drain pipes in a background thread to prevent Windows pipe deadlock
    comm_result = [None, None]  # [stdout, stderr]

    def _drain():
        comm_result[0], comm_result[1] = process.communicate()

    drain_thread = threading.Thread(target=_drain, daemon=True)
    drain_thread.start()

    last_write = 0
    last_storage_check = 0
    live_storage_mb = 0.0
    while drain_thread.is_alive():
        if tracked:
            try:
                rss_mb = _get_process_tree_rss(tracked)
                current_ram_mb = rss_mb
                if rss_mb > peak_ram_mb:
                    peak_ram_mb = rss_mb
            except Exception:
                tracked = None
        # Write live stats every ~1 second
        now = time.monotonic()
        if scan_dir and now - last_write >= 1.0:
            # Recalculate storage every ~5 seconds to avoid excessive disk I/O
            if now - last_storage_check >= 5.0:
                live_storage_mb = _calculate_dir_size_mb(scan_dir)
                last_storage_check = now
            _write_live_stats(scan_dir, current_ram_mb, peak_ram_mb, storage_mb=live_storage_mb)
            last_write = now
        drain_thread.join(timeout=0.2)

    stdout, stderr = comm_result[0] or b'', comm_result[1] or b''
    # Process has exited — current RAM is 0, but preserve peak
    current_ram_mb = 0.0
    # Write final stats (current=0 since process ended; preserve peak and storage)
    if scan_dir:
        _write_live_stats(scan_dir, current_ram_mb, peak_ram_mb,
                          storage_mb=_calculate_dir_size_mb(scan_dir))
    return process.returncode, stdout, stderr, peak_ram_mb


def _update_scan_counts(scan, scan_name, fallback_total_urls=0):
    scan_dir = get_scan_directory(scan_name)
    results = parse_scan_results(scan_dir)
    stats = results.get('stats', {})
    scan.total_urls = stats.get('total_urls', fallback_total_urls)
    scan.successful_urls = stats.get('successful_urls', scan.total_urls)
    scan.failed_urls = stats.get('failed_urls', 0)
    scan.js_downloaded = stats.get('js_downloaded', len(results.get('files', [])))
    scan.js_failed = stats.get('js_failed', 0)
    scan.peak_ram_mb = stats.get('peak_ram_mb', 0)
    scan.storage_mb = stats.get('storage_mb', 0)
    scan.secrets_count = len(results.get('secrets', []))
    scan.endpoints_count = len(results.get('endpoints', []))
    scan.subdomains_count = len(results.get('subdomains', []))
    scan.ips_count = len(results.get('ips', []))
    scan.cloud_resources_count = len(results.get('cloud_resources', []))
    scan.emails_count = len(results.get('emails', []))
    scan.app_links_count = len(results.get('app_links', []))
    scan.doc_links_count = len(results.get('doc_links', []))
    scan.social_links_count = len(results.get('social_links', []))
    scan.urls_count = len(results.get('urls', []))
    scan.files_count = len(results.get('files', []))
    scan.parameters_count = 0


def _is_transient_error(exc):
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return True
        if isinstance(reason, socket.timeout):
            return True
        if isinstance(reason, OSError) and getattr(reason, 'errno', None) in (-3, -2, 11001, 11004):
            return True
    return isinstance(exc, (TimeoutError, ConnectionResetError, ConnectionRefusedError))


# RFC 7230 token characters for HTTP header field names
_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+\-.^_`|~][\w\-]*$")


def _sanitize_headers(headers):
    """Return only well-formed 'Name: Value' header strings.

    Rejects any entry that starts with '-' (CLI flag injection),
    contains newlines/null bytes, or doesn't match the Name: Value format.
    """
    if not headers:
        return []
    safe = []
    for h in headers:
        if not isinstance(h, str):
            continue
        h = h.strip()
        if not h or h.startswith('-'):
            continue
        if '\n' in h or '\r' in h or '\x00' in h:
            continue
        if ':' not in h:
            continue
        name, _, val = h.partition(':')
        if not _HEADER_NAME_RE.match(name.strip()):
            continue
        safe.append(h)
    return safe


class _SSRFRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Block SSRF via open redirects — re-validate every redirect destination."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        ok, err = _ssrf_validate_url(newurl)
        if not ok:
            raise urllib.error.URLError(f"SSRF: redirect blocked — {err}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_js_url(url, output_dir, max_retries=3, retry_delay=3,
                     cookie=None, headers=None, max_bytes=10 * 1024 * 1024):
    """Download JS with retry/decompression logic similar to full scanner.

    max_bytes: hard cap on decompressed content size (default 10 MB).
    """
    # Defense-in-depth: reject non-http(s) schemes regardless of call site
    _scheme = urlparse(url).scheme.lower()
    if _scheme not in ('http', 'https'):
        return False, _safe_js_filename(url), f"URL scheme '{_scheme}' is not allowed"

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    safe_filename = _safe_js_filename(url)
    output_path = output_dir / safe_filename
    last_error = "Unknown error"

    for attempt in range(1, max_retries + 1):
        try:
            req_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept-Encoding': 'gzip, deflate',
            }
            if cookie:
                # Cookie values are passed as-is; validate no header injection chars
                safe_cookie = cookie.replace('\r', '').replace('\n', '').replace('\x00', '')
                req_headers['Cookie'] = safe_cookie
            if headers:
                for h in _sanitize_headers(headers):
                    key, _, val = h.partition(':')
                    req_headers[key.strip()] = val.strip()

            opener = urllib.request.build_opener(
                _SSRFRedirectHandler(),
                urllib.request.HTTPSHandler(context=ssl_context),
            )
            req = urllib.request.Request(url, headers=req_headers)
            with opener.open(req, timeout=30) as response:
                # Enforce Content-Length before reading to avoid DoS via large files
                content_length = response.headers.get('Content-Length')
                try:
                    if content_length and int(content_length) > max_bytes:
                        return False, safe_filename, f"File too large ({content_length} bytes > {max_bytes} limit)"
                except ValueError:
                    pass  # malformed Content-Length — chunked read cap still applies

                # Read in chunks to enforce size limit even without Content-Length
                chunks = []
                total = 0
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        return False, safe_filename, f"File exceeds {max_bytes // (1024*1024)} MB download limit"
                    chunks.append(chunk)
                raw = b''.join(chunks)

                encoding = response.headers.get('Content-Encoding', '').lower()
                if encoding == 'gzip':
                    content = gzip.decompress(raw)
                elif encoding == 'deflate':
                    try:
                        content = zlib.decompress(raw)
                    except zlib.error:
                        content = zlib.decompress(raw, -15)
                else:
                    try:
                        content = gzip.decompress(raw)
                    except Exception:
                        content = raw

                # Post-decompress size check
                if len(content) > max_bytes:
                    return False, safe_filename, f"Decompressed file exceeds {max_bytes // (1024*1024)} MB limit"

                start = content.lstrip()[:15].lower()
                if start.startswith((b'<!doctype', b'<html')):
                    return False, safe_filename, "Not a JS - False Positive"

                with open(_long_path(output_path), 'wb') as f:
                    f.write(content)
                return True, safe_filename, None
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
            break
        except Exception as e:
            last_error = str(e)[:150]
            if _is_transient_error(e) and attempt < max_retries:
                time.sleep(retry_delay)
                continue
            break

    try:
        lp = _long_path(output_path)
        if os.path.exists(lp):
            os.unlink(lp)
    except OSError:
        pass
    return False, safe_filename, last_error


def run_scan_async(app, scan_id, scan_name, target_urls, cookie=None, headers=None, depth=None, delay=None):
    """Run the scan in a background thread"""
    temp_url_file = None

    with app.app_context():
        scan = Scan.query.get(scan_id)
        if not scan:
            return

        scan.status = 'running'
        scan.started_at = datetime.now(timezone.utc)
        db.session.commit()

        try:
            temp_url_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.txt',
                prefix=f'urls_{scan_name}_',
                delete=False
            )
            for url in target_urls:
                temp_url_file.write(url + '\n')
            temp_url_file.close()

            # Save input URLs to scan directory for reference
            scan_dir = get_scan_directory(scan_name)
            os.makedirs(_long_path(scan_dir), exist_ok=True)
            input_urls_file = scan_dir / 'input_urls.txt'
            with open(_long_path(input_urls_file), 'w') as f:
                for url in target_urls:
                    f.write(url + '\n')

            cmd = [
                sys.executable,
                str(app.config['SCANNER_SCRIPT']),
                '-i', temp_url_file.name,
                '-n', scan_name,
                '-p', str(scan.parallel or 3),
                '-c', str(scan.concurrency or 2),
                '-f'
            ]

            if depth is not None:
                cmd.extend(['-d', str(depth)])
            if delay is not None and delay > 0:
                cmd.extend(['-k', str(delay)])
            if cookie:
                safe_cookie = cookie.replace('\r', '').replace('\n', '').replace('\x00', '')
                cmd.extend(['--cookie', safe_cookie])
            if headers:
                try:
                    header_list = json.loads(headers)
                    for h in _sanitize_headers(header_list):
                        cmd.extend(['-H', h])
                except (ValueError, TypeError):
                    pass

            scanner_dir = app.config['SCANNER_SCRIPT'].parent.parent

            return_code, _, stderr, child_peak_mb = _run_subprocess(app, cmd, scanner_dir, scan_id, scan_dir=scan_dir)

            scan_dir = get_scan_directory(scan_name)
            results = parse_scan_results(scan_dir)

            scan.status = 'completed' if return_code == 0 else 'failed'
            scan.completed_at = datetime.now(timezone.utc)

            stats = results.get('stats', {})
            scan.total_urls = stats.get('total_urls', len(target_urls))
            scan.successful_urls = stats.get('successful_urls', 0)
            scan.failed_urls = stats.get('failed_urls', 0)
            scan.js_downloaded = stats.get('js_downloaded', 0)
            scan.js_failed = stats.get('js_failed', 0)
            scan.peak_ram_mb = stats.get('peak_ram_mb', 0)
            scan.storage_mb = stats.get('storage_mb', 0)
            scan.secrets_count = len(results.get('secrets', []))
            scan.endpoints_count = len(results.get('endpoints', []))
            scan.subdomains_count = len(results.get('subdomains', []))
            scan.ips_count = len(results.get('ips', []))
            scan.cloud_resources_count = len(results.get('cloud_resources', []))
            scan.emails_count = len(results.get('emails', []))
            scan.app_links_count = len(results.get('app_links', []))
            scan.doc_links_count = len(results.get('doc_links', []))
            scan.social_links_count = len(results.get('social_links', []))
            scan.urls_count = len(results.get('urls', []))
            scan.files_count = len(results.get('files', []))
            scan.parameters_count = 0

            if return_code != 0:
                scan.error_message = stderr.decode('utf-8', errors='ignore')[:500]
            if child_peak_mb > 0:
                scan.peak_ram_mb = max(scan.peak_ram_mb or 0, child_peak_mb)

            db.session.commit()

        except Exception as e:
            scan.status = 'failed'
            scan.error_message = str(e)
            scan.completed_at = datetime.now(timezone.utc)
            # Calculate storage even on exception
            try:
                scan_dir = get_scan_directory(scan_name)
                scan.storage_mb = calculate_directory_size_mb(scan_dir)
            except Exception:
                pass
            db.session.commit()
        finally:
            active_scans.pop(scan_id, None)
            if temp_url_file and os.path.exists(temp_url_file.name):
                try:
                    os.unlink(temp_url_file.name)
                except Exception:
                    pass


def _get_trufflehog_path(scanner_dir):
    """Return the trufflehog binary path."""
    bin_name = 'trufflehog.exe' if os.name == 'nt' else 'trufflehog'
    local = scanner_dir / 'scanner' / 'bin' / bin_name
    return str(local) if local.exists() else 'trufflehog'


def _process_single_js_url(app, scan_id, url, js_dir, endpoints_dir, extracted_dir,
                           secrets_dir, scanner_dir, scan_dir, file_lock, stats,
                           cookie=None, headers=None, max_bytes=10 * 1024 * 1024):
    """Download one JS URL and immediately run all extractors on it."""
    success, filename, error = _download_js_url(url, js_dir, cookie=cookie, headers=headers, max_bytes=max_bytes)

    with file_lock:
        if success:
            stats['url_map'][filename] = url
        else:
            stats['failures'].append({'js_url': url, 'error': error or 'Unknown error'})

    if not success:
        return

    js_file_path = js_dir / filename

    # --- Run all three extractors for this single file ---

    # 1) Trufflehog (secret scanning)
    trufflehog_bin = _get_trufflehog_path(scanner_dir)
    trufflehog_cmd = [
        trufflehog_bin, 'filesystem', str(js_file_path),
        '--json', '--no-update'
    ]
    try:
        proc = subprocess.run(
            trufflehog_cmd, capture_output=True, timeout=120, cwd=str(scanner_dir)
        )
        if proc.stdout and proc.stdout.strip():
            with file_lock:
                with open(_long_path(secrets_dir / 'secrets.json'), 'ab') as f:
                    f.write(proc.stdout if proc.stdout.endswith(b'\n') else proc.stdout + b'\n')
    except Exception:
        pass

    # 2) Endpoint extraction (-f single file, appends to output)
    endpoint_cmd = [
        sys.executable, str(scanner_dir / 'scanner' / 'endpoint_extractor.py'),
        '-f', str(js_file_path),
        '-o', str(endpoints_dir / 'endpoints.json'),
        '-j'
    ]
    try:
        subprocess.run(endpoint_cmd, capture_output=True, timeout=120, cwd=str(scanner_dir))
    except Exception:
        pass

    # 3) Info extraction (-f single file, appends to output)
    info_cmd = [
        sys.executable, str(scanner_dir / 'scanner' / 'js_info_extractor.py'),
        '-f', str(js_file_path),
        '-o', str(extracted_dir),
        '-j'
    ]
    try:
        subprocess.run(info_cmd, capture_output=True, timeout=180, cwd=str(scanner_dir))
    except Exception:
        pass


def run_js_urls_scan_async(app, scan_id, scan_name, js_urls, cookie=None, headers=None, parallel=5):
    """Analyze a provided list of JS URLs directly (no crawling).

    Each JS URL is processed independently and in parallel:
      download → secret scanning + endpoint extraction + info extraction
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with app.app_context():
        scan = Scan.query.get(scan_id)
        if not scan:
            return

        scan.status = 'running'
        scan.started_at = datetime.now(timezone.utc)
        db.session.commit()

        try:
            scan_dir = get_scan_directory(scan_name)
            js_dir = scan_dir / 'downloaded-js' / 'js_urls'
            endpoints_dir = scan_dir / 'js-endpoints' / 'js_urls'
            extracted_dir = scan_dir / 'js-extracted' / 'js_urls'
            secrets_dir = scan_dir / 'secrets' / 'js_urls'
            for directory in [js_dir, endpoints_dir, extracted_dir, secrets_dir]:
                os.makedirs(_long_path(directory), exist_ok=True)

            input_urls_file = scan_dir / 'input_urls.txt'
            with open(_long_path(input_urls_file), 'w', encoding='utf-8') as f:
                for url in js_urls:
                    f.write(url + '\n')

            scanner_dir = app.config['SCANNER_SCRIPT'].parent.parent

            # Write initial live_stats so frontend shows progress from the start
            _write_live_stats(scan_dir, 0, 0)

            # Shared state protected by a lock
            file_lock = threading.Lock()
            stats = {'url_map': {}, 'failures': []}

            # RAM monitoring: poll current process tree while executor runs.
            # Since JS URLs scans run in-process (threads, not a subprocess),
            # we measure the whole process and subtract a baseline taken before
            # the scan work starts so the number reflects only the scan's usage.
            ram_stop = threading.Event()
            peak_ram_mb = 0.0
            baseline_mb = 0.0
            if psutil:
                try:
                    _p = psutil.Process(os.getpid())
                    baseline_mb = _p.memory_info().rss / (1024 * 1024)
                except Exception:
                    pass

            def _monitor_ram():
                nonlocal peak_ram_mb
                if not psutil:
                    return
                try:
                    proc = psutil.Process(os.getpid())
                except Exception:
                    return
                while not ram_stop.is_set():
                    try:
                        rss = proc.memory_info().rss
                        for child in proc.children(recursive=True):
                            try:
                                rss += child.memory_info().rss
                            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                                pass
                        current_mb = max(0, rss / (1024 * 1024) - baseline_mb)
                        if current_mb > peak_ram_mb:
                            peak_ram_mb = current_mb
                        storage_mb = _calculate_dir_size_mb(scan_dir)
                        _write_live_stats(scan_dir, current_mb, peak_ram_mb, storage_mb=storage_mb)
                    except Exception:
                        pass
                    ram_stop.wait(1.0)

            ram_thread = threading.Thread(target=_monitor_ram, daemon=True)

            # Parse headers JSON string from DB — sanitize before use
            clean_headers = []
            if headers:
                try:
                    header_list = json.loads(headers)
                    clean_headers = _sanitize_headers(header_list)
                except (ValueError, TypeError):
                    pass

            # Process each JS URL in parallel: download + extract per file
            max_workers = min(parallel or 5, len(js_urls))
            max_bytes = app.config.get('MAX_JS_DOWNLOAD_BYTES', 10 * 1024 * 1024)
            ram_thread.start()
            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(
                            _process_single_js_url, app, scan_id, url,
                            js_dir, endpoints_dir, extracted_dir, secrets_dir,
                            scanner_dir, scan_dir, file_lock, stats,
                            cookie=cookie, headers=clean_headers, max_bytes=max_bytes
                        ): url
                        for url in js_urls
                    }
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception:
                            pass
            finally:
                ram_stop.set()
                ram_thread.join(timeout=3)
                # Write final stats: current=0 (work done), preserve peak and storage
                _write_live_stats(scan_dir, 0, peak_ram_mb, storage_mb=_calculate_dir_size_mb(scan_dir))

            # Write url_map and failures
            if stats['url_map']:
                with open(_long_path(js_dir / 'url_map.json'), 'w', encoding='utf-8') as f:
                    json.dump(stats['url_map'], f, indent=2)
            if stats['failures']:
                with open(_long_path(js_dir / 'failed_downloads.json'), 'w', encoding='utf-8') as f:
                    json.dump({
                        'target_url': 'js_urls_input',
                        'total_failed': len(stats['failures']),
                        'failures': stats['failures']
                    }, f, indent=2)

            _update_scan_counts(scan, scan_name, fallback_total_urls=len(js_urls))
            if peak_ram_mb > 0:
                scan.peak_ram_mb = max(scan.peak_ram_mb or 0, peak_ram_mb)
            scan.status = 'completed'
            scan.completed_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception as e:
            scan.status = 'failed'
            scan.error_message = str(e)
            scan.completed_at = datetime.now(timezone.utc)
            db.session.commit()
        finally:
            active_scans.pop(scan_id, None)


def run_uploaded_file_scan_async(app, scan_id, scan_name):
    """Analyze an uploaded local JS file.

    All three extractors (secret scanner, endpoint, info) run in parallel on the
    uploaded file — same pattern as the JS URLs scan pipeline.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with app.app_context():
        scan = Scan.query.get(scan_id)
        if not scan:
            return

        scan.status = 'running'
        scan.started_at = datetime.now(timezone.utc)
        db.session.commit()

        try:
            scan_dir = get_scan_directory(scan_name)
            js_dir = scan_dir / 'downloaded-js' / 'uploaded_file'
            endpoints_dir = scan_dir / 'js-endpoints' / 'uploaded_file'
            extracted_dir = scan_dir / 'js-extracted' / 'uploaded_file'
            secrets_dir = scan_dir / 'secrets' / 'uploaded_file'
            for directory in [js_dir, endpoints_dir, extracted_dir, secrets_dir]:
                os.makedirs(_long_path(directory), exist_ok=True)

            scanner_dir = app.config['SCANNER_SCRIPT'].parent.parent

            # Write initial live_stats so frontend shows RAM from the start
            _write_live_stats(scan_dir, 0, 0)

            # --- RAM monitoring (same approach as JS URLs scan) ---
            ram_stop = threading.Event()
            peak_ram_mb = 0.0
            baseline_mb = 0.0
            if psutil:
                try:
                    _p = psutil.Process(os.getpid())
                    baseline_mb = _p.memory_info().rss / (1024 * 1024)
                except Exception:
                    pass

            def _monitor_ram():
                nonlocal peak_ram_mb
                if not psutil:
                    return
                try:
                    proc = psutil.Process(os.getpid())
                except Exception:
                    return
                while not ram_stop.is_set():
                    try:
                        rss = proc.memory_info().rss
                        for child in proc.children(recursive=True):
                            try:
                                rss += child.memory_info().rss
                            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                                pass
                        current_mb = max(0, rss / (1024 * 1024) - baseline_mb)
                        if current_mb > peak_ram_mb:
                            peak_ram_mb = current_mb
                        storage_mb = _calculate_dir_size_mb(scan_dir)
                        _write_live_stats(scan_dir, current_mb, peak_ram_mb, storage_mb=storage_mb)
                    except Exception:
                        pass
                    ram_stop.wait(1.0)

            ram_thread = threading.Thread(target=_monitor_ram, daemon=True)

            # --- Define the three parallel tasks ---

            errors = []  # collect non-fatal errors

            def _run_trufflehog():
                trufflehog_bin = _get_trufflehog_path(scanner_dir)
                cmd = [
                    trufflehog_bin, 'filesystem', str(js_dir),
                    '--json', '--no-update'
                ]
                try:
                    proc = subprocess.run(
                        cmd, capture_output=True, timeout=120, cwd=str(scanner_dir)
                    )
                    if proc.stdout and proc.stdout.strip():
                        with open(_long_path(secrets_dir / 'secrets.json'), 'wb') as f:
                            f.write(proc.stdout)
                    if proc.returncode != 0 and proc.stderr:
                        errors.append(proc.stderr.decode('utf-8', errors='ignore')[:500])
                except Exception:
                    pass

            def _run_endpoints():
                cmd = [
                    sys.executable, str(scanner_dir / 'scanner' / 'endpoint_extractor.py'),
                    '-d', str(js_dir),
                    '-o', str(endpoints_dir / 'endpoints.json'),
                    '-j'
                ]
                try:
                    proc = subprocess.run(
                        cmd, capture_output=True, timeout=120, cwd=str(scanner_dir)
                    )
                    if proc.returncode != 0 and proc.stderr:
                        errors.append(proc.stderr.decode('utf-8', errors='ignore')[:500])
                except Exception:
                    pass

            def _run_info_extraction():
                cmd = [
                    sys.executable, str(scanner_dir / 'scanner' / 'js_info_extractor.py'),
                    '-d', str(js_dir),
                    '-o', str(extracted_dir),
                    '-j'
                ]
                try:
                    proc = subprocess.run(
                        cmd, capture_output=True, timeout=180, cwd=str(scanner_dir)
                    )
                    if proc.returncode != 0 and proc.stderr:
                        errors.append(proc.stderr.decode('utf-8', errors='ignore')[:500])
                except Exception:
                    pass

            # --- Run all three in parallel ---
            ram_thread.start()
            try:
                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [
                        executor.submit(_run_trufflehog),
                        executor.submit(_run_endpoints),
                        executor.submit(_run_info_extraction),
                    ]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception:
                            pass
            finally:
                ram_stop.set()
                ram_thread.join(timeout=3)
                _write_live_stats(scan_dir, 0, peak_ram_mb, storage_mb=_calculate_dir_size_mb(scan_dir))

            _update_scan_counts(scan, scan_name, fallback_total_urls=1)
            if peak_ram_mb > 0:
                scan.peak_ram_mb = max(scan.peak_ram_mb or 0, peak_ram_mb)
            last_error = errors[0] if errors else None
            scan.status = 'failed' if last_error else 'completed'
            scan.error_message = last_error
            scan.completed_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception as e:
            scan.status = 'failed'
            scan.error_message = str(e)
            scan.completed_at = datetime.now(timezone.utc)
            db.session.commit()
        finally:
            active_scans.pop(scan_id, None)
