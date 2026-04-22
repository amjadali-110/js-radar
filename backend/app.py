#!/usr/bin/env python3
"""
JS Discovery SaaS - Backend API
Flask application factory
"""

import os
import sys
import logging
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS

# Ensure project root is in path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import config_by_name
from backend.extensions import db, limiter
from backend.routes.scans import scans_bp
from backend.routes.dashboard import dashboard_bp
from backend.routes.health import health_bp


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('APP_ENV', 'development')

    config_class = config_by_name.get(config_name, config_by_name['default'])

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize production-specific config
    if hasattr(config_class, 'init_app'):
        config_class.init_app(app)

    # Logging
    log_level = logging.DEBUG if app.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    app.logger.setLevel(log_level)

    # CORS — wildcard allowed in development (Termux/IP access); restricted in production
    cors_origins = app.config.get('CORS_ORIGINS', '')
    if cors_origins.strip() == '*':
        CORS(app, origins='*', supports_credentials=False)
    else:
        allowed_origins = [o.strip() for o in cors_origins.split(',') if o.strip()] or ['http://localhost:3000']
        CORS(app, origins=allowed_origins, supports_credentials=False)

    # Security headers applied to every response
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        # Remove server fingerprint headers
        response.headers.pop('Server', None)
        response.headers.pop('X-Powered-By', None)
        return response

    # Rate limiter
    limiter.init_app(app)

    from flask_limiter.errors import RateLimitExceeded

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(e):
        return jsonify({'error': 'Rate limit exceeded', 'detail': str(e.description)}), 429

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    app.register_blueprint(scans_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(health_bp)

    # Default rate limits (120/min) are applied globally via RATELIMIT_DEFAULT_LIMITS
    # in the app config — flask-limiter reads that key automatically after init_app.
    # Per-route tighter limits are set with @limiter.limit() decorators on
    # create_scan and start_scan in routes/scans.py.

    # Create tables and add any missing columns
    with app.app_context():
        db.create_all()

        # Add columns that may be missing from older databases
        new_columns = [
            ('emails_count', 'INTEGER DEFAULT 0'),
            ('app_links_count', 'INTEGER DEFAULT 0'),
            ('doc_links_count', 'INTEGER DEFAULT 0'),
            ('files_count', 'INTEGER DEFAULT 0'),
            ('parameters_count', 'INTEGER DEFAULT 0'),
            ('peak_ram_mb', 'REAL DEFAULT 0'),
            ('storage_mb', 'REAL DEFAULT 0'),
            ('depth', 'INTEGER DEFAULT 1'),
            ('delay', 'INTEGER DEFAULT 0'),
            ('cookie', 'TEXT'),
            ('headers', 'TEXT'),
            ('scan_type', "VARCHAR(20) DEFAULT 'full'"),
        ]
        for col_name, col_type in new_columns:
            try:
                db.session.execute(db.text(f'ALTER TABLE scan ADD COLUMN {col_name} {col_type}'))
            except Exception:
                pass  # Column already exists
        db.session.commit()

    return app


if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('BACKEND_PORT', 3001))
    print(f"Starting JS Discovery Backend API on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=app.debug)
