"""Registry for MCP servers shipped with tooldex."""

from __future__ import annotations

from typing import Mapping

from mcp.server.fastmcp import FastMCP

from .server import MCP_SERVER

SERVERS: Mapping[str, FastMCP] = {"tooldex-shell": MCP_SERVER}

__all__ = ["SERVERS"]
