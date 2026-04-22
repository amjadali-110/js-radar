#!/usr/bin/env python3
"""
JS Info Extractor - Extract sensitive information from JavaScript files
Extracts: Cloud Buckets, IP Addresses, Emails, Domains, Doc Links, App Links
"""

import argparse
import os
import re
import json
import ssl
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

def _long_path(p):
    """On Windows, prefix path with \\\\?\\ to bypass the 260-char MAX_PATH limit."""
    s = str(p)
    if os.name == 'nt' and not s.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(s)
    return s

# Bundled binaries directory (scanner/bin/)
_BIN_DIR = Path(__file__).parent / "bin"

def _tool_path(name):
    """Return path to a tool binary: use scanner/bin/ if present, else fall back to system PATH."""
    candidates = [_BIN_DIR / name, _BIN_DIR / f"{name}.exe"] if os.name == 'nt' else [_BIN_DIR / name]
    for local in candidates:
        if local.is_file():
            return str(local)
    return name

# ================= REGEX PATTERNS =================

# IP Addresses — real IPs never have a digit or dot immediately adjacent.
# The negative lookbehind/lookahead reject partial matches inside SVG path
# data, concatenated decimals (e.g. "00.09.05.12.12"), version strings, etc.
IP_PATTERN = (
    r'(?<![.\d])'
    r'(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)'
    r'(?![.\d])'
)

# Emails
EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

# Full URLs — matches http/https URLs with optional auth, IP or domain host, optional port, and path
URL_PATTERN = (
    r'(?:https?://)'
    r'(?:(?:[0-9a-zA-Z_!~*\'().&=+$%-]+:)?[0-9a-zA-Z_!~*\'().&=+$%-]+@)?'
    r'(?:(?:[0-9]{1,3}\.){3}[0-9]{1,3}'
    r'|(?:[0-9a-zA-Z_!~*\'()-]+\.)*(?:[0-9a-zA-Z][0-9a-zA-Z-]{0,61})?[0-9a-zA-Z]\.[a-zA-Z]{2,6})'
    r'(?::[0-9]{1,5})?'
    r'(?:[^\"\'\`\s]*)'
)

# ================= DOMAIN EXTRACTION PATTERNS =================
# Domains are extracted ONLY from the contexts where they genuinely appear
# in JS files, eliminating false positives from JS property/method chains
# (e.g. window.nreum.info, console.error, host.includes).
#
# One RFC-compliant DNS label: starts/ends alphanumeric, hyphens allowed inside
_DNS_LABEL = r'[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
# Full domain: one-or-more label+dot groups, then a TLD (letters only).
# The negative lookahead rejects partial matches where the "TLD" is followed
# by more letters (truncated TLD), a hyphen (mid-label, e.g. google in
# google-analytics), or a dot (more labels the regex couldn't consume).
_DNS_DOMAIN = r'(?:' + _DNS_LABEL + r'\.)+[a-zA-Z]{2,}(?![a-zA-Z\-.])'

# Context 1: Explicit-protocol URLs — https://api.x.com, wss://ws.x.io, ftp://files.x.net
DOMAIN_IN_URL_PATTERN = r'(?:https?|wss?|ftp)://(' + _DNS_DOMAIN + r')'

# Context 2: Protocol-relative URLs — //cdn.x.com, //player.vimeo.com
# Negative lookbehind prevents re-matching the // from ://
DOMAIN_IN_PROTO_REL_PATTERN = r'(?<![:/\w])//(' + _DNS_DOMAIN + r')'

# Context 3: Escaped-dot notation inside JS regex literals — vimeo\.com, be\.googleapis\.com
# Raw backslash+dot appears as the two characters \. in the file text
DOMAIN_IN_REGEX_LIT_PATTERN = (
    r'(?<![a-zA-Z0-9\-])'
    r'([a-zA-Z0-9][a-zA-Z0-9\-]*(?:\\\.[a-zA-Z0-9][a-zA-Z0-9\-]*)*\\\.[a-zA-Z]{2,})'
    r'(?![a-zA-Z0-9\-\\])'
)

# Context 4: Quoted standalone hostname strings — "api.x.com", 'sub.domain.io'
# Backreference \1 ensures the opening and closing quotes match (both " or both ')
DOMAIN_IN_QUOTES_PATTERN = r'(["\'])(' + _DNS_DOMAIN + r')\1'

# Context 5 (REMOVED): Comma-separated domain lists were originally matched
# here, but in real-world minified JS files, comma-separated function args
# and object properties (a.top,b.data,c.name) are structurally identical to
# domain lists (google.com,facebook.com,z.ai).  Every structural guard still
# produced false positives because minified JS has letter-comma-word.word
# sequences everywhere.  In practice, legitimate domains in JS files always
# appear in URLs, quoted strings, or regex literals — never as bare
# comma-separated text.  Removing this context eliminates ~30% of false
# positives with zero loss of real domains.

# ================= CLOUD BUCKET PATTERNS =================

