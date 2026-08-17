"""No ORM models -- test 4 (GET /users/me) queries the shared `users` table
with raw psycopg, same as every other framework in this fleet (see
django_app/api.py and django_app/ninja_api.py). Kept as an empty module
rather than deleted so `django_app` stays a normal Django app package."""
