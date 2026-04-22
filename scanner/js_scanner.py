#!/usr/bin/env python3
"""
JS Discovery Scanner - Manages gospider scans with resource monitoring and JS downloading
"""

import os
import re
import sys
import time
import json
import shutil
import signal
import argparse
import subprocess
import threading
import socket
import urllib.request
import ssl
import gzip
import zlib
import hashlib
from pathlib import Path
from datetime import datetime
import queue as _queue_module
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import patterns from js_info_extractor for crawl extraction
sys.path.insert(0, str(Path(__file__).parent))
from js_info_extractor import (
    EMAIL_PATTERN,
    SOCIAL_MEDIA_PATTERNS,
    APP_LINK_PATTERNS,
    DOC_LINK_PATTERNS,
    CLOUD_BUCKET_PATTERNS,
)

# Bundled binaries directory (scanner/bin/)
_BIN_DIR = Path(__file__).parent / "bin"


def _long_path(p):
    """On Windows, prefix path with \\\\?\\ to bypass the 260-char MAX_PATH limit.

    Python's open() / mkdir() honour this prefix so paths up to ~32 767 chars
    work on NTFS.  On non-Windows platforms the path is returned unchanged.
    """
    s = str(p)
    if os.name == 'nt' and not s.startswith('\\\\?\\'):
        # The prefix requires an absolute path with backslashes
        abs_path = os.path.abspath(s)
        return '\\\\?\\' + abs_path
    return s

def _tool_path(name):
    """Return path to a tool binary: use scanner/bin/ if present, else fall back to system PATH."""
    # On Windows, binaries have .exe extension
    candidates = [_BIN_DIR / name, _BIN_DIR / f"{name}.exe"] if os.name == 'nt' else [_BIN_DIR / name]
    for local in candidates:
        if local.is_file():
            return str(local)
    return name

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False
    print("WARNING: 'psutil' is not installed. RAM metrics will be disabled for this scan.")


class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


