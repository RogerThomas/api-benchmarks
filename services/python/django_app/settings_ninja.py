"""Settings for the Django Ninja variant — served over ASGI (serve.sh)."""

from .settings import *  # noqa: F403

ROOT_URLCONF = "django_app.urls_ninja"
