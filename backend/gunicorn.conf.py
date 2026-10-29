"""Small Render Free process with shared Postgres state and bounded AI calls."""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
worker_class = "gthread"
threads = int(os.environ.get("WEB_THREADS", "8"))
timeout = 45
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
# Exclude query strings, which can contain admin credentials.
access_log_format = '%(h)s %(m)s %(U)s %(s)s %(L)s'
