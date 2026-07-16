from os import environ

from .types import Version

COMMUNITY_SERVER_URL = "https://studio.skybrush.io/api/v1"
"""Root URL of the Skybrush Studio community server."""

AXIO_SERVER_URL = environ.get("AXIO_TRAJ_SERVER_URL", "http://localhost:8000")
"""Root URL of our own Axio trajectory server (axio-traj-rest). This is the
default backend: when the server URL preference is left empty, the add-on
talks to this server instead of the Skybrush community server. Override with
the AXIO_TRAJ_SERVER_URL environment variable."""

MINIMUM_BACKEND_VERSION = Version(2, 35, 0)
"""The minimum version of the backend that is compatible with this version of the plugin."""