CLOUD_BUCKET_PATTERNS = {
    'aws_s3': [
        r'https?://([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])\.s3\.amazonaws\.com',
        r'https?://([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])\.s3[.\-]([a-z0-9\-]+)\.amazonaws\.com',
        r'https?://s3\.amazonaws\.com/([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])',
        r'https?://s3[.\-]([a-z0-9\-]+)\.amazonaws\.com/([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])',
        r'https?://([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])\.s3-website[.\-]([a-z0-9\-]+)\.amazonaws\.com',
        r's3://([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])',
    ],
    'gcp': [
        r'https?://storage\.googleapis\.com/([a-z0-9][a-z0-9\-_\.]{1,61}[a-z0-9])',
        r'https?://([a-z0-9][a-z0-9\-_\.]{1,61}[a-z0-9])\.storage\.googleapis\.com',
        r'https?://storage\.cloud\.google\.com/([a-z0-9][a-z0-9\-_\.]{1,61}[a-z0-9])',
        r'gs://([a-z0-9][a-z0-9\-_\.]{1,61}[a-z0-9])',
    ],
    'azure': [
        r'https?://([a-z0-9]{3,24})\.blob\.core\.windows\.net/?([a-z0-9\-]{3,63})?',
        r'https?://([a-z0-9]{3,24})\.file\.core\.windows\.net',
        r'https?://([a-z0-9]{3,24})\.queue\.core\.windows\.net',
        r'https?://([a-z0-9]{3,24})\.table\.core\.windows\.net',
        r'https?://([a-z0-9]{3,24})\.dfs\.core\.windows\.net',
    ],
    'alibaba_oss': [
        r'https?://([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])\.oss-cn-([a-z0-9\-]+)\.aliyuncs\.com',
        r'https?://([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])\.oss-([a-z0-9\-]+)\.aliyuncs\.com',
        r'https?://oss\.aliyuncs\.com/([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])',
    ],
    'digitalocean_spaces': [
        r'https?://([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])\.([a-z0-9\-]+)\.digitaloceanspaces\.com',
        r'https?://([a-z0-9\-]+)\.digitaloceanspaces\.com/([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])',
    ],
    'ibm_cos': [
        r'https?://([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])\.s3\.([a-z0-9\-]+)\.cloud-object-storage\.appdomain\.cloud',
        r'https?://s3\.([a-z0-9\-]+)\.cloud-object-storage\.appdomain\.cloud/([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])',
    ],
    'oracle_oci': [
        r'https?://objectstorage\.([a-z0-9\-]+)\.oraclecloud\.com/n/([a-z0-9\-_]+)/b/([a-z0-9][a-z0-9\-_\.]{1,255}[a-z0-9])',
        r'https?://([a-z0-9\-_]+)\.objectstorage\.([a-z0-9\-]+)\.oraclecloud\.com',
    ],
    'tencent_cos': [
        r'https?://([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])\.cos\.([a-z0-9\-]+)\.myqcloud\.com',
        r'https?://([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])-([0-9]+)\.cos\.([a-z0-9\-]+)\.myqcloud\.com',
    ],
    'backblaze_b2': [
        r'https?://f[0-9]{3}\.backblazeb2\.com/file/([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])',
        r'https?://s3\.([a-z0-9\-]+)\.backblazeb2\.com/([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])',
    ],
    'wasabi': [
        r'https?://s3\.wasabisys\.com/([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])',
        r'https?://s3\.([a-z0-9\-]+)\.wasabisys\.com/([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])',
        r'https?://([a-z0-9][a-z0-9\-\.]{1,61}[a-z0-9])\.s3\.wasabisys\.com',
    ],
    'cloudflare_r2': [
        r'https?://([a-z0-9]+)\.r2\.cloudflarestorage\.com/([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])',
        r'https?://pub-([a-z0-9]+)\.r2\.dev',
    ],
}

# ================= DOC LINK PATTERNS =================

DOC_LINK_PATTERNS = {
    'google_docs': [
        r'https?://docs\.google\.com/document/d/([a-zA-Z0-9_-]+)',
        r'https?://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)',
        r'https?://docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)',
        r'https?://docs\.google\.com/forms/(?:d|e)/([a-zA-Z0-9_-]+)',
        r'https?://docs\.google\.com/drawings/d/([a-zA-Z0-9_-]+)',
        r'https?://drive\.google\.com/(?:file/d|open\?id=|uc\?id=)([a-zA-Z0-9_-]+)',
        r'https?://drive\.google\.com/(?:drive/folders/|open\?id=)([a-zA-Z0-9_-]+)',
        r'https?://script\.google\.com/d/([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?google\.com/maps/d/(?:u/\d+/)?(?:viewer|edit)\?mid=([a-zA-Z0-9_-]+)',
        r'https?://jamboard\.google\.com/d/([a-zA-Z0-9_-]+)',
    ],
    'mediafire': [
        r'https?://(?:www\.)?mediafire\.com/file/([a-zA-Z0-9]+)(?:/[a-zA-Z0-9\-_.]+)?',
        r'https?://(?:www\.)?mediafire\.com/folder/([a-zA-Z0-9]+)(?:/[a-zA-Z0-9\-_.]+)?',
        r'https?://(?:www\.)?mediafire\.com/\?([a-zA-Z0-9]{11,15})',
        r'https?://download[0-9]*\.mediafire\.com/([a-zA-Z0-9]+)(?:/[a-zA-Z0-9\-_.]+)?',
        r'https?://(?:www\.)?mediafire\.com/(?:myfiles|view|convkey)/([a-zA-Z0-9]+)',
    ],
    'dropbox': [
        r'https?://(?:www\.)?(?:dropbox\.com|dl\.dropboxusercontent\.com)/(?:s|sh|scl/fi)/[a-zA-Z0-9\-_.\/]+(?:\?dl=[01]|\?raw=1)?',
    ],
    'onedrive_sharepoint': [
        r'https?://1drv\.ms/[a-zA-Z0-9]+',
        r'https?://onedrive\.live\.com/(?:redir|view|download)\?[a-zA-Z0-9=%&._-]+',
        r'https?://[a-zA-Z0-9\-]+(?:-my)?\.sharepoint\.com/(?::[a-z]:/[rg]/)?(?:personal/|sites/)[a-zA-Z0-9\-_.\/?=&%]+',
    ],
    'zoho': [
        r'https?://workdrive\.zoho\.(?:com|in|eu|com\.au|jp|com\.cn)/(?:file|folder|external|open)/([a-zA-Z0-9]{20,})',
        r'https?://workdrive\.zoho\.(?:com|in|eu|com\.au|jp|com\.cn)/viewer/([a-zA-Z0-9]{20,})',
        r'https?://workdrive\.zoho\.(?:com|in|eu|com\.au|jp|com\.cn)/home/([a-zA-Z0-9]{20,})',
    ],
    'mega': [
        r'https?://mega\.(?:nz|co\.nz)/file/([a-zA-Z0-9]{8,})#([a-zA-Z0-9_-]{30,})',
        r'https?://mega\.(?:nz|co\.nz)/folder/([a-zA-Z0-9]{8,})#([a-zA-Z0-9_-]{30,})',
        r'https?://mega\.(?:nz|co\.nz)/#!([a-zA-Z0-9]{8,})!([a-zA-Z0-9_-]{30,})',
        r'https?://mega\.(?:nz|co\.nz)/#F!([a-zA-Z0-9]{8,})!([a-zA-Z0-9_-]{30,})',
    ],
}

# ================= APP LINK PATTERNS =================

APP_LINK_PATTERNS = {
    'play_store': [
        r'https?://play\.google\.com/store/apps/details\?id=([a-zA-Z0-9._]+)',
        r'https?://play\.google\.com/store/apps/dev\?id=([0-9]+)',
        r'market://details\?id=([a-zA-Z0-9._]+)',
    ],
    'app_store': [
        r'https?://apps\.apple\.com/(?:[a-z]{2}/)?app/(?:[a-zA-Z0-9\-_.]+/)?id([0-9]+)',
        r'https?://itunes\.apple\.com/(?:[a-z]{2}/)?app/(?:[a-zA-Z0-9\-_.]+/)?id([0-9]+)',
        r'itms-apps?://(?:apps|itunes)\.apple\.com/[a-zA-Z0-9\-_./?=&%]+',
    ],
}

# ================= SOCIAL MEDIA PATTERNS =================

