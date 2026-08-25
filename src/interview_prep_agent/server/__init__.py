"""The web session layer: a bounded wrapper over the agent.

Optional — the core package never imports this; install the ``server`` extra
to use it. ``create_app`` builds the application; the ``serve`` command runs
it.
"""

from .app import create_app

__all__ = ["create_app"]
