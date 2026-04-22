"""
Scan result parsing service
"""

import os
import re
import json
from pathlib import Path
from flask import current_app
from backend.utils.filename import safe_filename_to_url, safe_dirname_to_url


def _long_path(p):
    """On Windows, prefix path with \\\\?\\ to bypass the 260-char MAX_PATH limit."""
    s = str(p)
    if os.name == 'nt' and not s.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(s)
    return s


def get_scan_directory(scan_name):
    """Get the directory for a scan"""
    return current_app.config['SCANS_DIR'] / scan_name


def _load_url_maps(scan_dir):
    """Load all url_map.json files from downloaded-js subdirectories.
    Returns a combined dict mapping safe filenames to original URLs."""
    url_map = {}
    downloaded_js_dir = Path(scan_dir) / 'downloaded-js'
    if downloaded_js_dir.exists():
        for subdir in downloaded_js_dir.iterdir():
            if subdir.is_dir():
                map_file = subdir / 'url_map.json'
                if map_file.exists():
                    try:
                        with open(_long_path(map_file), 'r') as f:
                            url_map.update(json.load(f))
                    except Exception:
                        pass
    return url_map


def _resolve_filename(safe_name, url_map):
    """Resolve a safe filename to original URL using url_map, falling back to safe_filename_to_url."""
    if safe_name and safe_name in url_map:
        return url_map[safe_name]
    # Try with .js extension stripped
    if safe_name and safe_name.endswith('.js') and safe_name[:-3] in url_map:
        return url_map[safe_name[:-3]]
    return safe_filename_to_url(safe_name)