SOCIAL_MEDIA_PATTERNS = {
    'facebook': [
        r'https?://(?:www\.)?facebook\.com/[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
        r'https?://(?:www\.)?fb\.com/[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
        r'https?://(?:www\.)?facebook\.com/groups/[a-zA-Z0-9._-]+',
        r'https?://(?:www\.)?facebook\.com/pages/[a-zA-Z0-9._/-]+',
        r'https?://m\.facebook\.com/[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
    ],
    'instagram': [
        r'https?://(?:www\.)?instagram\.com/[a-zA-Z0-9._]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
        r'https?://(?:www\.)?instagr\.am/[a-zA-Z0-9._]+',
    ],
    'twitter': [
        r'https?://(?:www\.)?(?:twitter|x)\.com/[a-zA-Z0-9_]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
        r'https?://t\.co/[a-zA-Z0-9]+',
    ],
    'linkedin': [
        r'https?://(?:www\.)?linkedin\.com/(?:company|in|school|showcase)/[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
    ],
    'youtube': [
        r'https?://(?:www\.)?youtube\.com/(?:channel|c|user|@)[a-zA-Z0-9._/-]+',
        r'https?://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]+',
        r'https?://youtu\.be/[a-zA-Z0-9_-]+',
    ],
    'tiktok': [
        r'https?://(?:www\.)?tiktok\.com/@[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
    ],
    'pinterest': [
        r'https?://(?:www\.)?pinterest\.com/[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
        r'https?://pin\.it/[a-zA-Z0-9]+',
    ],
    'reddit': [
        r'https?://(?:www\.)?reddit\.com/(?:r|u|user)/[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
    ],
    'snapchat': [
        r'https?://(?:www\.)?snapchat\.com/add/[a-zA-Z0-9._-]+',
    ],
    'telegram': [
        r'https?://(?:www\.)?t\.me/[a-zA-Z0-9._-]+',
        r'https?://(?:www\.)?telegram\.me/[a-zA-Z0-9._-]+',
    ],
    'whatsapp': [
        r'https?://(?:www\.)?wa\.me/[0-9]+',
        r'https?://(?:api|chat|web)\.whatsapp\.com/[a-zA-Z0-9._/?=&%-]+',
    ],
    'discord': [
        r'https?://(?:www\.)?discord\.(?:gg|com/invite)/[a-zA-Z0-9-]+',
        r'https?://(?:www\.)?discord\.com/channels/[0-9]+(?:/[0-9]+)?',
    ],
    'github': [
        r'https?://(?:www\.)?github\.com/(?:orgs/)?[a-zA-Z0-9._-]+(?![a-zA-Z0-9._/?=&%-])',
    ],
    'medium': [
        r'https?://(?:www\.)?medium\.com/@?[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._/?=&%-]*)?',
    ],
    'tumblr': [
        r'https?://[a-zA-Z0-9-]+\.tumblr\.com(?:/[a-zA-Z0-9._/?=&%-]*)?',
    ],
    'twitch': [
        r'https?://(?:www\.)?twitch\.tv/[a-zA-Z0-9._-]+',
    ],
    'vimeo': [
        r'https?://(?:www\.)?vimeo\.com/[a-zA-Z0-9._-]+',
    ],
}

# ================= SKIP PATTERNS (False Positives) =================

SKIP_DOMAINS = []

# Detects JS property chaining or function calls right after a candidate domain.
# Used for quoted-context matches: if chaining happens directly off a closing quote
# (e.g. "str".method()), the quoted content is code, not a real domain.
_JS_PROPERTY_CHAIN_RE = re.compile(
    r'^(?:'
    r'\.[a-zA-Z_$]'       # .method or .property (JS chaining)
    r'|\('                 # function call
    r'|\['                 # bracket access
    r')'
)


SKIP_IPS = []


