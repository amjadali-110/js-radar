"""
Health check and root routes
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify

health_bp = Blueprint('health', __name__)


@health_bp.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now(timezone.utc).isoformat()})


@health_bp.route('/')
def index():
    """Root endpoint — minimal response to avoid information disclosure."""
    return jsonify({'status': 'ok'})
