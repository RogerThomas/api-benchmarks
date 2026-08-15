"""Unmanaged model over the `users` table every framework reads for test 4
(seeded by services/db/init.sql) — no migrations, same shared row."""

from __future__ import annotations

from django.db import models


class User(models.Model):
    id = models.TextField(primary_key=True)
    name = models.TextField()
    email = models.TextField()
    address = models.TextField()
    city = models.TextField()
    country = models.TextField()

    class Meta:
        app_label = "django_app"
        db_table = "users"
        managed = False
