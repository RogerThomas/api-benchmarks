"""Container entrypoint: the images are distroless (no shell), so this expands
the env into the server's own command line, then execs it.

    python serve.py peregrine <module:app>   # jero/fastapi/litestar/blacksheep/flask
    python serve.py robyn
    python serve.py django-bolt

Env: WORKERS (default 1). peregrine runs ASGI apps on uvloop (it's installed,
and peregrine uses it whenever it's importable). Request/access logging stays
off for every server.

Temporary, for the peregrine-vs-granian A/B: SERVER=granian runs the same app
under granian instead (`--loop uvloop` for ASGI; WSGI pinned to one blocking
thread, as the pre-peregrine harness ran it).
"""

import os
import sys

workers = os.environ.get("WORKERS", "1")

match sys.argv[1:]:
    case ["peregrine", app] if os.environ.get("SERVER") == "granian":
        wsgi = app.startswith("flask_app")
        argv = ["granian", "--interface", "wsgi" if wsgi else "asgi"]
        argv += ["--blocking-threads", "1"] if wsgi else ["--loop", "uvloop"]
        argv += ["--host", "0.0.0.0", "--port", "8000", "--workers", workers, app]
    case ["peregrine", app]:
        argv = ["peregrine", "--host", "0.0.0.0", "--port", "8000"]
        argv += ["--workers", workers, app]
    case ["robyn"]:
        # --log-level WARNING: Robyn defaults to INFO ("verbose/debug mode", per
        # its own startup banner).
        argv = ["python", "robyn_app.py", "--processes", "1", "--workers", workers]
        argv += ["--log-level", "WARNING"]
    case ["django-bolt"]:
        argv = ["python", "manage.py", "runbolt", "--host", "0.0.0.0", "--port", "8000"]
        argv += ["--processes", workers]
    case _:
        sys.exit(__doc__)

os.execvp(argv[0], argv)