class ResourceMonitor:
    """Monitor RAM and storage usage for the scan"""

    def __init__(self, scan_dir):
        self.scan_dir = scan_dir
        self.running = False
        self.peak_ram_mb = 0
        self.current_ram_mb = 0
        self.storage_mb = 0
        self.process_pids = set()
        self.lock = threading.Lock()

    def add_pid(self, pid):
        with self.lock:
            self.process_pids.add(pid)

    def remove_pid(self, pid):
        with self.lock:
            self.process_pids.discard(pid)

    def get_scan_storage(self):
        """Get total storage used by scan directory in MB"""
        total_bytes = 0
        try:
            directory = Path(self.scan_dir)
            if directory.exists():
                for f in directory.rglob('*'):
                    if f.is_file():
                        try:
                            total_bytes += os.path.getsize(_long_path(f))
                        except OSError:
                            pass
        except Exception:
            pass
        return total_bytes / (1024 * 1024)

    def get_processes_ram(self):
        """Get RAM usage of all tracked processes in MB.

        Important: avoid double counting when both a parent process and one of
        its children are tracked (common in this scanner). We build a unique
        process set first, then sum memory exactly once per PID.
        """
        if not PSUTIL_AVAILABLE:
            return 0

        total_ram = 0
        with self.lock:
            root_pids = list(self.process_pids)

        # Build a de-duplicated set of all tracked roots + descendants
        all_pids = set()
        stale_roots = []
        for root_pid in root_pids:
            try:
                root_proc = psutil.Process(root_pid)
                procs = [root_proc] + root_proc.children(recursive=True)
                for proc in procs:
                    try:
                        all_pids.add(proc.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                stale_roots.append(root_pid)

        # Drop dead roots from the tracking list
        for stale_pid in stale_roots:
            self.remove_pid(stale_pid)

        # Sum memory exactly once per process (prefer USS when available)
        for pid in all_pids:
            try:
                proc = psutil.Process(pid)
                try:
                    mem_info = proc.memory_full_info()
                    # USS better reflects "unique" process memory and avoids
                    # inflating totals due to shared pages/libraries.
                    ram_bytes = getattr(mem_info, 'uss', 0) or proc.memory_info().rss
                except (psutil.AccessDenied, AttributeError):
                    ram_bytes = proc.memory_info().rss
                total_ram += ram_bytes
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        return total_ram / (1024 * 1024)

    def update(self):
        """Update resource metrics"""
        self.current_ram_mb = self.get_processes_ram()
        self.storage_mb = self.get_scan_storage()
        if self.current_ram_mb > self.peak_ram_mb:
            self.peak_ram_mb = self.current_ram_mb

    def get_stats(self):
        """Get current resource statistics"""
        return {
            'current_ram_mb': self.current_ram_mb,
            'peak_ram_mb': self.peak_ram_mb,
            'storage_mb': self.storage_mb
        }


class JSDownloader:
    """Download JS files from gospider output in parallel"""

    def __init__(self, spider_output_dir, download_dir, target_url="", timeout=30, on_file_ready=None):
        self.spider_output_dir = Path(spider_output_dir)
        self.download_dir = Path(download_dir)
        self.target_url = target_url
        self.timeout = timeout
        self.on_file_ready = on_file_ready  # called with Path after each successful download
        self.processed_urls = set()
        self.lock = threading.Lock()
        self.running = True
        self.js_downloaded = 0
        self.js_failed = 0
        self.failed_downloads = []  # List of (js_url, error_reason)

        # Create SSL context that ignores certificate errors
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

        # JS URL pattern - matches .js and .js.map URLs with optional query params
        # Uses lookahead to avoid false positives like .json, .jsp, .jsx
        self.js_pattern = re.compile(r'https?://[^\s\'"<>]+\.js(?:\.map)?(?:\?[^\s\'"<>]*)?(?=[\s\'"<>]|$)')

        # Exclusion patterns
        self.exclude_patterns = []

        # Mapping of safe filenames to original URLs
        self.url_map = {}

    def get_safe_filename(self, url):
        """Convert URL to safe filename"""
        safe_name = url
        for char in ['/', ':', '?', '&', '=', '#', '%', '*', '<', '>', '|', '"', "'", ' ']:
            safe_name = safe_name.replace(char, '_')
        if len(safe_name) > 80:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            safe_name = safe_name[:67] + '_' + url_hash
        return safe_name

    def normalize_url(self, url):
        """Normalize URL - remove query params and standard ports"""
        # Remove query parameters
        url = url.split('?')[0]
        # Remove standard ports
        url = re.sub(r'(https?://[^:/]+):(80|443)(/|$)', r'\1\3', url)
        return url

    def extract_js_urls(self):
        """Extract JS URLs from gospider output files"""
        js_urls = set()

        if not self.spider_output_dir.exists():
            return js_urls

        try:
            for filepath in self.spider_output_dir.rglob('*'):
                if filepath.is_file():
                    try:
                        with open(_long_path(filepath), 'r', errors='ignore') as f:
                            content = f.read()
                            urls = self.js_pattern.findall(content)
                            for url in urls:
                                # Normalize and filter
                                url = self.normalize_url(url)
                                if not any(excl in url for excl in self.exclude_patterns):
                                    js_urls.add(url)
                    except Exception:
                        pass
        except Exception:
            pass

        return js_urls

    def _is_transient_error(self, exc):
        """Return True if the exception is a transient network/DNS error worth retrying."""
        if isinstance(exc, urllib.error.URLError):
            reason = exc.reason
            # socket.gaierror: DNS failures (errno -3 / NXDOMAIN, -2 / no answer, etc.)
            if isinstance(reason, socket.gaierror):
                return True
            # socket.timeout: connection/read timeout wrapped inside URLError
            if isinstance(reason, socket.timeout):
                return True
            # Generic OSError with well-known transient errnos
            # -3/-2: Linux DNS errnos; 11001/11004: Windows WSAHOST_NOT_FOUND / WSANO_DATA
            if isinstance(reason, OSError) and getattr(reason, 'errno', None) in (-3, -2, 11001, 11004):
                return True
        # Bare TimeoutError / ConnectionResetError raised directly (not wrapped in URLError)
        if isinstance(exc, (TimeoutError, ConnectionResetError, ConnectionRefusedError)):
            return True
        return False

    def download_file(self, url, max_retries=3, retry_delay=3):
        """Download a single JS file. Returns (success, error_reason).

        Retries up to max_retries times on transient network/DNS errors
        (e.g. [Errno -3] Temporary failure in name resolution) with a
        retry_delay-second pause between attempts.
        """
        safe_filename = self.get_safe_filename(url)
        # Only add .js extension if not already present
        if not safe_filename.endswith('.js'):
            safe_filename = safe_filename + '.js'
        output_path = self.download_dir / safe_filename

        last_error = "Unknown error"
        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept-Encoding': 'gzip, deflate',
                    }
                )
                with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl_context) as response:
                    raw = response.read()
                    # Normalize header to lowercase — HTTP headers are case-insensitive
                    encoding = response.headers.get('Content-Encoding', '').lower()
                    if encoding == 'gzip':
                        content = gzip.decompress(raw)
                    elif encoding == 'deflate':
                        # Some servers send raw DEFLATE (no zlib header) despite claiming deflate;
                        # try zlib-wrapped first, fall back to raw deflate (wbits=-15)
                        try:
                            content = zlib.decompress(raw)
                        except zlib.error:
                            content = zlib.decompress(raw, -15)
                    else:
                        # No Content-Encoding header: try gzip anyway since some CDNs
                        # compress without setting the header (root cause of the original bug)
                        try:
                            content = gzip.decompress(raw)
                        except Exception:
                            content = raw
                    # Check if it's an HTML page (false positive)
                    start = content.lstrip()[:15].lower()
                    if start.startswith((b'<!doctype', b'<html')):
                        return False, "Not a JS - False Positive"
                    with open(_long_path(output_path), 'wb') as f:
                        f.write(content)
                with self.lock:
                    self.url_map[safe_filename] = url
                    self.save_url_map()
                if self.on_file_ready:
                    try:
                        self.on_file_ready(output_path)
                    except Exception:
                        pass
                return True, None

            except urllib.error.HTTPError as e:
                # HTTP errors (4xx/5xx) are not transient — don't retry
                last_error = f"HTTP {e.code}: {e.reason}"
                break
            except urllib.error.URLError as e:
                last_error = f"URL Error: {str(e.reason)}"
                if self._is_transient_error(e) and attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
                break
            except TimeoutError as e:
                last_error = "Timeout"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
                break
            except Exception as e:
                last_error = str(e)[:100]
                break

        # Remove partial file if exists
        try:
            lp = _long_path(output_path)
            if os.path.exists(lp):
                os.unlink(lp)
        except OSError:
            pass
        return False, last_error

    def run(self):
        """Main download loop - runs while gospider is scanning"""
        os.makedirs(_long_path(self.download_dir), exist_ok=True)

        while self.running:
            # Extract new JS URLs
            current_urls = self.extract_js_urls()

            with self.lock:
                new_urls = current_urls - self.processed_urls

            # Download new JS files - mark each as processed only AFTER download attempt
            for url in new_urls:
                if not self.running:
                    break
                success, error = self.download_file(url)
                with self.lock:
                    self.processed_urls.add(url)
                    if success:
                        self.js_downloaded += 1
                    else:
                        self.js_failed += 1
                        self.failed_downloads.append((url, error))
                        self.save_failed_downloads()

            # Small delay before next check
            time.sleep(2)

        # Final pass after gospider completes - download ALL remaining URLs
        current_urls = self.extract_js_urls()
        with self.lock:
            new_urls = current_urls - self.processed_urls

        for url in new_urls:
            success, error = self.download_file(url)
            with self.lock:
                self.processed_urls.add(url)
                if success:
                    self.js_downloaded += 1
                else:
                    self.js_failed += 1
                    self.failed_downloads.append((url, error))
                    self.save_failed_downloads()

        # Save filename-to-URL mapping
        self.save_url_map()

    def save_url_map(self):
        """Save mapping of safe filenames to original URLs"""
        if not self.url_map:
            return
        map_file = self.download_dir / "url_map.json"
        try:
            with open(_long_path(map_file), 'w') as f:
                json.dump(self.url_map, f, indent=2)
        except Exception:
            pass

    def save_failed_downloads(self):
        """Save failed downloads to a JSON file in the download directory"""
        if not self.failed_downloads:
            return

        failed_file = self.download_dir / "failed_downloads.json"
        try:
            data = {
                'target_url': self.target_url,
                'total_failed': len(self.failed_downloads),
                'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'failures': [
                    {'js_url': js_url, 'error': error}
                    for js_url, error in self.failed_downloads
                ]
            }
            with open(_long_path(failed_file), 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def stop(self):
        """Stop the downloader"""
        self.running = False

    def get_stats(self):
        """Get download statistics"""
        with self.lock:
            return {
                'downloaded': self.js_downloaded,
                'failed': self.js_failed,
                'failed_details': list(self.failed_downloads),
                'total_found': len(self.processed_urls)
            }


class JSScanner:
    """Main scanner class for managing gospider scans"""

    def __init__(self, input_file, scan_name, max_parallel=3, concurrency=2, force=False, depth=1, delay=0, cookie='', headers=None):
        self.input_file = Path(input_file)
        self.scan_name = scan_name
        self.max_parallel = max_parallel
        self.concurrency = concurrency
        self.force = force  # Force overwrite existing scan without prompting
        self.depth = depth
        self.delay = delay
        self.cookie = cookie or ''
        self.headers = headers or []

        # Create scan directory inside data/scans
        self.base_dir = Path(__file__).parent.parent / "data" / "scans"
        self.scan_dir = self.base_dir / scan_name
        self.output_dir = self.scan_dir / "spider_output"
        self.downloaded_js_dir = self.scan_dir / "downloaded-js"
        self.secrets_dir = self.scan_dir / "secrets"
        self.js_endpoints_dir = self.scan_dir / "js-endpoints"
        self.js_extracted_dir = self.scan_dir / "js-extracted"

        # Path to extractor scripts (sibling files in scanner/)
        self.extractor_script = Path(__file__).parent / "endpoint_extractor.py"
        self.info_extractor_script = Path(__file__).parent / "js_info_extractor.py"

        # URL list
        self.urls = []

        # Statistics
        self.total_urls = 0
        self.completed_urls = 0
        self.failed_urls = 0
        self.total_js_downloaded = 0
        self.total_js_failed = 0
        self.total_secrets_found = 0
        self.total_endpoints_found = 0
        self.total_info_extracted = 0
        self.all_failed_downloads = []  # List of (target_url, js_url, error)
        self.active_processes = {}
        self.active_downloaders = {}
        self.lock = threading.Lock()

        # Resource monitor
        self.resource_monitor = None

        # Control flags
        self.running = True
        self.start_time = None

    def check_existing_scan(self):
        """Check if scan directory already exists and handle it"""
        if self.scan_dir.exists():
            # If force mode is enabled, automatically overwrite
            if self.force:
                print(f"{Colors.YELLOW}[*] Force mode: Removing existing scan directory...{Colors.RESET}")
                shutil.rmtree(_long_path(self.scan_dir))
                return

            # Check if running in non-interactive mode (no terminal)
            if not sys.stdin.isatty():
                print(f"{Colors.YELLOW}[*] Non-interactive mode: Removing existing scan directory...{Colors.RESET}")
                shutil.rmtree(_long_path(self.scan_dir))
                return

            print(f"\n{Colors.YELLOW}[!] Warning: Scan directory already exists: {self.scan_dir}{Colors.RESET}")
            print(f"{Colors.WHITE}    Choose an option:{Colors.RESET}")
            print(f"    [1] Overwrite (delete existing scan)")
            print(f"    [2] Rename (add timestamp to new scan)")
            print(f"    [3] Cancel")

            while True:
                choice = input(f"\n{Colors.YELLOW}Enter choice [1/2/3]: {Colors.RESET}").strip()

                if choice == '1':
                    print(f"{Colors.RED}[*] Removing existing scan directory...{Colors.RESET}")
                    shutil.rmtree(_long_path(self.scan_dir))
                    break
                elif choice == '2':
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    new_name = f"{self.scan_name}_{timestamp}"
                    self.scan_dir = self.base_dir / new_name
                    self.output_dir = self.scan_dir / "spider_output"
                    self.downloaded_js_dir = self.scan_dir / "downloaded-js"
                    self.secrets_dir = self.scan_dir / "secrets"
                    self.js_endpoints_dir = self.scan_dir / "js-endpoints"
                    self.js_extracted_dir = self.scan_dir / "js-extracted"
                    self.scan_name = new_name
                    print(f"{Colors.GREEN}[+] New scan name: {new_name}{Colors.RESET}")
                    break
                elif choice == '3':
                    print(f"{Colors.RED}[!] Scan cancelled.{Colors.RESET}")
                    sys.exit(0)
                else:
                    print(f"{Colors.RED}[!] Invalid choice. Please enter 1, 2, or 3.{Colors.RESET}")

    def setup_directories(self):
        """Create necessary directories for the scan"""
        # Create base directory first
        os.makedirs(_long_path(self.base_dir), exist_ok=True)

        self.check_existing_scan()

        print(f"{Colors.CYAN}[*] Setting up scan directory: {self.scan_dir}{Colors.RESET}")

        for d in [self.scan_dir, self.output_dir, self.downloaded_js_dir,
                  self.secrets_dir, self.js_endpoints_dir, self.js_extracted_dir]:
            os.makedirs(_long_path(d), exist_ok=True)

        # Create scan info file
        info_file = self.scan_dir / "scan_info.txt"
        with open(_long_path(info_file), 'w') as f:
            f.write(f"Scan Name: {self.scan_name}\n")
            f.write(f"Input File: {self.input_file}\n")
            f.write(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Max Parallel: {self.max_parallel}\n")
            f.write(f"Concurrency: {self.concurrency}\n")

    def load_urls(self):
        """Load URLs from input file"""
        print(f"{Colors.CYAN}[*] Loading URLs from: {self.input_file}{Colors.RESET}")

        if not self.input_file.exists():
            print(f"{Colors.RED}[!] Error: Input file not found: {self.input_file}{Colors.RESET}")
            sys.exit(1)

        with open(self.input_file, 'r') as f:
            for line in f:
                url = line.strip()
                if url and not url.startswith('#'):
                    self.urls.append(url)

        self.total_urls = len(self.urls)
        print(f"{Colors.GREEN}[+] Found {self.total_urls} URLs{Colors.RESET}")

        return self.urls

    def get_safe_filename(self, url):
        """Convert URL to safe filename, preserving protocol"""
        safe_name = url.replace('https://', 'https_').replace('http://', 'http_')
        for char in ['/', ':', '?', '&', '=', '#', '%', '*', '<', '>', '|', '"', "'"]:
            safe_name = safe_name.replace(char, '_')
        if len(safe_name) > 80:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            safe_name = safe_name[:67] + '_' + url_hash
        return safe_name

    def run_trufflehog(self, js_download_dir, secrets_output_dir):
        """Run secret scanner on the whole JS download directory and return secrets count"""
        secrets_count = 0

        if not js_download_dir.exists():
            return secrets_count

        # Check if directory has any JS files
        js_files = list(js_download_dir.glob('*.js'))
        if not js_files:
            return secrets_count

        os.makedirs(_long_path(secrets_output_dir), exist_ok=True)
        output_file = secrets_output_dir / "secrets.json"

        # Scan the whole directory at once
        cmd = [
            _tool_path("trufflehog"),
            "filesystem",
            str(js_download_dir),
            "--json",
            "--no-update"
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if self.resource_monitor:
                self.resource_monitor.add_pid(process.pid)
            try:
                stdout, _ = process.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                print(f"[trufflehog] timed out after 300s for {js_download_dir}")
                stdout = ""
            finally:
                if self.resource_monitor:
                    self.resource_monitor.remove_pid(process.pid)

            # Parse JSON output to count secrets
            if stdout.strip():
                # Each line is a JSON object representing a secret
                lines = [line for line in stdout.strip().split('\n') if line.strip()]
                if lines:
                    secrets_count = len(lines)
                    # Save results to file
                    with open(_long_path(output_file), 'w') as f:
                        f.write(stdout)

        except Exception as e:
            print(f"[trufflehog] error: {e}")

        return secrets_count

    def run_endpoint_extractor(self, js_download_dir, endpoints_output_dir):
        """Run endpoint extractor on downloaded JS files and return endpoints count"""
        endpoints_count = 0

        if not js_download_dir.exists():
            return endpoints_count

        # Check if directory has any JS files (search recursively for .js and .js.js files)
        js_files = list(js_download_dir.rglob('*.js')) + list(js_download_dir.rglob('*.js.js'))
        if not js_files:
            return endpoints_count

        # Check if extractor script exists
        if not self.extractor_script.exists():
            return endpoints_count

        os.makedirs(_long_path(endpoints_output_dir), exist_ok=True)
        output_file = endpoints_output_dir / "endpoints.json"

        cmd = [
            sys.executable,
            str(self.extractor_script),
            "-d", str(js_download_dir),
            "-o", str(output_file),
            "-j"
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if self.resource_monitor:
                self.resource_monitor.add_pid(process.pid)
            timed_out = False
            try:
                _, stderr = process.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                print(f"[endpoint_extractor] timed out after 120s for {js_download_dir}")
                stderr = ""
                timed_out = True
            finally:
                if self.resource_monitor:
                    self.resource_monitor.remove_pid(process.pid)

            if not timed_out and process.returncode != 0:
                print(f"[endpoint_extractor] exited with code {process.returncode}")
                if stderr:
                    print(f"[endpoint_extractor] stderr: {stderr[:500]}")

            # Count endpoints from output file (skip on timeout - file may be partial)
            if not timed_out and os.path.exists(_long_path(output_file)):
                try:
                    with open(_long_path(output_file), 'r') as f:
                        lines = [line for line in f.readlines() if line.strip()]
                        endpoints_count = len(lines)
                except Exception as e:
                    print(f"[endpoint_extractor] error reading output: {e}")

        except Exception as e:
            print(f"[endpoint_extractor] error: {e}")

        return endpoints_count

    def run_js_info_extractor(self, js_download_dir, extracted_output_dir):
        """Run JS info extractor on downloaded JS files and return total findings count"""
        info_count = 0

        if not js_download_dir.exists():
            return info_count

        # Check if directory has any JS files (search recursively for .js and .js.js files)
        js_files = list(js_download_dir.rglob('*.js')) + list(js_download_dir.rglob('*.js.js'))
        if not js_files:
            return info_count

        # Check if info extractor script exists
        if not self.info_extractor_script.exists():
            return info_count

        os.makedirs(_long_path(extracted_output_dir), exist_ok=True)

        cmd = [
            sys.executable,
            str(self.info_extractor_script),
            "-d", str(js_download_dir),
            "-o", str(extracted_output_dir),
            "-j"
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if self.resource_monitor:
                self.resource_monitor.add_pid(process.pid)
            timed_out = False
            try:
                stdout, stderr = process.communicate(timeout=180)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                print(f"[js_info_extractor] timed out after 180s for {js_download_dir}")
                stdout = ""
                stderr = ""
                timed_out = True
            finally:
                if self.resource_monitor:
                    self.resource_monitor.remove_pid(process.pid)

            if not timed_out and process.returncode != 0:
                print(f"[js_info_extractor] exited with code {process.returncode}")
                if stderr:
                    print(f"[js_info_extractor] stderr: {stderr[:500]}")

            # Parse JSON output to get count
            if stdout.strip():
                try:
                    summary = json.loads(stdout.strip())
                    info_count = summary.get('total_findings', 0)
                except Exception as e:
                    print(f"[js_info_extractor] error parsing output: {e}")

        except Exception as e:
            print(f"[js_info_extractor] error: {e}")

        return info_count

    def extract_crawl_urls(self, spider_output_subdir, extracted_output_subdir, base_name):
        """Extract all URLs from gospider crawl output and save as crawl_urls.json"""
        url_pattern = re.compile(
            r'(?:https?://)'
            r'(?:(?:[0-9a-zA-Z_!~*\'().&=+$%-]+:)?[0-9a-zA-Z_!~*\'().&=+$%-]+@)?'
            r'(?:(?:[0-9]{1,3}\.){3}[0-9]{1,3}'
            r'|(?:[0-9a-zA-Z_!~*\'()-]+\.)*(?:[0-9a-zA-Z][0-9a-zA-Z-]{0,61})?[0-9a-zA-Z]\.[a-zA-Z]{2,6})'
            r'(?::[0-9]{1,5})?'
            r'(?:[^\"\'\`\s]*)'
        )

        if not spider_output_subdir.exists():
            return 0

        seen = set()
        crawl_urls = []

        try:
            for filepath in spider_output_subdir.rglob('*'):
                if filepath.is_file():
                    try:
                        with open(_long_path(filepath), 'r', errors='ignore') as f:
                            content = f.read()
                        for match in url_pattern.finditer(content):
                            url = match.group(0).rstrip(');,}>]')
                            if len(url) > 10 and url not in seen:
                                seen.add(url)
                                crawl_urls.append({
                                    "base": base_name,
                                    "source": "gospider",
                                    "url": url,
                                    "type": "crawl"
                                })
                    except Exception:
                        pass
        except Exception:
            pass

        if crawl_urls:
            os.makedirs(_long_path(extracted_output_subdir), exist_ok=True)
            with open(_long_path(extracted_output_subdir / 'crawl_urls.json'), 'w') as f:
                for item in crawl_urls:
                    f.write(json.dumps(item) + '\n')

        return len(crawl_urls)

    def extract_crawl_info(self, spider_output_subdir, extracted_output_subdir, base_name):
        """Extract emails, social links, app links, doc links, and cloud resources from gospider output.

        Runs regex patterns against the raw gospider output text (not just URLs)
        to catch all occurrences of these categories in crawl data.
        """
        if not spider_output_subdir.exists():
            return

        # Read all raw gospider output into a single text block
        raw_content_parts = []
        try:
            for filepath in spider_output_subdir.rglob('*'):
                if filepath.is_file():
                    try:
                        with open(_long_path(filepath), 'r', errors='ignore') as f:
                            raw_content_parts.append(f.read())
                    except Exception:
                        pass
        except Exception:
            pass

        if not raw_content_parts:
            return

        content = '\n'.join(raw_content_parts)
        os.makedirs(_long_path(extracted_output_subdir), exist_ok=True)

        # Compile patterns once
        email_regex = re.compile(EMAIL_PATTERN, re.IGNORECASE)

        social_compiled = {}
        for platform, patterns in SOCIAL_MEDIA_PATTERNS.items():
            social_compiled[platform] = [re.compile(p, re.IGNORECASE) for p in patterns]

        app_compiled = {}
        for store, patterns in APP_LINK_PATTERNS.items():
            app_compiled[store] = [re.compile(p, re.IGNORECASE) for p in patterns]

        doc_compiled = {}
        for service, patterns in DOC_LINK_PATTERNS.items():
            doc_compiled[service] = [re.compile(p, re.IGNORECASE) for p in patterns]

        cloud_compiled = {}
        for provider, patterns in CLOUD_BUCKET_PATTERNS.items():
            cloud_compiled[provider] = [re.compile(p, re.IGNORECASE) for p in patterns]

        # --- Emails ---
        seen_emails = set()
        crawl_emails = []
        for match in email_regex.finditer(content):
            email = match.group(0).lower()
            if email not in seen_emails:
                seen_emails.add(email)
                crawl_emails.append({
                    "base": base_name,
                    "source": "gospider",
                    "email": email,
                    "type": "crawl"
                })

        if crawl_emails:
            with open(_long_path(extracted_output_subdir / 'crawl_emails.json'), 'w') as f:
                for item in crawl_emails:
                    f.write(json.dumps(item) + '\n')

        # --- Social Links ---
        seen_social = set()
        crawl_social = []
        for platform, regexes in social_compiled.items():
            for regex in regexes:
                for match in regex.finditer(content):
                    link = match.group(0).rstrip(');,}>]')
                    if link not in seen_social:
                        seen_social.add(link)
                        crawl_social.append({
                            "base": base_name,
                            "source": "gospider",
                            "type": platform,
                            "link": link,
                            "origin": "crawl"
                        })

        if crawl_social:
            with open(_long_path(extracted_output_subdir / 'crawl_social_links.json'), 'w') as f:
                for item in crawl_social:
                    f.write(json.dumps(item) + '\n')

        # --- App Links ---
        seen_app = set()
        crawl_app = []
        for store, regexes in app_compiled.items():
            for regex in regexes:
                for match in regex.finditer(content):
                    link = match.group(0).rstrip(');,}>]')
                    if link not in seen_app:
                        seen_app.add(link)
                        crawl_app.append({
                            "base": base_name,
                            "source": "gospider",
                            "type": store,
                            "link": link,
                            "origin": "crawl"
                        })

        if crawl_app:
            with open(_long_path(extracted_output_subdir / 'crawl_app_links.json'), 'w') as f:
                for item in crawl_app:
                    f.write(json.dumps(item) + '\n')

        # --- Doc Links ---
        seen_doc = set()
        crawl_doc = []
        for service, regexes in doc_compiled.items():
            for regex in regexes:
                for match in regex.finditer(content):
                    link = match.group(0).rstrip(');,}>]')
                    if link not in seen_doc:
                        seen_doc.add(link)
                        crawl_doc.append({
                            "base": base_name,
                            "source": "gospider",
                            "type": service,
                            "link": link,
                            "origin": "crawl"
                        })

        if crawl_doc:
            with open(_long_path(extracted_output_subdir / 'crawl_doc_links.json'), 'w') as f:
                for item in crawl_doc:
                    f.write(json.dumps(item) + '\n')

        # --- Cloud Resources ---
        seen_cloud = set()
        crawl_cloud = []
        for provider, regexes in cloud_compiled.items():
            for regex in regexes:
                for match in regex.finditer(content):
                    # Use full match URL (not just captured bucket name)
                    bucket = match.group(0)
                    dedup_key = (provider, bucket)
                    if dedup_key not in seen_cloud:
                        seen_cloud.add(dedup_key)
                        crawl_cloud.append({
                            "base": base_name,
                            "source": "gospider",
                            "type": provider,
                            "bucket": bucket,
                            "origin": "crawl"
                        })

        if crawl_cloud:
            with open(_long_path(extracted_output_subdir / 'crawl_cloud_buckets.json'), 'w') as f:
                for item in crawl_cloud:
                    f.write(json.dumps(item) + '\n')

    def run_gospider_with_js_download(self, url_index, url):
        """Run gospider and JS downloader in parallel for a single URL"""
        safe_name = self.get_safe_filename(url)
        spider_output_subdir = self.output_dir / safe_name
        js_download_subdir = self.downloaded_js_dir / safe_name
        secrets_output_subdir = self.secrets_dir / safe_name
        endpoints_output_subdir = self.js_endpoints_dir / safe_name
        extracted_output_subdir = self.js_extracted_dir / safe_name

        # Gospider command
        cmd = [
            _tool_path("gospider"),
            "-s", url,
            "-o", str(spider_output_subdir),
            "-c", str(self.concurrency),
            "-d", str(self.depth),
            "-q"
        ]
        if self.delay > 0:
            cmd.extend(["-k", str(self.delay)])
        if self.cookie:
            cmd.extend(["--cookie", self.cookie])
        for h in self.headers:
            if h.strip():
                cmd.extend(["-H", h.strip()])

        try:
            # ------------------------------------------------------------------
            # Per-file streaming extraction pipeline:
            # As each JS file finishes downloading it is immediately queued for
            # trufflehog / endpoint / info extraction.  The extraction worker
            # runs concurrently with ongoing downloads so the user sees results
            # accumulating in real time instead of waiting for all downloads.
            # ------------------------------------------------------------------

            # Output files — extractors APPEND per-file so results build up live
            th_output_file = secrets_output_subdir / "secrets.json"
            ep_output_file = endpoints_output_subdir / "endpoints.json"

            # Create output dirs before any extraction subprocess is launched
            os.makedirs(_long_path(secrets_output_subdir), exist_ok=True)
            os.makedirs(_long_path(endpoints_output_subdir), exist_ok=True)
            os.makedirs(_long_path(extracted_output_subdir), exist_ok=True)

            _file_queue = _queue_module.Queue()
            _extraction_stop = threading.Event()
            _info_acc = [0]  # mutable so the worker thread can accumulate

            def _extract_one_file(filepath):
                """Run all three JS extractors on a single downloaded file."""
                # 1. Trufflehog — supports 'filesystem <single_file>'
                cmd_th = [
                    _tool_path("trufflehog"), "filesystem",
                    str(filepath), "--json", "--no-update"
                ]
                try:
                    proc_th = subprocess.Popen(
                        cmd_th, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True
                    )
                    if self.resource_monitor:
                        self.resource_monitor.add_pid(proc_th.pid)
                    try:
                        stdout_th, _ = proc_th.communicate(timeout=60)
                    except subprocess.TimeoutExpired:
                        proc_th.kill()
                        proc_th.communicate()
                        stdout_th = ""
                    finally:
                        if self.resource_monitor:
                            self.resource_monitor.remove_pid(proc_th.pid)
                    if stdout_th.strip():
                        # Append NDJSON lines — worker is single-threaded so no lock needed
                        with open(_long_path(th_output_file), 'a') as _f:
                            _f.write(stdout_th if stdout_th.endswith('\n') else stdout_th + '\n')
                except Exception as _e:
                    pass

                # 2. Endpoint extractor — '-f <file>' appends to output file
                if self.extractor_script.exists():
                    cmd_ep = [
                        sys.executable, str(self.extractor_script),
                        "-f", str(filepath),
                        "-o", str(ep_output_file),
                        "-j"
                    ]
                    try:
                        proc_ep = subprocess.Popen(
                            cmd_ep, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True
                        )
                        if self.resource_monitor:
                            self.resource_monitor.add_pid(proc_ep.pid)
                        try:
                            proc_ep.communicate(timeout=30)
                        except subprocess.TimeoutExpired:
                            proc_ep.kill()
                            proc_ep.communicate()
                        finally:
                            if self.resource_monitor:
                                self.resource_monitor.remove_pid(proc_ep.pid)
                    except Exception:
                        pass

                # 3. JS info extractor — '-f <file>' appends to output dir files
                if self.info_extractor_script.exists():
                    cmd_info = [
                        sys.executable, str(self.info_extractor_script),
                        "-f", str(filepath),
                        "-o", str(extracted_output_subdir),
                        "-j"
                    ]
                    try:
                        proc_info = subprocess.Popen(
                            cmd_info, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True
                        )
                        if self.resource_monitor:
                            self.resource_monitor.add_pid(proc_info.pid)
                        try:
                            stdout_info, _ = proc_info.communicate(timeout=60)
                        except subprocess.TimeoutExpired:
                            proc_info.kill()
                            proc_info.communicate()
                            stdout_info = ""
                        finally:
                            if self.resource_monitor:
                                self.resource_monitor.remove_pid(proc_info.pid)
                        if stdout_info.strip():
                            try:
                                _info_acc[0] += json.loads(stdout_info.strip()).get('total_findings', 0)
                            except Exception:
                                pass
                    except Exception:
                        pass

            def _extraction_worker():
                """Drain the per-file queue until stop is signalled and queue is empty."""
                while not (_extraction_stop.is_set() and _file_queue.empty()):
                    try:
                        fp = _file_queue.get(timeout=1)
                        _extract_one_file(fp)
                        _file_queue.task_done()
                    except _queue_module.Empty:
                        continue

            def _on_file_ready(filepath):
                """Callback fired by JSDownloader after each successful file write."""
                _file_queue.put(filepath)

            # Start the extraction worker before the downloader so no file is missed
            extraction_thread = threading.Thread(
                target=_extraction_worker, daemon=True, name="extraction-worker"
            )
            extraction_thread.start()

            # Start gospider (suppress console output, results go to spider_output)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )

            with self.lock:
                self.active_processes[url_index] = process

            if self.resource_monitor:
                self.resource_monitor.add_pid(process.pid)

            # Start JS downloader with per-file callback for streaming extraction
            js_downloader = JSDownloader(
                spider_output_subdir, js_download_subdir,
                target_url=url, on_file_ready=_on_file_ready
            )
            downloader_thread = threading.Thread(target=js_downloader.run, daemon=True)
            downloader_thread.start()

            with self.lock:
                self.active_downloaders[url_index] = js_downloader

            # Wait for gospider to complete
            process.wait()

            # Stop JS downloader (it will do a final pass; callback fires for each file)
            js_downloader.stop()
            downloader_thread.join(timeout=30)

            # Signal extraction worker that no more files are coming, then drain
            _extraction_stop.set()
            extraction_thread.join()

            # Get JS download stats
            js_stats = js_downloader.get_stats()

            if self.resource_monitor:
                self.resource_monitor.remove_pid(process.pid)

            # Collect final counts directly from output files (extractors appended per-file)
            secrets_found = 0
            if th_output_file.exists():
                try:
                    with open(_long_path(th_output_file), 'r') as _f:
                        secrets_found = len([l for l in _f if l.strip()])
                except Exception:
                    pass

            endpoints_found = 0
            if ep_output_file.exists():
                try:
                    with open(_long_path(ep_output_file), 'r') as _f:
                        endpoints_found = len([l for l in _f if l.strip()])
                except Exception:
                    pass

            info_extracted = _info_acc[0]

            # Crawl tasks work on gospider output — run them now in parallel
            def _crawl_urls_task():
                return self.extract_crawl_urls(spider_output_subdir, extracted_output_subdir, safe_name)

            def _crawl_info_task():
                self.extract_crawl_info(spider_output_subdir, extracted_output_subdir, safe_name)

            from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _as_completed
            with _TPE(max_workers=2) as _executor:
                _crawl_futures = {
                    _executor.submit(_crawl_urls_task): 'crawl_urls',
                    _executor.submit(_crawl_info_task): 'crawl_info',
                }
                for _cf in _as_completed(_crawl_futures):
                    try:
                        _cf.result()
                    except Exception:
                        pass

            with self.lock:
                del self.active_processes[url_index]
                if url_index in self.active_downloaders:
                    del self.active_downloaders[url_index]
                self.total_js_downloaded += js_stats['downloaded']
                self.total_js_failed += js_stats['failed']
                self.total_secrets_found += secrets_found
                self.total_endpoints_found += endpoints_found
                self.total_info_extracted += info_extracted
                # Collect failed downloads with target URL
                for js_url, error in js_stats.get('failed_details', []):
                    self.all_failed_downloads.append((url, js_url, error))

            if process.returncode == 0:
                return True, url_index, url, js_stats, secrets_found, endpoints_found, info_extracted
            else:
                return False, url_index, url, js_stats, secrets_found, endpoints_found, info_extracted

        except Exception as e:
            with self.lock:
                if url_index in self.active_processes:
                    del self.active_processes[url_index]
                if url_index in self.active_downloaders:
                    del self.active_downloaders[url_index]
            return False, url_index, f"{url} - Error: {str(e)}", {'downloaded': 0, 'failed': 0, 'failed_details': []}, 0, 0, 0

    def write_live_stats(self, stats, elapsed):
        """Write live stats to JSON file for the web UI"""
        try:
            live_stats_file = self.scan_dir / "live_stats.json"
            with self.lock:
                live_data = {
                    'current_ram_mb': round(stats['current_ram_mb'], 2),
                    'peak_ram_mb': round(stats['peak_ram_mb'], 2),
                    'storage_mb': round(stats['storage_mb'], 2),
                    'completed_urls': self.completed_urls,
                    'total_urls': self.total_urls,
                    'failed_urls': self.failed_urls,
                    'js_downloaded': self.total_js_downloaded,
                    'js_failed': self.total_js_failed,
                    'secrets_found': self.total_secrets_found,
                    'endpoints_found': self.total_endpoints_found,
                    'info_extracted': self.total_info_extracted,
                    'active_processes': len(self.active_processes),
                    'elapsed_seconds': round(elapsed, 1),
                }
            # Write to file (use temp+replace on Unix for atomicity,
            # direct write on Windows to avoid PermissionError when
            # the backend has the file open for reading)
            if os.name == 'nt':
                with open(_long_path(live_stats_file), 'w') as f:
                    json.dump(live_data, f)
            else:
                tmp_file = live_stats_file.with_suffix('.tmp')
                with open(_long_path(tmp_file), 'w') as f:
                    json.dump(live_data, f)
                tmp_file.replace(live_stats_file)
        except Exception:
            pass

    def display_progress(self):
        """Display progress and resource usage"""
        while self.running:
            if self.resource_monitor:
                self.resource_monitor.update()
                stats = self.resource_monitor.get_stats()
            else:
                stats = {'current_ram_mb': 0, 'peak_ram_mb': 0, 'storage_mb': 0}

            elapsed = time.time() - self.start_time if self.start_time else 0
            elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))

            with self.lock:
                active_count = len(self.active_processes)
                js_downloaded = self.total_js_downloaded
                secrets_found = self.total_secrets_found
                endpoints_found = self.total_endpoints_found
                info_extracted = self.total_info_extracted

            progress = (self.completed_urls / self.total_urls * 100) if self.total_urls > 0 else 0

            # Write live stats for the web UI
            self.write_live_stats(stats, elapsed)

            bar_width = 20
            filled = int(bar_width * progress / 100)
            bar = '█' * filled + '░' * (bar_width - filled)

            status = (
                f"\r{Colors.BOLD}[{bar}] {progress:5.1f}%{Colors.RESET} | "
                f"{Colors.GREEN}Done: {self.completed_urls}/{self.total_urls}{Colors.RESET} | "
                f"{Colors.YELLOW}Active: {active_count}{Colors.RESET} | "
                f"{Colors.BLUE}JS: {js_downloaded}{Colors.RESET} | "
                f"{Colors.RED}Secrets: {secrets_found}{Colors.RESET} | "
                f"{Colors.CYAN}Endpoints: {endpoints_found}{Colors.RESET} | "
                f"{Colors.WHITE}Info: {info_extracted}{Colors.RESET} | "
                f"{Colors.MAGENTA}RAM: {stats['current_ram_mb']:.1f}MB (Peak: {stats['peak_ram_mb']:.1f}MB){Colors.RESET} | "
                f"{Colors.YELLOW}Disk: {stats['storage_mb']:.1f}MB{Colors.RESET} | "
                f"{Colors.GREEN}{elapsed_str}{Colors.RESET}    "
            )

            print(status, end='', flush=True)
            time.sleep(1)

    def run_scan(self):
        """Execute the scan"""
        print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*60}")
        print(f"  JS Discovery Scanner - Starting Scan")
        print(f"{'='*60}{Colors.RESET}\n")

        self.setup_directories()
        self.load_urls()

        if self.total_urls == 0:
            print(f"{Colors.RED}[!] No URLs to scan{Colors.RESET}")
            return

        self.resource_monitor = ResourceMonitor(self.scan_dir)
        # Track the scanner process itself for RAM measurement
        self.resource_monitor.add_pid(os.getpid())

        self.start_time = time.time()
        progress_thread = threading.Thread(target=self.display_progress, daemon=True)
        progress_thread.start()

        print(f"\n{Colors.CYAN}[*] Starting scan with {self.max_parallel} parallel processes...{Colors.RESET}")
        print(f"{Colors.CYAN}[*] Pipeline: Gospider -> JS Download -> Trufflehog -> Endpoints -> Info Extractor{Colors.RESET}\n")

        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            futures = {}
            for i, url in enumerate(self.urls, 1):
                if not self.running:
                    break
                future = executor.submit(self.run_gospider_with_js_download, i, url)
                futures[future] = (i, url)

            for future in as_completed(futures):
                if not self.running:
                    break

                try:
                    success, url_index, result, js_stats, secrets, endpoints, info = future.result()
                    with self.lock:
                        self.completed_urls += 1
                        if not success:
                            self.failed_urls += 1
                except Exception as e:
                    with self.lock:
                        self.completed_urls += 1
                        self.failed_urls += 1

        self.running = False
        time.sleep(1.5)

        self.print_final_stats()

    def print_final_stats(self):
        """Print final scan statistics"""
        elapsed = time.time() - self.start_time
        elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))

        if self.resource_monitor:
            self.resource_monitor.update()
            stats = self.resource_monitor.get_stats()
        else:
            stats = {'current_ram_mb': 0, 'peak_ram_mb': 0, 'storage_mb': 0}

        print(f"\n\n{Colors.BOLD}{Colors.GREEN}{'='*60}")
        print(f"  Scan Complete!")
        print(f"{'='*60}{Colors.RESET}")
        print(f"\n{Colors.CYAN}Scan Statistics:{Colors.RESET}")
        print(f"  • Scan Name: {self.scan_name}")
        print(f"  • Total URLs: {self.total_urls}")
        print(f"  • Successful: {Colors.GREEN}{self.completed_urls - self.failed_urls}{Colors.RESET}")
        print(f"  • Failed: {Colors.RED}{self.failed_urls}{Colors.RESET}")
        print(f"  • Duration: {elapsed_str}")
        print(f"\n{Colors.BLUE}JS Download Statistics:{Colors.RESET}")
        print(f"  • JS Files Downloaded: {Colors.GREEN}{self.total_js_downloaded}{Colors.RESET}")
        print(f"  • JS Downloads Failed: {Colors.RED}{self.total_js_failed}{Colors.RESET}")
        print(f"\n{Colors.RED}Trufflehog Results:{Colors.RESET}")
        print(f"  • Secrets Found: {Colors.RED if self.total_secrets_found > 0 else Colors.GREEN}{self.total_secrets_found}{Colors.RESET}")
        print(f"\n{Colors.CYAN}Endpoint Extraction Results:{Colors.RESET}")
        print(f"  • Endpoints Found: {Colors.GREEN}{self.total_endpoints_found}{Colors.RESET}")
        print(f"\n{Colors.WHITE}JS Info Extraction Results:{Colors.RESET}")
        print(f"  • Total Info Found: {Colors.GREEN}{self.total_info_extracted}{Colors.RESET}")
        print(f"  • (IPs, Emails, Domains, Cloud Buckets, Doc Links, App Links)")
        print(f"\n{Colors.MAGENTA}Resource Usage:{Colors.RESET}")
        print(f"  • Peak RAM: {stats['peak_ram_mb']:.2f} MB")
        print(f"  • Storage Used: {stats['storage_mb']:.2f} MB")
        print(f"\n{Colors.YELLOW}Output Location:{Colors.RESET}")
        print(f"  • Scan Directory: {self.scan_dir}")
        print(f"  • Spider Output: {self.output_dir}")
        print(f"  • Downloaded JS: {self.downloaded_js_dir}")
        print(f"  • Secrets Results: {self.secrets_dir}")
        print(f"  • JS Endpoints: {self.js_endpoints_dir}")
        print(f"  • JS Extracted Info: {self.js_extracted_dir}")

        # Save final report
        report_file = self.scan_dir / "scan_report.txt"
        with open(_long_path(report_file), 'w') as f:
            f.write(f"JS Discovery Scanner - Final Report\n")
            f.write(f"{'='*50}\n\n")
            f.write(f"Scan Name: {self.scan_name}\n")
            f.write(f"Input File: {self.input_file}\n")
            f.write(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Duration: {elapsed_str}\n\n")
            f.write(f"Scan Results:\n")
            f.write(f"  Total URLs: {self.total_urls}\n")
            f.write(f"  Successful: {self.completed_urls - self.failed_urls}\n")
            f.write(f"  Failed: {self.failed_urls}\n\n")
            f.write(f"JS Download Results:\n")
            f.write(f"  JS Files Downloaded: {self.total_js_downloaded}\n")
            f.write(f"  JS Downloads Failed: {self.total_js_failed}\n\n")
            f.write(f"Trufflehog Results:\n")
            f.write(f"  Secrets Found: {self.total_secrets_found}\n\n")
            f.write(f"Endpoint Extraction Results:\n")
            f.write(f"  Endpoints Found: {self.total_endpoints_found}\n\n")
            f.write(f"JS Info Extraction Results:\n")
            f.write(f"  Total Info Found: {self.total_info_extracted}\n")
            f.write(f"  (IPs, Emails, Domains, Cloud Buckets, Doc Links, App Links)\n\n")
            f.write(f"Resource Usage:\n")
            f.write(f"  Peak RAM: {stats['peak_ram_mb']:.2f} MB\n")
            f.write(f"  Storage Used: {stats['storage_mb']:.2f} MB\n")

        print(f"\n{Colors.GREEN}[+] Report saved to: {report_file}{Colors.RESET}")

        # Write final live_stats.json so frontend picks up completed stats
        self.write_live_stats(stats, elapsed)

        # Save failed downloads summary
        if self.all_failed_downloads:
            failed_summary_file = self.scan_dir / "failed_js_downloads.json"

            # Group by error type for summary
            error_counts = {}
            for _, _, error in self.all_failed_downloads:
                error_type = error.split(':')[0] if ':' in error else error
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

            # Group by target URL
            by_target = {}
            for target_url, js_url, error in self.all_failed_downloads:
                if target_url not in by_target:
                    by_target[target_url] = []
                by_target[target_url].append({'js_url': js_url, 'error': error})

            data = {
                'total_failed': len(self.all_failed_downloads),
                'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'error_summary': error_counts,
                'by_target': by_target
            }

            with open(_long_path(failed_summary_file), 'w') as f:
                json.dump(data, f, indent=2)

            print(f"{Colors.YELLOW}[!] Failed downloads log: {failed_summary_file}{Colors.RESET}\n")
        else:
            print()

    def cleanup(self):
        """Cleanup running processes on interrupt"""
        print(f"\n{Colors.YELLOW}[!] Interrupt received, cleaning up...{Colors.RESET}")
        self.running = False

        # Stop all JS downloaders
        with self.lock:
            for url_index, downloader in list(self.active_downloaders.items()):
                try:
                    downloader.stop()
                except Exception:
                    pass

        # Terminate all gospider processes
        with self.lock:
            for url_index, process in list(self.active_processes.items()):
                try:
                    if os.name != 'nt':
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    else:
                        process.terminate()
                    print(f"{Colors.YELLOW}[!] Terminated process {url_index}{Colors.RESET}")
                except Exception:
                    pass


def main():
    parser = argparse.ArgumentParser(
        description='JS Discovery Scanner - Full JS Analysis Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline: Gospider -> JS Download -> Trufflehog -> Endpoints -> Info Extractor (all parallel per URL)

Info Extractor finds: IPs, Emails, Domains, Cloud Buckets, Doc Links, App Links

Examples:
  python js_scanner.py -i urls.txt
  python js_scanner.py -i urls.txt -n my_scan -p 5
  python js_scanner.py -i final-httpx.txt -n my_scan -p 3 -c 5
        """
    )

    parser.add_argument('-i', '--input', type=str, help='Input file containing URLs')
    parser.add_argument('-n', '--name', type=str, help='Scan name (creates folder with this name)')
    parser.add_argument('-p', '--parallel', type=int, default=3, help='Max parallel processes (default: 3)')
    parser.add_argument('-c', '--concurrency', type=int, default=2, help='Gospider concurrency (default: 2)')
    parser.add_argument('-f', '--force', action='store_true', help='Force overwrite existing scan without prompting')
    parser.add_argument('-d', '--depth', type=int, default=1, help='Max crawl depth (0 for infinite, default: 1)')
    parser.add_argument('-k', '--delay', type=int, default=0, help='Delay between requests to same domain in seconds (default: 0)')
    parser.add_argument('--cookie', type=str, default='', help='Cookie to use for gospider (e.g., "testA=a; testB=b")')
    parser.add_argument('-H', '--header', action='append', default=[], help='Header to use for gospider (use multiple -H for multiple headers)')

    args = parser.parse_args()

    if not args.input:
        # Check if running in interactive mode
        if sys.stdin.isatty():
            print(f"\n{Colors.BOLD}{Colors.CYAN}JS Discovery Scanner{Colors.RESET}")
            print(f"{Colors.WHITE}{'─'*40}{Colors.RESET}\n")

            args.input = input(f"{Colors.YELLOW}Enter input file path: {Colors.RESET}").strip()
            if not args.input:
                print(f"{Colors.RED}[!] Input file is required{Colors.RESET}")
                sys.exit(1)
        else:
            print(f"{Colors.RED}[!] Input file is required (use -i flag){Colors.RESET}")
            sys.exit(1)

    if not args.name:
        default_name = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # Check if running in interactive mode
        if sys.stdin.isatty():
            args.name = input(f"{Colors.YELLOW}Enter scan name [{default_name}]: {Colors.RESET}").strip()
            if not args.name:
                args.name = default_name
        else:
            args.name = default_name

    if not os.path.exists(args.input):
        print(f"{Colors.RED}[!] Error: Input file not found: {args.input}{Colors.RESET}")
        sys.exit(1)

    run_script = "run.ps1" if os.name == "nt" else "run.sh"
    gospider_path = _tool_path("gospider")
    if gospider_path == "gospider" and shutil.which("gospider") is None:
        print(f"{Colors.RED}[!] Error: gospider not found in scanner/bin/ or system PATH{Colors.RESET}")
        print(f"{Colors.YELLOW}[*] Run {run_script} to auto-download, or install manually{Colors.RESET}")
        sys.exit(1)

    trufflehog_path = _tool_path("trufflehog")
    if trufflehog_path == "trufflehog" and shutil.which("trufflehog") is None:
        print(f"{Colors.RED}[!] Error: trufflehog not found in scanner/bin/ or system PATH{Colors.RESET}")
        print(f"{Colors.YELLOW}[*] Run {run_script} to auto-download, or install manually{Colors.RESET}")
        sys.exit(1)

    scanner = JSScanner(
        input_file=args.input,
        scan_name=args.name,
        max_parallel=args.parallel,
        concurrency=args.concurrency,
        force=args.force,
        depth=args.depth,
        delay=args.delay,
        cookie=args.cookie,
        headers=args.header
    )

    def signal_handler(sig, frame):
        scanner.cleanup()
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)

    scanner.run_scan()


if __name__ == "__main__":
    main()
