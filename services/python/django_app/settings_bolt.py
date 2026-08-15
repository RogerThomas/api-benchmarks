"""Settings for the Django Bolt variant — served via `manage.py runbolt`."""

from .settings import *  # noqa: F403

INSTALLED_APPS = [*INSTALLED_APPS, "django_bolt"]  # noqa: F405
ROOT_URLCONF = "django_app.urls_empty"
