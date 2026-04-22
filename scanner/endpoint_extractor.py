#!/usr/bin/env python3
import argparse
import os
import re
import json
from pathlib import Path


def _long_path(p):
    """On Windows, prefix path with \\\\?\\ to bypass the 260-char MAX_PATH limit."""
    s = str(p)
    if os.name == 'nt' and not s.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(s)
    return s

# ================= YOUR EXACT REGEX =================
REGEX_PATTERNS = [
    r'"\?(.*?)"',
    r'"\/(.*?)"',
    r"'\/(.*?)'",
    r"`\/(.*?)`",
    r'this\.fetch\(this\.url\("([^"]+)"\)\)'
]

compiled = [re.compile(r) for r in REGEX_PATTERNS]

# Default static junk filters
DEFAULT_SKIP = [
    ".png", ".jpg", ".gif", ".jpeg", ".swf", ".woff", ".woff2", ".svg", ".css", ".ico",
    ".ttf", ".doc", ".pdf", ".docx", ".pptx", ".bmp", ".tiff", ".mp4", ".avi", ".mkv", ".mov",
    ".flv", ".wmv", ".webm", ".heic", ".webp", ".otf", ".eot", ".mp3", ".wav", ".aac", ".flac",
    ".ogg", ".m4a", ".tif", ".heif", ".psd", ".eps", ".ai", ".wma", ".opus", ".m4v", ".sfnt",
    ".ppt", ".odp", ".apng", ".jp2", ".jxl", ".emf", ".wmf", ".indd", ".sketch", ".xcf", ".alac",
    ".aiff", ".aif", ".mid", ".midi", ".amr", ".ra", ".3gp", ".3g2", ".mpe", ".mpeg", ".mpg",
    ".mts", ".m2ts", ".vob", ".ogv", ".rm", ".rmvb", ".fon", ".pfb", ".pfa", ".epub", ".mobi",
    ".prc", ".lit", ".scss", ".less", ".blend", ".fbx", ".obj", ".stl", ".glb", ".gltf",
    ".c4d", ".zip", ".rar", ".7z"
]

counter = 1

# ================= CORE =================
def is_valid(match):
    if len(match) < 3:
        return False
    if re.search(r'[ <>|{}\[\]^*+]', match):
        return False
    return True

def extract(content, skip_list):
    found = set()
    results = []

    for regex in compiled:
        for m in regex.finditer(content):
            match = m.group(0)
            match = match.strip("\"'`")

            if not is_valid(match):
                continue

            # Apply skip filter
            if skip_list:
                for s in skip_list:
                    if s.lower() in match.lower():
                        break
                else:
                    if match not in found:
                        found.add(match)
                        results.append(match)
            else:
                if match not in found:
                    found.add(match)
                    results.append(match)

    return results

# ================= FETCH =================
def fetch_url(url):
    try:
        import requests
        r = requests.get(url, timeout=7, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200:
            return r.text
    except:
        pass
    return None

# ================= CATEGORIZE =================
def categorize(value):
    """Categorize extracted value by URL structure"""
    if value.startswith('?'):
        return 'parameter'
    elif '?' in value:
        return 'endpoints-params'
    else:
        return 'endpoint'

# ================= OUTPUT =================
def write_result(source, value, json_mode, out_file, base=""):
    global counter

    if json_mode:
        category = categorize(value)
        obj = {"base": base, "source": source, category: value}
        line = json.dumps(obj)
        print(line)
        if out_file:
            with open(_long_path(out_file), "a") as f:
                f.write(line + "\n")
    else:
        print(f"[ {counter} ] {source} : {value}")
        if out_file:
            with open(_long_path(out_file), "a") as f:
                f.write(f"{source} : {value}\n")

    counter += 1

# ================= PROCESS =================
def process(source, content, json_mode, out_file, skip_list, base=""):
    endpoints = extract(content, skip_list)
    for ep in endpoints:
        write_result(source, ep, json_mode, out_file, base)

# ================= MAIN =================
parser = argparse.ArgumentParser()
parser.add_argument("-u", help="Single JS URL")
parser.add_argument("-l", help="File containing JS URLs")
parser.add_argument("-f", help="Single downloaded JS file")
parser.add_argument("-d", help="Directory of downloaded JS files")
parser.add_argument("-o", help="Output file")
parser.add_argument("-j", action="store_true", help="JSON output")
parser.add_argument("--skip", help="Extra keywords/extensions to skip (comma-separated)")
parser.add_argument("--no-skip", action="store_true", help="Disable all skipping (show everything)")
args = parser.parse_args()

# Build skip list
if args.no_skip:
    skip_list = []   # disable all filtering
else:
    skip_list = DEFAULT_SKIP.copy()
    if args.skip:
        skip_list.extend([x.strip() for x in args.skip.split(",")])

# URL list
if args.l:
    with open(args.l) as f:
        for url in f:
            url = url.strip()
            data = fetch_url(url)
            if data:
                process(url, data, args.j, args.o, skip_list)

# Single URL
if args.u:
    data = fetch_url(args.u)
    if data:
        process(args.u, data, args.j, args.o, skip_list)

# Single file
if args.f:
    with open(_long_path(args.f), errors="ignore") as f:
        process(Path(args.f).name, f.read(), args.j, args.o, skip_list)

# Directory - base is the directory name (e.g. "admin2.tesla.com")
if args.d:
    base = Path(args.d).name
    for root, dirs, files in os.walk(args.d):
        for file in files:
            if file.endswith(".js.txt") or file.endswith(".js"):
                path = os.path.join(root, file)
                with open(_long_path(path), errors="ignore") as f:
                    process(file, f.read(), args.j, args.o, skip_list, base)