class JSInfoExtractor:
    """Extract various information from JS files"""

    def __init__(self):
        # Compile all patterns
        self.ip_regex = re.compile(IP_PATTERN)
        self.email_regex = re.compile(EMAIL_PATTERN, re.IGNORECASE)
        self.url_regex = re.compile(URL_PATTERN)

        # Domain extraction: four focused patterns (URL/quoted contexts)
        self.domain_url_regex       = re.compile(DOMAIN_IN_URL_PATTERN,          re.IGNORECASE)
        self.domain_proto_rel_regex = re.compile(DOMAIN_IN_PROTO_REL_PATTERN,    re.IGNORECASE)
        self.domain_regex_lit_regex = re.compile(DOMAIN_IN_REGEX_LIT_PATTERN,    re.IGNORECASE)
        self.domain_quotes_regex    = re.compile(DOMAIN_IN_QUOTES_PATTERN,       re.IGNORECASE)

        # Load valid TLDs
        self.tlds = self._load_tlds()

        self.cloud_patterns = {}
        for provider, patterns in CLOUD_BUCKET_PATTERNS.items():
            self.cloud_patterns[provider] = [re.compile(p, re.IGNORECASE) for p in patterns]

        self.doc_patterns = {}
        for service, patterns in DOC_LINK_PATTERNS.items():
            self.doc_patterns[service] = [re.compile(p, re.IGNORECASE) for p in patterns]

        self.app_patterns = {}
        for store, patterns in APP_LINK_PATTERNS.items():
            self.app_patterns[store] = [re.compile(p, re.IGNORECASE) for p in patterns]

        self.social_patterns = {}
        for platform, patterns in SOCIAL_MEDIA_PATTERNS.items():
            self.social_patterns[platform] = [re.compile(p, re.IGNORECASE) for p in patterns]

    def _load_tlds(self):
        """Load valid TLDs from the public suffix list file"""
        tld_file = Path(__file__).parent / 'bin' / 'TLDs.txt'
        tlds = set()
        try:
            with open(tld_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments, empty lines, wildcards, exceptions
                    if not line or line.startswith('//') or line.startswith('*') or line.startswith('!'):
                        continue
                    tlds.add(line.lower())
        except FileNotFoundError:
            pass
        return tlds

    @staticmethod
    def _has_mixed_case(domain_original):
        """Return True if the entire domain string has mixed case (e.g. cD, sB, eE).

        Real domains are always written in consistent case — all lowercase
        (api.example.com) or all uppercase.  Mixed case is almost always a JS
        camelCase identifier or property chain, not a domain.
        """
        return any(c.isupper() for c in domain_original) and any(c.islower() for c in domain_original)

    def _has_valid_tld(self, domain):
        """Return True if domain ends with a known TLD and has at least one hostname label before it."""
        if not self.tlds:
            return True  # Fallback: accept all if TLD list failed to load
        parts = domain.lower().split('.')
        if len(parts) < 2:
            return False
        # Reject bare TLD/eTLD entries — the domain itself is a TLD (e.g. "co.ao", "co.uk", "com").
        # These appear in JS files as supported-suffix lists and must not be treated as hostnames.
        if domain.lower() in self.tlds:
            return False
        # Valid single-label TLD: at least one hostname label before it (len >= 2, guaranteed above)
        if parts[-1] in self.tlds:
            return True
        # Valid two-label eTLD (e.g. "co.uk"): requires at least one hostname label before it (len >= 3)
        if len(parts) >= 3 and '.'.join(parts[-2:]) in self.tlds:
            return True
        return False

    def extract_ips(self, content):
        """Extract IP addresses, filtering out SVG/coordinate false positives.

        SVG path data and dense numeric sequences produce IP-like patterns
        (e.g. "00.09.05.12" inside "a.12.12 0 00.09.05.12L512 466.75").
        These are detected by counting dots in a window around the match:
        real IPs sit in code/string contexts with few surrounding dots,
        while coordinate data has many.
        """
        ips = set()
        for match in self.ip_regex.finditer(content):
            ip = match.group(0)
            if ip in SKIP_IPS:
                continue
            # Check surrounding context for numeric/coordinate density.
            # SVG path data and dense decimal sequences have many dots
            # around the match; real IP contexts (URLs, JSON, config) don't.
            win_start = max(0, match.start() - 40)
            win_end = min(len(content), match.end() + 40)
            surrounding = content[win_start:match.start()] + content[match.end():win_end]
            if surrounding.count('.') > 3:
                continue
            ips.add(ip)
        return sorted(list(ips))

    def extract_emails(self, content):
        """Extract email addresses"""
        emails = set()
        for match in self.email_regex.finditer(content):
            email = match.group(0).lower()
            # Skip common false positives
            if not any(skip in email for skip in ['@example', '@test', '@localhost']):
                emails.add(email)
        return sorted(list(emails))

    def extract_domains(self, content):
        """Extract domains from URL, quoted-string, and regex-literal contexts.

        Scans four high-confidence contexts where real hostnames appear in JS:
          1. Explicit-protocol URLs  (https://, http://, wss://, ftp://)
          2. Protocol-relative URLs  (//domain.tld)
          3. Escaped-dot regex literals  (vimeo\\.com inside /pattern/)
          4. Quoted standalone strings   ("api.example.com")

        Each context has strong delimiters (protocol prefix, //, \\., quotes)
        that distinguish real domains from JS property chains.
        """
        raw = set()

        # Context 1 & 2: URL-based — high confidence, no extra filtering needed
        for regex in (self.domain_url_regex, self.domain_proto_rel_regex):
            for match in regex.finditer(content):
                raw.add(match.group(1).lower())

        # Context 3: Escaped-dot regex literals — normalise \. → .
        for match in self.domain_regex_lit_regex.finditer(content):
            domain = match.group(1).lower().replace('\\.', '.')
            if '.' in domain:
                raw.add(domain)

        # Context 4: Quoted standalone hostnames — matching quotes via backreference.
        # Group 1 = quote char, Group 2 = domain.
        # Reject if:
        #   - TLD has mixed case (camelCase JS identifier like u.cD)
        #   - JS property chaining follows the closing quote (.method, (, [)
        #   - Opening quote preceded by [ → bracket property access (obj["key.path"])
        #   - Closing quote followed by : → object key, not value ("key.path":val)
        for match in self.domain_quotes_regex.finditer(content):
            original = match.group(2)
            if self._has_mixed_case(original):
                continue
            # Check char before opening quote
            before_pos = match.start() - 1
            if before_pos >= 0 and content[before_pos] == '[':
                continue
            # Check char after closing quote
            after_pos = match.end()
            if after_pos < len(content):
                after_char = content[after_pos]
                if after_char == ':':
                    continue
            after_quote = content[after_pos:after_pos + 20]
            if _JS_PROPERTY_CHAIN_RE.match(after_quote):
                continue
            raw.add(original.lower())

        # Apply common filters and TLD validation
        result = []
        for domain in sorted(raw):
            if any(skip in domain for skip in SKIP_DOMAINS):
                continue
            if re.match(r'.*\.(js|css|png|jpg|jpeg|gif|svg|ico|woff|ttf|eot|map|md)$', domain):
                continue
            if self._has_valid_tld(domain):
                result.append(domain)
        return result

    def extract_cloud_buckets(self, content):
        """Extract cloud bucket URLs"""
        results = {}
        for provider, patterns in self.cloud_patterns.items():
            found = set()
            for regex in patterns:
                for match in regex.finditer(content):
                    found.add(match.group(0))
            if found:
                results[provider] = sorted(list(found))
        return results

    def extract_doc_links(self, content):
        """Extract document links"""
        results = {}
        for service, patterns in self.doc_patterns.items():
            found = set()
            for regex in patterns:
                for match in regex.finditer(content):
                    found.add(match.group(0))
            if found:
                results[service] = sorted(list(found))
        return results

    def extract_app_links(self, content):
        """Extract app store links"""
        results = {}
        for store, patterns in self.app_patterns.items():
            found = set()
            for regex in patterns:
                for match in regex.finditer(content):
                    found.add(match.group(0))
            if found:
                results[store] = sorted(list(found))
        return results

    # Max path segments allowed for social media profile URLs.
    # Real profiles are shallow (e.g. /username, /pages/name, /groups/name).
    # Internal/API endpoints are deep (e.g. /privacy_sandbox/pixel/register/trigger/).
    _MAX_SOCIAL_PATH_SEGMENTS = 2

    # Known tracking/API endpoints to skip (e.g. facebook.com/tr/, instagram.com/tr/)
    _SKIP_SOCIAL_PATHS = {'/tr', '/tr/'}

    def extract_social_links(self, content):
        """Extract social media links"""
        results = {}
        for platform, patterns in self.social_patterns.items():
            found = set()
            for regex in patterns:
                for match in regex.finditer(content):
                    url = match.group(0)
                    # Extract path and count non-empty segments
                    path = url.split('/', 3)[-1] if url.count('/') >= 3 else ''
                    segments = [s for s in path.split('/') if s]
                    if len(segments) > self._MAX_SOCIAL_PATH_SEGMENTS:
                        continue
                    # Skip known tracking endpoints
                    url_path = '/' + path if path else ''
                    if url_path.rstrip('/') in {p.rstrip('/') for p in self._SKIP_SOCIAL_PATHS}:
                        continue
                    found.add(url)
            if found:
                results[platform] = sorted(list(found))
        return results

    def extract_urls(self, content):
        """Extract full URLs (http/https) from content"""
        urls = set()
        for match in self.url_regex.finditer(content):
            url = match.group(0)
            # Strip trailing punctuation that's likely not part of the URL
            url = url.rstrip(');,}>]')
            if len(url) > 10:  # skip very short matches
                urls.add(url)
        return sorted(list(urls))

    def extract_all(self, content):
        """Extract all information from content"""
        return {
            'ip_addresses': self.extract_ips(content),
            'emails': self.extract_emails(content),
            'domains': self.extract_domains(content),
            'cloud_buckets': self.extract_cloud_buckets(content),
            'doc_links': self.extract_doc_links(content),
            'app_links': self.extract_app_links(content),
            'social_links': self.extract_social_links(content),
            'urls': self.extract_urls(content),
        }


def resolve_domains_with_dnsx(domains):
    """Run dnsx to DNS-resolve a list of domains.

    Returns:
        (resolved_set, ran_ok) where:
          - resolved_set: set of domain strings that resolved successfully
          - ran_ok: True if dnsx executed (even if nothing resolved),
                    False if dnsx is missing or crashed (caller should use 'unknown')
    """
    if not domains:
        return set(), True
    try:
        result = subprocess.run(
            [_tool_path('dnsx'), '-silent', '-t', '50'],
            input='\n'.join(domains),
            capture_output=True,
            text=True,
            timeout=120
        )
        resolved = set()
        for line in result.stdout.strip().splitlines():
            line = line.strip().lower()
            if line:
                resolved.add(line)
        return resolved, True
    except FileNotFoundError:
        print('[dnsx] not found in PATH — domain status will be set to unknown')
        return set(), False
    except subprocess.TimeoutExpired:
        print('[dnsx] timed out after 120s — domain status will be set to unknown')
        return set(), False
    except Exception as e:
        print(f'[dnsx] unexpected error: {e} — domain status will be set to unknown')
        return set(), False


def process_file(js_file, output_dir, json_output=False):
    """Process a single local JS file (like -d but for one file)"""
    js_file = Path(js_file)
    if not js_file.exists():
        print(f"File not found: {js_file}")
        return 0
    output_dir = Path(output_dir)
    os.makedirs(_long_path(output_dir), exist_ok=True)

    extractor = JSInfoExtractor()
    base_name = js_file.parent.name
    source_name = js_file.name

    try:
        with open(_long_path(js_file), 'r', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {js_file}: {e}")
        return 0

    results = extractor.extract_all(content)

    all_ips = [{"base": base_name, "source": source_name, "ip": ip} for ip in results['ip_addresses']]
    all_emails = [{"base": base_name, "source": source_name, "email": e} for e in results['emails']]
    all_domains = [{"base": base_name, "source": source_name, "domain": d} for d in results['domains']]
    all_cloud_buckets = [
        {"base": base_name, "source": source_name, "type": provider, "bucket": bucket}
        for provider, buckets in results['cloud_buckets'].items() for bucket in buckets
    ]
    all_doc_links = [
        {"base": base_name, "source": source_name, "type": service, "link": link}
        for service, links in results['doc_links'].items() for link in links
    ]
    all_app_links = [
        {"base": base_name, "source": source_name, "type": store, "link": link}
        for store, links in results['app_links'].items() for link in links
    ]
    all_social_links = [
        {"base": base_name, "source": source_name, "type": platform, "link": link}
        for platform, links in results['social_links'].items() for link in links
    ]
    all_urls = [{"base": base_name, "source": source_name, "url": u, "type": "js"} for u in results['urls']]

    # Resolve domains
    if all_domains:
        unique_domains = list({item['domain'] for item in all_domains})
        resolved, dnsx_ran = resolve_domains_with_dnsx(unique_domains)
        for item in all_domains:
            if not dnsx_ran:
                item['status'] = 'unknown'
            elif item['domain'] in resolved:
                item['status'] = 'active'
            else:
                item['status'] = 'inactive'

    total_count = 0
    file_map = [
        (all_ips, 'ip_addresses.json'),
        (all_emails, 'emails.json'),
        (all_domains, 'domains.json'),
        (all_cloud_buckets, 'cloud_buckets.json'),
        (all_doc_links, 'doc_links.json'),
        (all_app_links, 'app_links.json'),
        (all_social_links, 'social_links.json'),
        (all_urls, 'urls.json'),
    ]
    for items, fname in file_map:
        if items:
            with open(_long_path(output_dir / fname), 'a') as f:
                for item in items:
                    f.write(json.dumps(item) + '\n')
            total_count += len(items)

    summary = {
        'total_js_files': 1,
        'ip_addresses_count': len(all_ips),
        'emails_count': len(all_emails),
        'domains_count': len(all_domains),
        'cloud_buckets_count': len(all_cloud_buckets),
        'doc_links_count': len(all_doc_links),
        'app_links_count': len(all_app_links),
        'social_links_count': len(all_social_links),
        'urls_count': len(all_urls),
        'total_findings': total_count,
    }

    if json_output:
        print(json.dumps(summary))

    return total_count


def process_directory(js_dir, output_dir, json_output=False):
    """Process all JS files in a directory"""
    js_dir = Path(js_dir)
    output_dir = Path(output_dir)

    if not js_dir.exists():
        print(f"Directory not found: {js_dir}")
        return 0

    # Find all JS files
    js_files = list(js_dir.glob('*.js')) + list(js_dir.glob('*.js.txt'))
    if not js_files:
        return 0

    os.makedirs(_long_path(output_dir), exist_ok=True)

    extractor = JSInfoExtractor()

    # Derive base from the JS directory name (e.g., "app-us.observe.ai")
    base_name = js_dir.name

    # Aggregated results with source tracking
    all_ips = []  # List of {"base": ..., "source": ..., "ip": ...}
    all_emails = []  # List of {"base": ..., "source": ..., "email": ...}
    all_domains = []  # List of {"base": ..., "source": ..., "domain": ...}
    all_cloud_buckets = []  # List of {"base": ..., "source": ..., "type": ..., "bucket": ...}
    all_doc_links = []  # List of {"base": ..., "source": ..., "type": ..., "link": ...}
    all_app_links = []  # List of {"base": ..., "source": ..., "type": ..., "link": ...}
    all_social_links = []  # List of {"base": ..., "source": ..., "type": ..., "link": ...}
    all_urls = []  # List of {"base": ..., "source": ..., "url": ...}

    # Track unique values to avoid duplicates
    seen_ips = set()
    seen_emails = set()
    seen_domains = set()
    seen_buckets = set()
    seen_docs = set()
    seen_apps = set()
    seen_socials = set()
    seen_urls = set()

    # Process each file
    for js_file in js_files:
        try:
            with open(_long_path(js_file), 'r', errors='ignore') as f:
                content = f.read()

            source_name = js_file.name
            results = extractor.extract_all(content)

            # Aggregate IPs with source
            for ip in results['ip_addresses']:
                key = (source_name, ip)
                if key not in seen_ips:
                    seen_ips.add(key)
                    all_ips.append({"base": base_name, "source": source_name, "ip": ip})

            # Aggregate emails with source
            for email in results['emails']:
                key = (source_name, email)
                if key not in seen_emails:
                    seen_emails.add(key)
                    all_emails.append({"base": base_name, "source": source_name, "email": email})

            # Aggregate domains with source
            for domain in results['domains']:
                key = (source_name, domain)
                if key not in seen_domains:
                    seen_domains.add(key)
                    all_domains.append({"base": base_name, "source": source_name, "domain": domain})

            # Aggregate cloud buckets with source
            for provider, buckets in results['cloud_buckets'].items():
                for bucket in buckets:
                    key = (source_name, provider, bucket)
                    if key not in seen_buckets:
                        seen_buckets.add(key)
                        all_cloud_buckets.append({
                            "base": base_name,
                            "source": source_name,
                            "type": provider,
                            "bucket": bucket
                        })

            # Aggregate doc links with source
            for service, links in results['doc_links'].items():
                for link in links:
                    key = (source_name, service, link)
                    if key not in seen_docs:
                        seen_docs.add(key)
                        all_doc_links.append({
                            "base": base_name,
                            "source": source_name,
                            "type": service,
                            "link": link
                        })

            # Aggregate app links with source
            for store, links in results['app_links'].items():
                for link in links:
                    key = (source_name, store, link)
                    if key not in seen_apps:
                        seen_apps.add(key)
                        all_app_links.append({
                            "base": base_name,
                            "source": source_name,
                            "type": store,
                            "link": link
                        })

            # Aggregate social media links with source
            for platform, links in results['social_links'].items():
                for link in links:
                    key = (source_name, platform, link)
                    if key not in seen_socials:
                        seen_socials.add(key)
                        all_social_links.append({
                            "base": base_name,
                            "source": source_name,
                            "type": platform,
                            "link": link
                        })

            # Aggregate URLs with source
            for url in results['urls']:
                key = (source_name, url)
                if key not in seen_urls:
                    seen_urls.add(key)
                    all_urls.append({"base": base_name, "source": source_name, "url": url, "type": "js"})

        except Exception as e:
            pass

    # Resolve extracted domains with dnsx and tag each entry active/inactive/unknown
    if all_domains:
        unique_domains = list({item['domain'] for item in all_domains})
        resolved, dnsx_ran = resolve_domains_with_dnsx(unique_domains)
        for item in all_domains:
            if not dnsx_ran:
                item['status'] = 'unknown'
            elif item['domain'] in resolved:
                item['status'] = 'active'
            else:
                item['status'] = 'inactive'

    # Count totals
    total_count = 0

    # Save individual files (JSON Lines format - one JSON object per line)
    if all_ips:
        with open(_long_path(output_dir / 'ip_addresses.json'), 'w') as f:
            for item in all_ips:
                f.write(json.dumps(item) + '\n')
        total_count += len(all_ips)

    if all_emails:
        with open(_long_path(output_dir / 'emails.json'), 'w') as f:
            for item in all_emails:
                f.write(json.dumps(item) + '\n')
        total_count += len(all_emails)

    if all_domains:
        with open(_long_path(output_dir / 'domains.json'), 'w') as f:
            for item in all_domains:
                f.write(json.dumps(item) + '\n')
        total_count += len(all_domains)

    if all_cloud_buckets:
        with open(_long_path(output_dir / 'cloud_buckets.json'), 'w') as f:
            for item in all_cloud_buckets:
                f.write(json.dumps(item) + '\n')
        total_count += len(all_cloud_buckets)

    if all_doc_links:
        with open(_long_path(output_dir / 'doc_links.json'), 'w') as f:
            for item in all_doc_links:
                f.write(json.dumps(item) + '\n')
        total_count += len(all_doc_links)

    if all_app_links:
        with open(_long_path(output_dir / 'app_links.json'), 'w') as f:
            for item in all_app_links:
                f.write(json.dumps(item) + '\n')
        total_count += len(all_app_links)

    if all_social_links:
        with open(_long_path(output_dir / 'social_links.json'), 'w') as f:
            for item in all_social_links:
                f.write(json.dumps(item) + '\n')
        total_count += len(all_social_links)

    if all_urls:
        with open(_long_path(output_dir / 'urls.json'), 'w') as f:
            for item in all_urls:
                f.write(json.dumps(item) + '\n')
        total_count += len(all_urls)

    # Save summary
    summary = {
        'total_js_files': len(js_files),
        'ip_addresses_count': len(all_ips),
        'emails_count': len(all_emails),
        'domains_count': len(all_domains),
        'cloud_buckets_count': len(all_cloud_buckets),
        'doc_links_count': len(all_doc_links),
        'app_links_count': len(all_app_links),
        'social_links_count': len(all_social_links),
        'urls_count': len(all_urls),
        'total_findings': total_count,
    }

    with open(_long_path(output_dir / 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)

    if json_output:
        print(json.dumps(summary))
    else:
        print(f"IPs: {summary['ip_addresses_count']}, Emails: {summary['emails_count']}, "
              f"Domains: {summary['domains_count']}, Buckets: {summary['cloud_buckets_count']}, "
              f"Docs: {summary['doc_links_count']}, Apps: {summary['app_links_count']}, "
              f"Social: {summary['social_links_count']}, URLs: {summary['urls_count']}")

    return total_count


def fetch_url(url, timeout=15):
    """Fetch content from a URL"""
    # Create SSL context that ignores certificate errors
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def process_url(url, output_dir=None, json_output=False):
    """Process a single JS URL"""
    content = fetch_url(url)
    if not content:
        return 0

    extractor = JSInfoExtractor()
    results = extractor.extract_all(content)

    # Use URL as source name
    source_name = url

    # Build results with source
    all_ips = [{"source": source_name, "ip": ip} for ip in results['ip_addresses']]
    all_emails = [{"source": source_name, "email": email} for email in results['emails']]
    all_domains = [{"source": source_name, "domain": domain} for domain in results['domains']]

    all_cloud_buckets = []
    for provider, buckets in results['cloud_buckets'].items():
        for bucket in buckets:
            all_cloud_buckets.append({"source": source_name, "type": provider, "bucket": bucket})

    all_doc_links = []
    for service, links in results['doc_links'].items():
        for link in links:
            all_doc_links.append({"source": source_name, "type": service, "link": link})

    all_app_links = []
    for store, links in results['app_links'].items():
        for link in links:
            all_app_links.append({"source": source_name, "type": store, "link": link})

    all_social_links = []
    for platform, links in results['social_links'].items():
        for link in links:
            all_social_links.append({"source": source_name, "type": platform, "link": link})

    all_urls = [{"source": source_name, "url": u, "type": "js"} for u in results['urls']]

    total_count = len(all_ips) + len(all_emails) + len(all_domains) + \
                  len(all_cloud_buckets) + len(all_doc_links) + len(all_app_links) + \
                  len(all_social_links) + len(all_urls)

    # Save to files if output directory specified
    if output_dir:
        output_dir = Path(output_dir)
        os.makedirs(_long_path(output_dir), exist_ok=True)

        if all_ips:
            with open(_long_path(output_dir / 'ip_addresses.json'), 'w') as f:
                for item in all_ips:
                    f.write(json.dumps(item) + '\n')

        if all_emails:
            with open(_long_path(output_dir / 'emails.json'), 'w') as f:
                for item in all_emails:
                    f.write(json.dumps(item) + '\n')

        if all_domains:
            with open(_long_path(output_dir / 'domains.json'), 'w') as f:
                for item in all_domains:
                    f.write(json.dumps(item) + '\n')

        if all_cloud_buckets:
            with open(_long_path(output_dir / 'cloud_buckets.json'), 'w') as f:
                for item in all_cloud_buckets:
                    f.write(json.dumps(item) + '\n')

        if all_doc_links:
            with open(_long_path(output_dir / 'doc_links.json'), 'w') as f:
                for item in all_doc_links:
                    f.write(json.dumps(item) + '\n')

        if all_app_links:
            with open(_long_path(output_dir / 'app_links.json'), 'w') as f:
                for item in all_app_links:
                    f.write(json.dumps(item) + '\n')

        if all_social_links:
            with open(_long_path(output_dir / 'social_links.json'), 'w') as f:
                for item in all_social_links:
                    f.write(json.dumps(item) + '\n')

        if all_urls:
            with open(_long_path(output_dir / 'urls.json'), 'w') as f:
                for item in all_urls:
                    f.write(json.dumps(item) + '\n')

        # Save summary
        summary = {
            'source_url': url,
            'ip_addresses_count': len(all_ips),
            'emails_count': len(all_emails),
            'domains_count': len(all_domains),
            'cloud_buckets_count': len(all_cloud_buckets),
            'doc_links_count': len(all_doc_links),
            'app_links_count': len(all_app_links),
            'social_links_count': len(all_social_links),
            'urls_count': len(all_urls),
            'total_findings': total_count,
        }
        with open(_long_path(output_dir / 'summary.json'), 'w') as f:
            json.dump(summary, f, indent=2)

    # Print results
    if json_output:
        # Print each finding as JSON line
        for item in all_ips:
            print(json.dumps(item))
        for item in all_emails:
            print(json.dumps(item))
        for item in all_domains:
            print(json.dumps(item))
        for item in all_cloud_buckets:
            print(json.dumps(item))
        for item in all_doc_links:
            print(json.dumps(item))
        for item in all_app_links:
            print(json.dumps(item))
        for item in all_social_links:
            print(json.dumps(item))
        for item in all_urls:
            print(json.dumps(item))
    else:
        # Print findings in readable format
        counter = 1
        for item in all_ips:
            print(f"[ {counter} ] [IP] {item['source']} : {item['ip']}")
            counter += 1
        for item in all_emails:
            print(f"[ {counter} ] [EMAIL] {item['source']} : {item['email']}")
            counter += 1
        for item in all_domains:
            print(f"[ {counter} ] [DOMAIN] {item['source']} : {item['domain']}")
            counter += 1
        for item in all_cloud_buckets:
            print(f"[ {counter} ] [BUCKET:{item['type']}] {item['source']} : {item['bucket']}")
            counter += 1
        for item in all_doc_links:
            print(f"[ {counter} ] [DOC:{item['type']}] {item['source']} : {item['link']}")
            counter += 1
        for item in all_app_links:
            print(f"[ {counter} ] [APP:{item['type']}] {item['source']} : {item['link']}")
            counter += 1
        for item in all_social_links:
            print(f"[ {counter} ] [SOCIAL:{item['type']}] {item['source']} : {item['link']}")
            counter += 1
        for item in all_urls:
            print(f"[ {counter} ] [URL] {item['source']} : {item['url']}")
            counter += 1

        # Print summary at end
        print(f"\n[Summary] IPs: {len(all_ips)}, Emails: {len(all_emails)}, "
              f"Domains: {len(all_domains)}, Buckets: {len(all_cloud_buckets)}, "
              f"Docs: {len(all_doc_links)}, Apps: {len(all_app_links)}, "
              f"Social: {len(all_social_links)}, URLs: {len(all_urls)}")

    return total_count


def process_url_list(url_file, output_dir=None, json_output=False):
    """Process a list of JS URLs from a file"""
    url_file = Path(url_file)
    if not url_file.exists():
        print(f"Error: File not found: {url_file}")
        return 0

    extractor = JSInfoExtractor()

    # Aggregated results with source tracking
    all_ips = []
    all_emails = []
    all_domains = []
    all_cloud_buckets = []
    all_doc_links = []
    all_app_links = []
    all_social_links = []
    all_urls = []

    seen_ips = set()
    seen_emails = set()
    seen_domains = set()
    seen_buckets = set()
    seen_docs = set()
    seen_apps = set()
    seen_socials = set()
    seen_urls = set()

    urls_processed = 0

    with open(url_file, 'r') as f:
        for line in f:
            url = line.strip()
            if not url or url.startswith('#'):
                continue

            content = fetch_url(url)
            if not content:
                continue

            urls_processed += 1
            results = extractor.extract_all(content)
            source_name = url

            # Aggregate with source
            for ip in results['ip_addresses']:
                key = (source_name, ip)
                if key not in seen_ips:
                    seen_ips.add(key)
                    all_ips.append({"source": source_name, "ip": ip})

            for email in results['emails']:
                key = (source_name, email)
                if key not in seen_emails:
                    seen_emails.add(key)
                    all_emails.append({"source": source_name, "email": email})

            for domain in results['domains']:
                key = (source_name, domain)
                if key not in seen_domains:
                    seen_domains.add(key)
                    all_domains.append({"source": source_name, "domain": domain})

            for provider, buckets in results['cloud_buckets'].items():
                for bucket in buckets:
                    key = (source_name, provider, bucket)
                    if key not in seen_buckets:
                        seen_buckets.add(key)
                        all_cloud_buckets.append({"source": source_name, "type": provider, "bucket": bucket})

            for service, links in results['doc_links'].items():
                for link in links:
                    key = (source_name, service, link)
                    if key not in seen_docs:
                        seen_docs.add(key)
                        all_doc_links.append({"source": source_name, "type": service, "link": link})

            for store, links in results['app_links'].items():
                for link in links:
                    key = (source_name, store, link)
                    if key not in seen_apps:
                        seen_apps.add(key)
                        all_app_links.append({"source": source_name, "type": store, "link": link})

            for platform, links in results['social_links'].items():
                for link in links:
                    key = (source_name, platform, link)
                    if key not in seen_socials:
                        seen_socials.add(key)
                        all_social_links.append({"source": source_name, "type": platform, "link": link})

            for url in results['urls']:
                key = (source_name, url)
                if key not in seen_urls:
                    seen_urls.add(key)
                    all_urls.append({"source": source_name, "url": url, "type": "js"})

    total_count = len(all_ips) + len(all_emails) + len(all_domains) + \
                  len(all_cloud_buckets) + len(all_doc_links) + len(all_app_links) + \
                  len(all_social_links) + len(all_urls)

    # Save to files if output directory specified
    if output_dir:
        output_dir = Path(output_dir)
        os.makedirs(_long_path(output_dir), exist_ok=True)

        if all_ips:
            with open(_long_path(output_dir / 'ip_addresses.json'), 'w') as f:
                for item in all_ips:
                    f.write(json.dumps(item) + '\n')

        if all_emails:
            with open(_long_path(output_dir / 'emails.json'), 'w') as f:
                for item in all_emails:
                    f.write(json.dumps(item) + '\n')

        if all_domains:
            with open(_long_path(output_dir / 'domains.json'), 'w') as f:
                for item in all_domains:
                    f.write(json.dumps(item) + '\n')

        if all_cloud_buckets:
            with open(_long_path(output_dir / 'cloud_buckets.json'), 'w') as f:
                for item in all_cloud_buckets:
                    f.write(json.dumps(item) + '\n')

        if all_doc_links:
            with open(_long_path(output_dir / 'doc_links.json'), 'w') as f:
                for item in all_doc_links:
                    f.write(json.dumps(item) + '\n')

        if all_app_links:
            with open(_long_path(output_dir / 'app_links.json'), 'w') as f:
                for item in all_app_links:
                    f.write(json.dumps(item) + '\n')

        if all_social_links:
            with open(_long_path(output_dir / 'social_links.json'), 'w') as f:
                for item in all_social_links:
                    f.write(json.dumps(item) + '\n')

        if all_urls:
            with open(_long_path(output_dir / 'urls.json'), 'w') as f:
                for item in all_urls:
                    f.write(json.dumps(item) + '\n')

        # Save summary
        summary = {
            'urls_processed': urls_processed,
            'ip_addresses_count': len(all_ips),
            'emails_count': len(all_emails),
            'domains_count': len(all_domains),
            'cloud_buckets_count': len(all_cloud_buckets),
            'doc_links_count': len(all_doc_links),
            'app_links_count': len(all_app_links),
            'social_links_count': len(all_social_links),
            'urls_count': len(all_urls),
            'total_findings': total_count,
        }
        with open(_long_path(output_dir / 'summary.json'), 'w') as f:
            json.dump(summary, f, indent=2)

    # Print results
    if json_output:
        for item in all_ips:
            print(json.dumps(item))
        for item in all_emails:
            print(json.dumps(item))
        for item in all_domains:
            print(json.dumps(item))
        for item in all_cloud_buckets:
            print(json.dumps(item))
        for item in all_doc_links:
            print(json.dumps(item))
        for item in all_app_links:
            print(json.dumps(item))
        for item in all_social_links:
            print(json.dumps(item))
        for item in all_urls:
            print(json.dumps(item))
    else:
        counter = 1
        for item in all_ips:
            print(f"[ {counter} ] [IP] {item['source']} : {item['ip']}")
            counter += 1
        for item in all_emails:
            print(f"[ {counter} ] [EMAIL] {item['source']} : {item['email']}")
            counter += 1
        for item in all_domains:
            print(f"[ {counter} ] [DOMAIN] {item['source']} : {item['domain']}")
            counter += 1
        for item in all_cloud_buckets:
            print(f"[ {counter} ] [BUCKET:{item['type']}] {item['source']} : {item['bucket']}")
            counter += 1
        for item in all_doc_links:
            print(f"[ {counter} ] [DOC:{item['type']}] {item['source']} : {item['link']}")
            counter += 1
        for item in all_app_links:
            print(f"[ {counter} ] [APP:{item['type']}] {item['source']} : {item['link']}")
            counter += 1
        for item in all_social_links:
            print(f"[ {counter} ] [SOCIAL:{item['type']}] {item['source']} : {item['link']}")
            counter += 1
        for item in all_urls:
            print(f"[ {counter} ] [URL] {item['source']} : {item['url']}")
            counter += 1

        print(f"\n[Summary] URLs Processed: {urls_processed} | IPs: {len(all_ips)}, Emails: {len(all_emails)}, "
              f"Domains: {len(all_domains)}, Buckets: {len(all_cloud_buckets)}, "
              f"Docs: {len(all_doc_links)}, Apps: {len(all_app_links)}, "
              f"Social: {len(all_social_links)}, URLs: {len(all_urls)}")

    return total_count


def main():
    parser = argparse.ArgumentParser(
        description='JS Info Extractor - Extract sensitive info from JS files/URLs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Extracts:
  - IP Addresses
  - Email Addresses
  - Domains & Subdomains
  - Cloud Buckets (AWS, GCP, Azure, Alibaba, DigitalOcean, IBM, Oracle, Tencent, Backblaze, Wasabi, Cloudflare)
  - Doc Links (Google Docs/Drive, MediaFire, Dropbox, OneDrive, SharePoint, Zoho, Mega)
  - App Links (Play Store, App Store)

Examples:
  python js_info_extractor.py -u https://example.com/app.js
  python js_info_extractor.py -u https://example.com/app.js -o ./output
  python js_info_extractor.py -l js_urls.txt -o ./output
  python js_info_extractor.py -d ./downloaded-js -o ./output
  python js_info_extractor.py -d ./js-files -o ./results -j
        """
    )

    parser.add_argument('-u', '--url', help='Single JS URL to extract from')
    parser.add_argument('-l', '--list', help='File containing list of JS URLs')
    parser.add_argument('-f', '--file', help='Single local JS file to extract from')
    parser.add_argument('-d', '--directory', help='Directory containing JS files')
    parser.add_argument('-o', '--output', help='Output directory for results')
    parser.add_argument('-j', '--json', action='store_true', help='JSON output for summary')

    args = parser.parse_args()

    # Check that at least one input is provided
    if not args.url and not args.list and not args.file and not args.directory:
        parser.print_help()
        print("\nError: Please provide at least one input: -u (URL), -l (URL list), -f (file), or -d (directory)")
        return

    # Process based on input type
    if args.url:
        process_url(args.url, args.output, args.json)

    if args.list:
        process_url_list(args.list, args.output, args.json)

    if args.file:
        process_file(args.file, args.output, args.json)

    if args.directory:
        process_directory(args.directory, args.output, args.json)


if __name__ == "__main__":
    main()
