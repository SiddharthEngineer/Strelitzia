"""The dashboard's URL prefix. Every route (API and UI) lives under it, and nginx proxies it unchanged.

Its own module so app.py, auth.py and admin.py can all import it (app.py imports the other two).
Keep it in step with `base` in dashboard/vite.config.ts.
"""

PREFIX = "/strelitzia/dashboard"
API_PREFIX = f"{PREFIX}/api"
