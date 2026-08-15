"""URL configuration for Django Ninja — mounted at the root, so paths match
every other framework exactly (/info, /movies, /catalog, /users/me)."""

from __future__ import annotations

from django.urls import path

from .ninja_api import api

urlpatterns = [path("", api.urls)]
