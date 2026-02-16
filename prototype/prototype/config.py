"""Central configuration for the prototype."""

import os

debug: bool = os.environ.get("CODD_DEBUG", "").lower() in ("1", "true")
