"""ASGI entrypoint for Django Ninja, launched via serve.sh (granian/uvicorn)
like the other ASGI frameworks. Django Bolt runs its own server
(manage.py runbolt) and never imports this module."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_app.settings_ninja")

application = get_asgi_application()