def read_live_stats(scan_dir):
    """Read live_stats.json written by a running scan process"""
    live_stats_file = Path(scan_dir) / 'live_stats.json'
    if live_stats_file.exists():
        try:
            with open(_long_path(live_stats_file), 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return None


def calculate_directory_size_mb(directory):
    """Calculate total size of a directory in MB"""
    total_size = 0
    directory = Path(directory)
    if directory.exists():
        for f in directory.rglob('*'):
            if f.is_file():
                try:
                    total_size += os.path.getsize(_long_path(f))
                except OSError:
                    pass
    return round(total_size / (1024 * 1024), 2)


def parse_scan_results(scan_dir):
    """Parse scan results from the scan directory"""
    results = {
        'secrets': [],
        'endpoints': [],
        'parameters': [],
        'cloud_resources': [],
        'subdomains': [],
        'ips': [],
        'files': [],
        'emails': [],
        'app_links': [],
        'doc_links': [],
        'social_links': [],
        'urls': [],
        'stats': {}
    }

    scan_dir = Path(scan_dir)
    if not scan_dir.exists():
        return results

    # Load filename-to-URL mappings
    url_map = _load_url_maps(scan_dir)

    # Always calculate storage from disk as fallback
    results['stats']['storage_mb'] = calculate_directory_size_mb(scan_dir)

    # Parse scan report for stats
    report_file = scan_dir / 'scan_report.txt'
    if report_file.exists():
        try:
            with open(_long_path(report_file), 'r') as f:
                content = f.read()
                total_match = re.search(r'Total URLs:\s*(\d+)', content)
                if total_match:
                    results['stats']['total_urls'] = int(total_match.group(1))

                successful_match = re.search(r'Successful:\s*(\d+)', content)
                if successful_match:
                    results['stats']['successful_urls'] = int(successful_match.group(1))

                failed_match = re.search(r'Failed:\s*(\d+)', content)
                if failed_match:
                    results['stats']['failed_urls'] = int(failed_match.group(1))

                js_dl_match = re.search(r'JS Files Downloaded:\s*(\d+)', content)
                if js_dl_match:
                    results['stats']['js_downloaded'] = int(js_dl_match.group(1))

                js_fail_match = re.search(r'JS Downloads Failed:\s*(\d+)', content)
                if js_fail_match:
                    results['stats']['js_failed'] = int(js_fail_match.group(1))

                secrets_match = re.search(r'Secrets Found:\s*(\d+)', content)
                if secrets_match:
                    results['stats']['secrets_count'] = int(secrets_match.group(1))

                endpoints_match = re.search(r'Endpoints Found:\s*(\d+)', content)
                if endpoints_match:
                    results['stats']['endpoints_count'] = int(endpoints_match.group(1))

                peak_ram_match = re.search(r'Peak RAM:\s*([\d.]+)\s*MB', content)
                if peak_ram_match:
                    results['stats']['peak_ram_mb'] = float(peak_ram_match.group(1))

                storage_match = re.search(r'Storage Used:\s*([\d.]+)\s*MB', content)
                if storage_match:
                    results['stats']['storage_mb'] = float(storage_match.group(1))
        except Exception as e:
            print(f"Error parsing report: {e}")

    # Parse secrets results
    secrets_dir = scan_dir / 'secrets'
    if secrets_dir.exists():
        secret_id = 1
        for subdir in secrets_dir.iterdir():
            if subdir.is_dir():
                secrets_file = subdir / 'secrets.json'
                if secrets_file.exists():
                    try:
                        with open(_long_path(secrets_file), 'r') as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    try:
                                        secret_data = json.loads(line)
                                        raw_file = secret_data.get('SourceMetadata', {}).get('Data', {}).get('Filesystem', {}).get('file', 'unknown')
                                        results['secrets'].append({
                                            'id': secret_id,
                                            'type': secret_data.get('DetectorName', 'Unknown'),
                                            'value': secret_data.get('Raw', secret_data.get('Redacted', '***')),
                                            'file': _resolve_filename(os.path.basename(raw_file), url_map),
                                            'base': safe_dirname_to_url(subdir.name),
                                            'line': secret_data.get('SourceMetadata', {}).get('Data', {}).get('Filesystem', {}).get('line', 0),
                                            'severity': 'high' if secret_data.get('Verified', False) else 'medium'
                                        })
                                        secret_id += 1
                                    except json.JSONDecodeError:
                                        pass
                    except Exception as e:
                        print(f"Error parsing secrets: {e}")

    # Parse endpoints
    endpoints_dir = scan_dir / 'js-endpoints'
    if endpoints_dir.exists():
        endpoint_id = 1
        for subdir in endpoints_dir.iterdir():
            if subdir.is_dir():
                endpoints_file = subdir / 'endpoints.json'
                if endpoints_file.exists():
                    try:
                        with open(_long_path(endpoints_file), 'r') as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    try:
                                        ep_data = json.loads(line)
                                        # Read category from JSON key set by endpoint_extractor.py
                                        if 'parameter' in ep_data:
                                            ep_type = 'Parameter'
                                            url = ep_data['parameter']
                                        elif 'endpoints-params' in ep_data:
                                            ep_type = 'Endpoint-Param'
                                            url = ep_data['endpoints-params']
                                        else:
                                            ep_type = 'Endpoint'
                                            url = ep_data.get('endpoint', '')

                                        results['endpoints'].append({
                                            'id': endpoint_id,
                                            'url': url,
                                            'type': ep_type,
                                            'file': _resolve_filename(ep_data.get('source', 'unknown'), url_map),
                                            'base': safe_dirname_to_url(ep_data.get('base', '')),
                                            'line': 0
                                        })
                                        endpoint_id += 1
                                    except json.JSONDecodeError:
                                        pass
                    except Exception as e:
                        print(f"Error parsing endpoints: {e}")

    # Parse JS extracted info (domains, IPs, cloud resources)
    extracted_dir = scan_dir / 'js-extracted'
    if extracted_dir.exists():
        for subdir in extracted_dir.iterdir():
            if subdir.is_dir():
                _parse_domains(subdir, results, url_map)
                _parse_ips(subdir, results, url_map)
                _parse_cloud_buckets(subdir, results, url_map)
                _parse_emails(subdir, results, url_map)
                _parse_app_links(subdir, results, url_map)
                _parse_doc_links(subdir, results, url_map)
                _parse_social_links(subdir, results, url_map)
                _parse_urls(subdir, results, url_map)

    # Get downloaded files
    downloaded_js_dir = scan_dir / 'downloaded-js'
    if downloaded_js_dir.exists():
        file_id = 1
        for subdir in downloaded_js_dir.iterdir():
            if subdir.is_dir():
                base_url = safe_dirname_to_url(subdir.name)

                for js_file in subdir.glob('*.js'):
                    try:
                        size = os.path.getsize(_long_path(js_file))
                        size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
                        url_name = _resolve_filename(js_file.name, url_map)
                        results['files'].append({
                            'id': file_id,
                            'filename': url_name,
                            'url': url_name,
                            'baseUrl': base_url,
                            'size': size_str,
                            'type': 'JavaScript',
                            'downloaded': True
                        })
                        file_id += 1
                    except Exception:
                        pass

    return results


def _parse_domains(subdir, results, url_map):
    domains_file = subdir / 'domains.json'
    if not domains_file.exists():
        return
    subdomain_id = len(results['subdomains']) + 1
    try:
        with open(_long_path(domains_file), 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        results['subdomains'].append({
                            'id': subdomain_id,
                            'subdomain': data.get('domain', ''),
                            'file': _resolve_filename(data.get('source', 'unknown'), url_map),
                            'base': safe_dirname_to_url(data.get('base', '')),
                            'status': data.get('status', 'unknown'),
                            'line': 0
                        })
                        subdomain_id += 1
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass


def _parse_ips(subdir, results, url_map):
    ips_file = subdir / 'ip_addresses.json'
    if not ips_file.exists():
        return
    ip_id = len(results['ips']) + 1
    try:
        with open(_long_path(ips_file), 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        results['ips'].append({
                            'id': ip_id,
                            'ip': data.get('ip', ''),
                            'file': _resolve_filename(data.get('source', 'unknown'), url_map),
                            'base': safe_dirname_to_url(data.get('base', '')),
                            'line': 0
                        })
                        ip_id += 1
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass


def _parse_cloud_buckets(subdir, results, url_map):
    type_mapping = {
        'aws_s3': 'S3 Bucket',
        'gcp': 'Google Cloud',
        'azure': 'Azure Blob',
        'alibaba_oss': 'Alibaba OSS',
        'digitalocean_spaces': 'DigitalOcean Spaces'
    }
    for filename, source_tag in [('cloud_buckets.json', 'js'), ('crawl_cloud_buckets.json', 'crawl')]:
        filepath = subdir / filename
        if not filepath.exists():
            continue
        cloud_id = len(results['cloud_resources']) + 1
        try:
            with open(_long_path(filepath), 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            bucket_type = data.get('type', 'unknown')
                            results['cloud_resources'].append({
                                'id': cloud_id,
                                'type': type_mapping.get(bucket_type, bucket_type),
                                'url': data.get('bucket', ''),
                                'file': _resolve_filename(data.get('source', 'unknown'), url_map),
                                'base': safe_dirname_to_url(data.get('base', '')),
                                'source': source_tag,
                                'line': 0
                            })
                            cloud_id += 1
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass


def _parse_emails(subdir, results, url_map):
    for filename, source_tag in [('emails.json', 'js'), ('crawl_emails.json', 'crawl')]:
        filepath = subdir / filename
        if not filepath.exists():
            continue
        email_id = len(results['emails']) + 1
        try:
            with open(_long_path(filepath), 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            results['emails'].append({
                                'id': email_id,
                                'email': data.get('email', ''),
                                'file': _resolve_filename(data.get('source', 'unknown'), url_map),
                                'base': safe_dirname_to_url(data.get('base', '')),
                                'source': source_tag,
                                'line': 0
                            })
                            email_id += 1
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass


def _parse_app_links(subdir, results, url_map):
    type_mapping = {
        'play_store': 'Play Store',
        'app_store': 'App Store',
        'google_play': 'Play Store',
        'apple_store': 'App Store'
    }
    for filename, source_tag in [('app_links.json', 'js'), ('crawl_app_links.json', 'crawl')]:
        filepath = subdir / filename
        if not filepath.exists():
            continue
        app_id = len(results['app_links']) + 1
        try:
            with open(_long_path(filepath), 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            link_type = data.get('type', 'unknown')
                            results['app_links'].append({
                                'id': app_id,
                                'type': type_mapping.get(link_type, link_type),
                                'url': data.get('link', data.get('url', '')),
                                'file': _resolve_filename(data.get('source', 'unknown'), url_map),
                                'base': safe_dirname_to_url(data.get('base', '')),
                                'source': source_tag,
                                'line': 0
                            })
                            app_id += 1
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass


def _parse_doc_links(subdir, results, url_map):
    for filename, source_tag in [('doc_links.json', 'js'), ('crawl_doc_links.json', 'crawl')]:
        filepath = subdir / filename
        if not filepath.exists():
            continue
        doc_id = len(results['doc_links']) + 1
        try:
            with open(_long_path(filepath), 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            results['doc_links'].append({
                                'id': doc_id,
                                'url': data.get('url', data.get('link', '')),
                                'type': data.get('type', 'Documentation'),
                                'file': _resolve_filename(data.get('source', 'unknown'), url_map),
                                'base': safe_dirname_to_url(data.get('base', '')),
                                'source': source_tag,
                                'line': 0
                            })
                            doc_id += 1
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass


def _parse_social_links(subdir, results, url_map):
    type_mapping = {
        'facebook': 'Facebook',
        'instagram': 'Instagram',
        'twitter': 'Twitter/X',
        'linkedin': 'LinkedIn',
        'youtube': 'YouTube',
        'tiktok': 'TikTok',
        'pinterest': 'Pinterest',
        'reddit': 'Reddit',
        'snapchat': 'Snapchat',
        'telegram': 'Telegram',
        'whatsapp': 'WhatsApp',
        'discord': 'Discord',
        'github': 'GitHub',
        'medium': 'Medium',
        'tumblr': 'Tumblr',
        'twitch': 'Twitch',
        'vimeo': 'Vimeo',
    }
    for filename, source_tag in [('social_links.json', 'js'), ('crawl_social_links.json', 'crawl')]:
        filepath = subdir / filename
        if not filepath.exists():
            continue
        social_id = len(results['social_links']) + 1
        try:
            with open(_long_path(filepath), 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            link_type = data.get('type', 'unknown')
                            results['social_links'].append({
                                'id': social_id,
                                'type': type_mapping.get(link_type, link_type),
                                'url': data.get('link', data.get('url', '')),
                                'file': _resolve_filename(data.get('source', 'unknown'), url_map),
                                'base': safe_dirname_to_url(data.get('base', '')),
                                'source': source_tag,
                                'line': 0
                            })
                            social_id += 1
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass


def _parse_urls(subdir, results, url_map):
    url_id = len(results['urls']) + 1

    # Parse JS-extracted URLs (from JS file analysis)
    urls_file = subdir / 'urls.json'
    if urls_file.exists():
        try:
            with open(_long_path(urls_file), 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            results['urls'].append({
                                'id': url_id,
                                'url': data.get('url', ''),
                                'file': _resolve_filename(data.get('source', 'unknown'), url_map),
                                'base': safe_dirname_to_url(data.get('base', '')),
                                'source': data.get('type', 'js'),
                                'line': 0
                            })
                            url_id += 1
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass

    # Parse crawl URLs (from gospider output)
    crawl_file = subdir / 'crawl_urls.json'
    if crawl_file.exists():
        try:
            with open(_long_path(crawl_file), 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            results['urls'].append({
                                'id': url_id,
                                'url': data.get('url', ''),
                                'file': data.get('source', 'gospider'),
                                'base': safe_dirname_to_url(data.get('base', '')),
                                'source': 'crawl',
                                'line': 0
                            })
                            url_id += 1
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
