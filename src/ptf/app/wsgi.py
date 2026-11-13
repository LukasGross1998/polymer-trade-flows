"""WSGI entry point for a production web server: `gunicorn ptf.app.wsgi:server`.

Dash is built on Flask; `server` is the Flask application that gunicorn runs. The app keeps
its data in memory (`AppState`), so it runs as one worker process with several threads.
"""

from ptf.app.__main__ import create_app

server = create_app().server
