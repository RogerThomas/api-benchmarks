"""Django settings for Django Bolt (`manage.py runbolt`).

No DATABASES: test 4 queries Postgres with raw fastpg (see api.py), so the ORM
is never configured or touched.
"""

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django_bolt",
    "django_app",
]

MIDDLEWARE = []
# `runbolt` routes via its own Rust router (autodiscovered from api.py), not
# Django's urlpatterns; urls_empty only gives Django something importable.
ROOT_URLCONF = "django_app.urls_empty"

SECRET_KEY = "jero-benchmarks-not-for-production"
DEBUG = False
ALLOWED_HOSTS = ["*"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {},
    "loggers": {},
}
