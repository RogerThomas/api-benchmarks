"""No ORM models -- test 4 (GET /users/me) queries the shared `users` table
with raw fastpg, same as every other async framework in this fleet (see
django_app/api.py). Kept as an empty module
rather than deleted so `django_app` stays a normal Django app package."""
