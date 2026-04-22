"""
Filename/URL conversion utilities
"""

import re


def safe_dirname_to_url(dirname):
    """Convert a safe directory name (from JSScanner.get_safe_filename) back to a URL.

    JSScanner.get_safe_filename converts:
        https://legolas.ponedev.net/sign-in -> https_legolas.ponedev.net_sign-in
    This reverses that conversion.
    """
    if not dirname:
        return dirname

    name = dirname
    protocol = ''
    if name.startswith('https_'):
        protocol = 'https://'
        name = name[6:]
    elif name.startswith('http_'):
        protocol = 'http://'
        name = name[5:]

    # Find where the domain ends by matching .tld_
    tld_match = re.search(r'\.([a-z]{2,10})_', name)
    if tld_match:
        idx = tld_match.end() - 1
        domain = name[:idx]
        rest = name[idx + 1:]  # skip the underscore after TLD
        # Check if rest starts with a port number (e.g. "8080" or "8080_path")
        port_match = re.match(r'^(\d{2,5})(_.+)?$', rest) if rest else None
        if port_match:
            domain = domain + ':' + port_match.group(1)
            remaining = port_match.group(2)
            path = remaining.replace('_', '/') if remaining else ''
        else:
            path = name[idx:]
            path = path.replace('_', '/')
    else:
        domain = name
        path = ''

    return protocol + domain + path


def safe_filename_to_url(filename):
    """Convert a safe filename back to a readable URL format"""
    if not filename or filename == 'unknown':
        return filename

    # Remove .js extension if present for processing
    name = filename
    if name.endswith('.js'):
        name = name[:-3]

    # Convert back to URL format
    protocol = ''
    if name.startswith('https___'):
        protocol = 'https://'
        name = name[8:]
    elif name.startswith('http___'):
        protocol = 'http://'
        name = name[7:]

    # Handle __ (which represents /_ in paths like /_next, /_nuxt)
    DOUBLE_UNDERSCORE_PLACEHOLDER = '<<<DOUBLEUNDERSCORE>>>'
    name = name.replace('__', DOUBLE_UNDERSCORE_PLACEHOLDER)

    domain = name
    path = ''

    # Pattern: match .tld_ where tld is 2-10 lowercase letters
    tld_match = re.search(r'\.([a-z]{2,10})_', name)

    if tld_match:
        idx = tld_match.end() - 1
        domain = name[:idx]
        rest = name[idx + 1:]
        # Check if rest starts with a port number (digits followed by _ or placeholder or end)
        port_match = re.match(r'^(\d{2,5})($|_|' + re.escape(DOUBLE_UNDERSCORE_PLACEHOLDER) + r')', rest) if rest else None
        if port_match:
            port_str = port_match.group(1)
            domain = domain + ':' + port_str
            remaining = rest[len(port_str):]
            if remaining.startswith('_'):
                path = remaining[1:]  # skip leading _
            elif remaining:
                path = remaining  # starts with placeholder, keep as-is
            else:
                path = ''
        else:
            path = rest
    elif '_' in name and DOUBLE_UNDERSCORE_PLACEHOLDER not in name:
        first_underscore = name.find('_')
        if first_underscore > 0 and '.' in name[:first_underscore]:
            domain = name[:first_underscore]
            path = name[first_underscore + 1:]
        else:
            parts = name.split('_')
            if '.' in parts[0]:
                domain = parts[0]
                path = '_'.join(parts[1:])
    elif DOUBLE_UNDERSCORE_PLACEHOLDER in name:
        idx = name.find(DOUBLE_UNDERSCORE_PLACEHOLDER)
        domain = name[:idx]
        path = name[idx:]

    if path:
        path = '/' + path.replace('_', '/')

    path = path.replace('/' + DOUBLE_UNDERSCORE_PLACEHOLDER, '/_').replace(DOUBLE_UNDERSCORE_PLACEHOLDER, '/_')

    name = protocol + domain + path

    if filename.endswith('.js') and not name.endswith('.js'):
        name = name + '.js'

    return name
