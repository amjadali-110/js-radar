"""
JS Discovery SaaS - Configuration
"""

import os
import secrets
from pathlib import Path

# Project root is one level up from backend/
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = Path(__file__).parent

# Database lives in backend/instance/
DB_PATH = BACKEND_DIR / 'instance' / 'js_discovery.db'


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', f'sqlite:///{DB_PATH}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SCANS_DIR = PROJECT_ROOT / 'data' / 'scans'
    SCANNER_SCRIPT = PROJECT_ROOT / 'scanner' / 'js_scanner.py'

    # CORS — comma-separated list of allowed origins; never default to wildcard
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:3000')

    # Flask-Limiter — uses Flask-Limiter's built-in config keys
    # RATELIMIT_DEFAULT_LIMITS is read automatically by flask-limiter after init_app
    RATELIMIT_DEFAULT_LIMITS = [
        os.environ.get('RATELIMIT_DEFAULT', '120 per minute')
    ]
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    # Custom key used only to configure the per-route scan-creation limit decorator
    RATELIMIT_SCAN_CREATE = os.environ.get('RATELIMIT_SCAN_CREATE', '10 per minute')

    # Upload / download limits
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024   # 16 MB max upload
    MAX_JS_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB per JS file download

    # Scan parameter bounds (enforce server-side)
    MAX_PARALLEL = 20
    MAX_CONCURRENCY = 10
    MAX_DEPTH = 5
    MAX_DELAY = 30


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    # Allow any origin in development so the app works when accessed via IP
    # (e.g., on Termux/Android or from another device on the same network).
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    # In production, CORS_ORIGINS must be set explicitly via environment variable.
    # Example: CORS_ORIGINS=https://jsdiscovery.example.com
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:3000')

    @classmethod
    def init_app(cls, app):
        if not os.environ.get('SECRET_KEY'):
            import warnings
            warnings.warn(
                'SECRET_KEY is not set. Using a random key — sessions will not '
                'persist across restarts. Set SECRET_KEY env var in production.'
            )
        if os.environ.get('CORS_ORIGINS', '') in ('*', ''):
            import warnings
            warnings.warn(
                'CORS_ORIGINS is set to wildcard or empty in production. '
                'Set CORS_ORIGINS to your frontend domain (e.g. https://app.example.com).'
            )


config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
