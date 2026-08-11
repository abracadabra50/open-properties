"""Backward-compatible MCP entrypoint."""
from open_properties.mcp_server import *  # noqa: F401,F403
from open_properties.mcp_server import main

if __name__ == "__main__":
    main()
