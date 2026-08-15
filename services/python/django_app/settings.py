"""Base Django settings shared by the Ninja and Bolt variants. Each variant's
settings_<fw>.py does `from .settings import *` and only overrides
ROOT_URLCONF (+ INSTALLED_APPS for Bolt) — same split as the rest of this
benchmark's "one shared base, framework picks its own wiring" convention.
"""

from __future__ import annotations

import os

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django_app",
]

MIDDLEWARE = []

SECRET_KEY = "jero-benchmarks-not-for-production"
DEBUG = False
ALLOWED_HOSTS = ["*"]

# Same DB_* env vars every other framework reads (see services/python/settings.py).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "bench"),
        "USER": os.environ.get("DB_USER", "bench"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "bench"),
        "HOST": os.environ.get("DB_HOST", "postgres"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        # psycopg3 server-side pool, sized to match every other framework's
        # db_pool_size=64 (see README "Equal resource budgets").
        "OPTIONS": {"pool": {"max_size": 64}},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {},
    "loggers": {},
}
