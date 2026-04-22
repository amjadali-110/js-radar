"""
Dashboard API routes - /api/dashboard/*
"""

from flask import Blueprint, jsonify
from backend.extensions import db
from backend.models.scan import Scan

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics"""
    total_scans = Scan.query.count()
    active_scans_count = Scan.query.filter_by(status='running').count()
    completed_scans = Scan.query.filter_by(status='completed').count()
    failed_scans = Scan.query.filter_by(status='failed').count()

    total_secrets = db.session.query(db.func.sum(Scan.secrets_count)).scalar() or 0
    total_endpoints = db.session.query(db.func.sum(Scan.endpoints_count)).scalar() or 0
    total_subdomains = db.session.query(db.func.sum(Scan.subdomains_count)).scalar() or 0
    total_cloud = db.session.query(db.func.sum(Scan.cloud_resources_count)).scalar() or 0
    total_storage_mb = db.session.query(db.func.sum(Scan.storage_mb)).scalar() or 0

    recent_scans = Scan.query.order_by(Scan.created_at.desc()).limit(5).all()

    return jsonify({
        'total_scans': total_scans,
        'active_scans': active_scans_count,
        'completed_scans': completed_scans,
        'failed_scans': failed_scans,
        'total_secrets': total_secrets,
        'total_endpoints': total_endpoints,
        'total_subdomains': total_subdomains,
        'total_cloud_resources': total_cloud,
        'total_storage_mb': round(total_storage_mb, 2),
        'recent_scans': [scan.to_dict() for scan in recent_scans]
    })
