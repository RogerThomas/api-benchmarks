#!/usr/bin/env python
"""Django's management CLI — only needed to launch Bolt (`runbolt`); the
other Django variant (Ninja) is served directly over ASGI via serve.sh."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_app.settings_bolt")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
