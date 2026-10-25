"""Remote MCP gateway for the tabside-mcp WordPress plugin on customer sites."""

import os

_VERSION_BASE = "1.0"

# The image build passes APP_VERSION (base + commit count) and GIT_SHA.
__version__ = os.environ.get("APP_VERSION") or f"{_VERSION_BASE}.0"
GIT_SHA = os.environ.get("GIT_SHA", "unknown")
