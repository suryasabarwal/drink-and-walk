"""Gunicorn settings for Render's free plan.

One worker, several threads: the rate limiter, the Nominatim 1-per-second spacing and the
forecast cache live in memory, so they only work if every request shares one process.
A plan can wait on the main map server and then the backup (up to about 70 s when both are
slow), so the default 30 s worker timeout would kill it with a 502.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1
threads = 8
timeout = 120
graceful_timeout = 20
accesslog = "-"
