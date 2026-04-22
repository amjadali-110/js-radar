"""
Scan database model
"""

import uuid
from datetime import datetime
from backend.extensions import db


class Scan(db.Model):
    """Scan model"""
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    target_url = db.Column(db.String(2048), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, running, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    # Scan configuration
    parallel = db.Column(db.Integer, default=3)
    concurrency = db.Column(db.Integer, default=2)
    depth = db.Column(db.Integer, default=1)
    delay = db.Column(db.Integer, default=0)
    cookie = db.Column(db.Text, nullable=True)
    headers = db.Column(db.Text, nullable=True)  # JSON array of header strings
    scan_type = db.Column(db.String(20), default='full')  # full, js_urls, file

    # Resource usage
    peak_ram_mb = db.Column(db.Float, default=0)
    storage_mb = db.Column(db.Float, default=0)

    # Statistics
    total_urls = db.Column(db.Integer, default=0)
    successful_urls = db.Column(db.Integer, default=0)
    failed_urls = db.Column(db.Integer, default=0)
    js_downloaded = db.Column(db.Integer, default=0)
    js_failed = db.Column(db.Integer, default=0)
    secrets_count = db.Column(db.Integer, default=0)
    endpoints_count = db.Column(db.Integer, default=0)
    subdomains_count = db.Column(db.Integer, default=0)
    ips_count = db.Column(db.Integer, default=0)
    cloud_resources_count = db.Column(db.Integer, default=0)
    emails_count = db.Column(db.Integer, default=0)
    app_links_count = db.Column(db.Integer, default=0)
    doc_links_count = db.Column(db.Integer, default=0)
    social_links_count = db.Column(db.Integer, default=0)
    urls_count = db.Column(db.Integer, default=0)
    files_count = db.Column(db.Integer, default=0)
    parameters_count = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'target_url': self.target_url,
            'description': self.description,
            'status': self.status,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'started_at': self.started_at.isoformat() + 'Z' if self.started_at else None,
            'completed_at': self.completed_at.isoformat() + 'Z' if self.completed_at else None,
            'error_message': self.error_message,
            'parallel': self.parallel,
            'concurrency': self.concurrency,
            'depth': self.depth,
            'delay': self.delay,
            'cookie': self.cookie,
            'headers': self.headers,
            'scan_type': self.scan_type or 'full',
            'peak_ram_mb': round(self.peak_ram_mb or 0, 2),
            'storage_mb': round(self.storage_mb or 0, 2),
            'total_urls': self.total_urls,
            'successful_urls': self.successful_urls,
            'failed_urls': self.failed_urls,
            'js_downloaded': self.js_downloaded,
            'js_failed': self.js_failed,
            'secrets_count': self.secrets_count,
            'endpoints_count': self.endpoints_count,
            'subdomains_count': self.subdomains_count,
            'ips_count': self.ips_count,
            'cloud_resources_count': self.cloud_resources_count,
            'emails_count': self.emails_count,
            'app_links_count': self.app_links_count,
            'doc_links_count': self.doc_links_count,
            'social_links_count': self.social_links_count,
            'urls_count': self.urls_count,
            'files_count': self.files_count,
            'parameters_count': self.parameters_count,
        }
