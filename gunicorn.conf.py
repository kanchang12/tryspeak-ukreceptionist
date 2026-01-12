# gunicorn.conf.py
import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers = 21
worker_class = 'sync'
threads = 2
timeout = 120  # 2 minutes for long-running voice processing
graceful_timeout = 30
keepalive = 5
accesslog = '-'
errorlog = '-'
loglevel = 'info'
