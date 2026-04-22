"""Gunicorn production configuration."""

import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('BACKEND_PORT', '3001')}"

# Worker processes
# NOTE: Must stay at 1 — the scanner uses an in-memory dict (active_scans) to
# track running subprocesses, and SQLite does not support concurrent writers.
# Concurrency comes from threads instead.
workers = 1
worker_class = 'gthread'
threads = int(os.environ.get('GUNICORN_THREADS', 4))

# Timeouts — scanner jobs can run long, so keep worker alive
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 300))
graceful_timeout = 120
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sus'

# Security
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Process naming
proc_name = 'js-discovery-api'
