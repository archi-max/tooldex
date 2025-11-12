"""Advanced tmux MCP server with multi-pane support and memory management.

This server provides a professional-grade tmux integration for AI agents, supporting:
- Multiple named pane attachments across sessions/windows
- Configurable memory buffers with automatic cleanup
- Cross-session/window pane management
- Robust error handling and validation
"""

from __future__ import annotations

import asyncio
import asyncio.subprocess
import os
import re
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from typing_extensions import TypedDict

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

# Configuration Constants
DEFAULT_MAX_BUFFER_LINES = 10000  # Per pane buffer limit
DEFAULT_MAX_ATTACHED_PANES = 20   # Maximum number of panes that can be attached
DEFAULT_BUFFER_CLEANUP_AGE = timedelta(hours=1)  # Auto-cleanup idle subscriptions
DEFAULT_POLL_INTERVAL = 0.2  # seconds
MAX_INITIAL_CAPTURE_LINES = 5000  # Maximum lines for initial capture
RESERVED_PANE_NAMES = {"primary"}  # Reserved names that can't be used for attachment

PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENT_GUIDE_PATH = PROJECT_ROOT / "docs" / "mcp" / "tooldex-advanced-shell-guide.md"
DOC_RESOURCE_URI = "doc://tooldex/advanced-shell-guide"


class PaneIdentifierType(Enum):
    """Types of tmux pane identifiers."""
    PANE_ID = "pane_id"        # %0, %1, etc.
    WINDOW_PANE = "window_pane"  # 0.0, 1.2, etc.
    SESSION_WINDOW_PANE = "session_window_pane"  # session:0.0


class AttachResult(TypedDict):
    """Result of attaching a tmux pane."""
    name: str
    pane_id: str
    session: str
    window: int
    pane_index: int
    attached_at: str
    is_primary: bool


class DetachResult(TypedDict):
    """Result of detaching a tmux pane."""
    name: str
    pane_id: str
    was_attached: bool
    active_subscriptions_cleared: int


class ListPanesResult(TypedDict):
    """Result of listing attached panes."""
    total_attached: int
    primary_pane: Optional[str]
    panes: List[Dict[str, Any]]


class ShellResult(TypedDict):
    """Structured output for a shell command execution."""
    command: str
    target_pane_name: str
    target_pane_id: str
    submitted: bool
    triggered_enter: bool
    note: str


class PaneReadResult(TypedDict):
    """Structured output for tmux pane capture."""
    pane_name: str
    pane_id: str
    lines_requested: int
    lines_returned: int
    truncated: bool
    buffer_usage: float  # Percentage of buffer used
    content: List[str]


class SubscriptionResult(TypedDict):
    """Information returned when a pane subscription is created."""
    token: str
    pane_name: str
    pane_id: str
    lines_recorded: int
    buffer_limit: int
    initial_lines: List[str]
    initial_truncated: bool


class UpdateResult(TypedDict):
    """Incremental update response for a pane subscription."""
    token: str
    pane_name: str
    pane_id: str
    new_lines: List[str]
    lines_recorded: int
    buffer_usage: float
    truncated: bool
    timed_out: bool


class BufferStatsResult(TypedDict):
    """Memory usage statistics for the MCP server."""
    total_panes_attached: int
    total_active_subscriptions: int
    total_buffer_lines: int
    max_buffer_lines_per_pane: int
    memory_estimate_mb: float
    panes: List[Dict[str, Any]]


class TmuxHierarchyResult(TypedDict):
    """Result of listing tmux hierarchy."""
    total_sessions: int
    total_windows: int
    total_panes: int
    current_session: Optional[str]
    current_window: Optional[str]
    current_pane: Optional[str]
    sessions: List[Dict[str, Any]]


class PaneScanResult(TypedDict):
    """Result of scanning all panes for content."""
    total_panes_scanned: int
    scan_timestamp: str
    panes: List[Dict[str, Any]]


@dataclass
class PaneInfo:
    """Information about an attached tmux pane."""
    name: str
    pane_id: str
    session: str
    window: int
    pane_index: int
    attached_at: datetime
    is_primary: bool = False
    last_accessed: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "pane_id": self.pane_id,
            "session": self.session,
            "window": self.window,
            "pane_index": self.pane_index,
            "attached_at": self.attached_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "is_primary": self.is_primary,
        }


@dataclass
class PaneSubscription:
    """Subscription state for tracking pane updates."""
    pane_name: str
    pane_id: str
    include_colors: bool
    lines_recorded: int
    buffer: Deque[str]
    max_buffer_lines: int
    last_snapshot: List[str]
    snapshot_ready: bool
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    
    def add_lines(self, lines: List[str]) -> None:
        """Add lines to buffer with automatic cleanup."""
        for line in lines:
            if len(self.buffer) >= self.max_buffer_lines:
                self.buffer.popleft()
            self.buffer.append(line)
        self.last_accessed = datetime.now()
    
    def get_buffer_usage(self) -> float:
        """Get buffer usage as percentage."""
        return (len(self.buffer) / self.max_buffer_lines) * 100 if self.max_buffer_lines > 0 else 0.0


class TmuxPaneRegistry:
    """Registry for managing multiple tmux panes with memory constraints."""
    
    def __init__(
        self,
        max_panes: int = DEFAULT_MAX_ATTACHED_PANES,
        max_buffer_lines: int = DEFAULT_MAX_BUFFER_LINES,
    ):
        self.max_panes = max_panes
        self.max_buffer_lines = max_buffer_lines
        self.panes: Dict[str, PaneInfo] = {}  # name -> PaneInfo
        self.pane_id_to_name: Dict[str, str] = {}  # pane_id -> name
        self.subscriptions: Dict[str, PaneSubscription] = {}  # token -> subscription
        self.pane_subscriptions: Dict[str, Set[str]] = {}  # pane_name -> set of tokens
        
    def attach_pane(
        self,
        name: str,
        pane_id: str,
        session: str,
        window: int,
        pane_index: int,
        is_primary: bool = False
    ) -> PaneInfo:
        """Attach a pane with a descriptive name."""
        if len(self.panes) >= self.max_panes and name not in self.panes:
            raise ValueError(
                f"Maximum number of attached panes ({self.max_panes}) reached. "
                f"Detach unused panes before attaching new ones."
            )
        
        # If re-attaching with same name, clean up old references
        if name in self.panes:
            old_pane = self.panes[name]
            if old_pane.pane_id in self.pane_id_to_name:
                del self.pane_id_to_name[old_pane.pane_id]
        
        pane_info = PaneInfo(
            name=name,
            pane_id=pane_id,
            session=session,
            window=window,
            pane_index=pane_index,
            attached_at=datetime.now(),
            is_primary=is_primary
        )
        
        self.panes[name] = pane_info
        self.pane_id_to_name[pane_id] = name
        
        if name not in self.pane_subscriptions:
            self.pane_subscriptions[name] = set()
        
        return pane_info
    
    def detach_pane(self, name: str) -> Tuple[Optional[PaneInfo], int]:
        """Detach a pane and clean up its subscriptions."""
        if name not in self.panes:
            return None, 0
        
        pane_info = self.panes[name]
        
        # Clean up subscriptions
        tokens_to_remove = list(self.pane_subscriptions.get(name, set()))
        for token in tokens_to_remove:
            if token in self.subscriptions:
                del self.subscriptions[token]
        
        # Clean up registry entries
        del self.panes[name]
        if pane_info.pane_id in self.pane_id_to_name:
            del self.pane_id_to_name[pane_info.pane_id]
        if name in self.pane_subscriptions:
            del self.pane_subscriptions[name]
        
        return pane_info, len(tokens_to_remove)
    
    def get_pane(self, name: str, ctx: Optional[Context] = None) -> Optional[PaneInfo]:
        """Get pane info by name, handling special 'primary' name.
        
        Args:
            name: Pane name or "primary" for the primary pane
            ctx: Optional context for auto-attachment logging
            
        Returns:
            PaneInfo if found, None otherwise
        """
        # Handle special "primary" name
        if name == "primary":
            pane = self.get_primary_pane()
            if not pane:
                # Try to auto-attach launch pane if available
                global _launch_pane_info
                if _launch_pane_info:
                    pane_id, session, window, pane_index, method = _launch_pane_info
                    try:
                        pane = self.attach_pane(
                            name="origin",
                            pane_id=pane_id,
                            session=session,
                            window=window,
                            pane_index=pane_index,
                            is_primary=True
                        )
                        if ctx:
                            asyncio.create_task(
                                ctx.info(f"Auto-attached launch pane as origin (primary): {pane_id}")
                            )
                    except ValueError:
                        # Max panes reached or other error
                        pass
            return pane
        
        # Regular pane lookup
        pane = self.panes.get(name)
        if pane:
            pane.last_accessed = datetime.now()
        return pane
    
    def get_primary_pane(self) -> Optional[PaneInfo]:
        """Get the primary pane if one is set."""
        for pane in self.panes.values():
            if pane.is_primary:
                return pane
        return None
    
    def create_subscription(
        self,
        pane_name: str,
        include_colors: bool,
        initial_lines: int,
        initial_content: List[str],
        ctx: Optional[Context] = None,
    ) -> str:
        """Create a new subscription for a pane.
        
        Args:
            pane_name: Name of the pane or "primary"
            include_colors: Whether to include color codes
            initial_lines: Number of lines recorded
            initial_content: Initial content to buffer
            ctx: Optional context for auto-attachment logging
        """
        # Get the pane (handles "primary" specially)
        pane = self.get_pane(pane_name, ctx)
        if not pane:
            if pane_name == "primary":
                raise ValueError("No primary pane available")
            else:
                raise ValueError(f"Pane '{pane_name}' is not attached")
        
        # Use actual pane name (not "primary")
        actual_pane_name = pane.name
        token = uuid4().hex
        
        subscription = PaneSubscription(
            pane_name=actual_pane_name,
            pane_id=pane.pane_id,
            include_colors=include_colors,
            lines_recorded=initial_lines,
            buffer=deque(initial_content, maxlen=self.max_buffer_lines),
            max_buffer_lines=self.max_buffer_lines,
            last_snapshot=initial_content[-100:] if initial_content else [],  # Keep last 100 for comparison
            snapshot_ready=bool(initial_content),
        )
        
        self.subscriptions[token] = subscription
        if actual_pane_name not in self.pane_subscriptions:
            self.pane_subscriptions[actual_pane_name] = set()
        self.pane_subscriptions[actual_pane_name].add(token)
        
        return token
    
    def cleanup_idle_subscriptions(self, max_age: timedelta = DEFAULT_BUFFER_CLEANUP_AGE) -> int:
        """Remove subscriptions that haven't been accessed recently."""
        now = datetime.now()
        tokens_to_remove = []
        
        for token, sub in self.subscriptions.items():
            if now - sub.last_accessed > max_age:
                tokens_to_remove.append(token)
        
        for token in tokens_to_remove:
            sub = self.subscriptions[token]
            self.subscriptions.pop(token, None)
            if sub.pane_name in self.pane_subscriptions:
                self.pane_subscriptions[sub.pane_name].discard(token)
        
        return len(tokens_to_remove)
    
    def get_buffer_stats(self) -> BufferStatsResult:
        """Get memory usage statistics."""
        total_lines = sum(len(sub.buffer) for sub in self.subscriptions.values())
        # Rough estimate: 100 bytes per line average
        memory_estimate_mb = (total_lines * 100) / (1024 * 1024)
        
        pane_stats = []
        for name, pane in self.panes.items():
            pane_subs = self.pane_subscriptions.get(name, set())
            pane_lines = sum(
                len(self.subscriptions[token].buffer) 
                for token in pane_subs 
                if token in self.subscriptions
            )
            pane_stats.append({
                "name": name,
                "pane_id": pane.pane_id,
                "active_subscriptions": len(pane_subs),
                "buffer_lines": pane_lines,
                "last_accessed": pane.last_accessed.isoformat(),
            })
        
        return {
            "total_panes_attached": len(self.panes),
            "total_active_subscriptions": len(self.subscriptions),
            "total_buffer_lines": total_lines,
            "max_buffer_lines_per_pane": self.max_buffer_lines,
            "memory_estimate_mb": memory_estimate_mb,
            "panes": pane_stats,
        }


# Global registry instance
_registry = TmuxPaneRegistry()

# MCP Server instance
MCP_SERVER = FastMCP("tooldex-tmux-advanced")

# Launch pane detection state
_launch_pane_info: Optional[Tuple[str, str, str, int, int]] = None


def _detect_launch_pane() -> Optional[Tuple[str, str, str, int, int]]:
    """Detect the tmux pane from which this server was launched.
    
    Uses multiple detection methods in order of reliability:
    1. TOOLDEX_PRIMARY_PANE environment variable (explicit)
    2. TMUX_PANE environment variable (tmux native)
    3. Parent process TTY tracking
    4. Tmux client detection via socket
    
    Returns: (pane_id, session, window, pane_index, detection_method) or None
    """
    detection_methods = []
    
    # Method 1: Explicit environment variable
    primary_pane = os.environ.get("TOOLDEX_PRIMARY_PANE")
    if primary_pane:
        detection_methods.append(("env:TOOLDEX_PRIMARY_PANE", primary_pane))
    
    # Method 2: TMUX_PANE (set when running inside tmux)
    tmux_pane = os.environ.get("TMUX_PANE")
    if tmux_pane:
        detection_methods.append(("env:TMUX_PANE", tmux_pane))
    
    # Method 3: Parent process TTY tracking
    try:
        # Get parent process ID
        ppid = os.getppid()
        
        # Try to find tmux pane associated with parent process
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_id},#{pane_pid},#{session_name},#{window_index},#{pane_index}"],
            capture_output=True,
            text=True,
            timeout=1
        )
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                parts = line.split(',')
                if len(parts) >= 5:
                    pane_id, pane_pid, session, window, pane_index = parts[:5]
                    # Check if this pane's process is our parent or ancestor
                    if pane_pid and _is_process_ancestor(int(pane_pid), ppid):
                        detection_methods.append(("process:parent", pane_id))
                        break
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError):
        pass
    
    # Method 4: TTY-based detection
    try:
        # Get current TTY
        tty = os.ttyname(sys.stdin.fileno()) if sys.stdin.isatty() else None
        if tty:
            # Find tmux pane with matching TTY
            result = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", "#{pane_id},#{pane_tty},#{session_name},#{window_index},#{pane_index}"],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    parts = line.split(',')
                    if len(parts) >= 5:
                        pane_id, pane_tty, session, window, pane_index = parts[:5]
                        if pane_tty == tty:
                            detection_methods.append(("tty:match", pane_id))
                            break
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass
    
    # Method 5: Socket/client detection
    tmux_socket = os.environ.get("TMUX")
    if tmux_socket:
        try:
            # Extract socket info and try to find active client
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{pane_id},#{session_name},#{window_index},#{pane_index}"],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode == 0:
                parts = result.stdout.strip().split(',')
                if len(parts) >= 4:
                    pane_id = parts[0]
                    detection_methods.append(("socket:active", pane_id))
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass
    
    # Try each detection method and validate
    for method, pane_id in detection_methods:
        try:
            # Validate and get full pane info
            result = subprocess.run(
                ["tmux", "display-message", "-p", "-t", pane_id, 
                 "#{pane_id},#{session_name},#{window_index},#{pane_index}"],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode == 0:
                parts = result.stdout.strip().split(',')
                if len(parts) >= 4:
                    pane_id, session, window_str, pane_index_str = parts[:4]
                    window = int(window_str)
                    pane_index = int(pane_index_str)
                    return (pane_id, session, window, pane_index, method)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError):
            continue
    
    return None


def _is_process_ancestor(potential_ancestor: int, process_pid: int, max_depth: int = 10) -> bool:
    """Check if a PID is an ancestor of another process."""
    current_pid = process_pid
    depth = 0
    
    while depth < max_depth:
        if current_pid == potential_ancestor:
            return True
        
        try:
            # Get parent PID from /proc filesystem
            with open(f"/proc/{current_pid}/stat", 'r') as f:
                fields = f.read().split(')')[-1].split()
                parent_pid = int(fields[1])  # ppid is the 4th field after the command
                
                if parent_pid == 0 or parent_pid == 1:  # Reached init
                    break
                    
                current_pid = parent_pid
                depth += 1
        except (FileNotFoundError, IOError, ValueError, IndexError):
            break
    
    return False


async def _initialize_launch_pane(ctx: Optional[Context[ServerSession, None]] = None) -> bool:
    """Initialize launch pane detection on server startup.
    
    Returns: True if launch pane was detected and attached
    """
    global _launch_pane_info
    
    # Skip if already initialized
    if _launch_pane_info is not None:
        return _registry.get_primary_pane() is not None
    
    # Detect launch pane
    detection_result = _detect_launch_pane()
    if not detection_result:
        if ctx:
            await ctx.info("No launch pane detected. Server running in external mode.")
        return False
    
    pane_id, session, window, pane_index, method = detection_result
    _launch_pane_info = (pane_id, session, window, pane_index, method)
    
    # Auto-attach as primary if not already attached
    if not _registry.get_primary_pane():
        try:
            pane_info = _registry.attach_pane(
                name="origin",
                pane_id=pane_id,
                session=session,
                window=window,
                pane_index=pane_index,
                is_primary=True
            )
            
            if ctx:
                await ctx.info(
                    f"Auto-attached launch pane as 'origin' (primary): {pane_id} "
                    f"[detected via {method}]"
                )
            return True
        except ValueError as e:
            if ctx:
                await ctx.warning(f"Failed to auto-attach launch pane: {e}")
    
    return False


async def _run_tmux_command(*args: str) -> str:
    """Execute a tmux command and return stdout."""
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(
            f"tmux command {' '.join(args)} failed with exit code {process.returncode}: "
            f"{stderr.decode().strip()}"
        )
    return stdout.decode("utf-8")


def _parse_pane_identifier(identifier: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Parse various tmux pane identifier formats.
    
    Returns: (session, window, pane_index) where any can be None
    """
    # Try session:window.pane format (e.g., "main:1.2")
    match = re.match(r'^([^:]+):(\d+)\.(\d+)$', identifier)
    if match:
        return match.group(1), int(match.group(2)), int(match.group(3))
    
    # Try window.pane format (e.g., "1.2")
    match = re.match(r'^(\d+)\.(\d+)$', identifier)
    if match:
        return None, int(match.group(1)), int(match.group(2))
    
    # Try just pane ID (e.g., "%15")
    if identifier.startswith('%'):
        return None, None, None
    
    # Assume it's a session name or window index
    if identifier.isdigit():
        return None, int(identifier), None
    
    return identifier, None, None


async def _get_pane_info(identifier: str) -> Tuple[str, str, int, int]:
    """Get detailed pane information from an identifier.
    
    Returns: (pane_id, session, window, pane_index)
    """
    # Get pane details using display-message
    format_str = "#{pane_id},#{session_name},#{window_index},#{pane_index}"
    output = await _run_tmux_command(
        "tmux", "display-message", "-p", "-t", identifier, format_str
    )
    
    parts = output.strip().split(',')
    if len(parts) != 4:
        raise ValueError(f"Invalid pane identifier: {identifier}")
    
    pane_id = parts[0]
    session = parts[1]
    window = int(parts[2])
    pane_index = int(parts[3])
    
    return pane_id, session, window, pane_index


async def _capture_pane_lines(
    pane_id: str,
    lines: int,
    include_colors: bool
) -> Tuple[List[str], bool]:
    """Capture the last N lines from a tmux pane."""
    if lines <= 0:
        raise ValueError("lines must be positive")
    
    # Capture with history
    start = f"-{lines + 1}"
    args = ["tmux", "capture-pane", "-t", pane_id, "-p", "-S", start]
    if include_colors:
        args.append("-e")
    
    output = await _run_tmux_command(*args)
    captured_lines = output.splitlines()
    
    # Check if truncated
    truncated = len(captured_lines) > lines
    if truncated:
        captured_lines = captured_lines[-lines:]
    
    return captured_lines, truncated


async def _get_pane_line_count(pane_id: str) -> int:
    """Get total line count for a pane (history + visible)."""
    output = await _run_tmux_command(
        "tmux",
        "display-message",
        "-p",
        "-t",
        pane_id,
        "#{history_size},#{pane_height}"
    )
    
    parts = output.strip().split(',')
    if len(parts) != 2:
        return 0
    
    try:
        history = int(parts[0])
        height = int(parts[1])
        return history + height
    except ValueError:
        return 0


@MCP_SERVER.tool()
async def attach_pane(
    ctx: Context[ServerSession, None],
    name: str,
    pane_identifier: str = "current",
    is_primary: bool = False,
) -> AttachResult:
    """Attach a tmux pane with a descriptive name for tracking.
    
    Args:
        name: Descriptive name for the pane (e.g., "gdb_debugger", "minecraft_server")
              Cannot be "primary" as it's reserved
        pane_identifier: Tmux pane identifier (e.g., "%0", "1.2", "session:0.0", "current" for launch pane)
        is_primary: Whether this should be marked as the primary pane
    """
    # Initialize launch pane if needed
    await _initialize_launch_pane(ctx)
    
    # Check for reserved names
    if name in RESERVED_PANE_NAMES:
        raise ValueError(
            f"'{name}' is a reserved pane name and cannot be used for attachment. "
            f"Reserved names: {', '.join(RESERVED_PANE_NAMES)}"
        )
    
    # Validate name
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise ValueError(
            "Pane name must contain only alphanumeric characters, underscores, and hyphens"
        )
    
    # Handle special "current" identifier
    if pane_identifier == "current":
        if _launch_pane_info:
            pane_id, session, window, pane_index, _ = _launch_pane_info
        else:
            raise ValueError(
                "Cannot use 'current' identifier: no launch pane detected. "
                "Specify an explicit pane identifier instead."
            )
    else:
        # Get detailed pane info
        pane_id, session, window, pane_index = await _get_pane_info(pane_identifier)
    
    # If marking as primary, clear other primary flags
    if is_primary:
        for pane in _registry.panes.values():
            pane.is_primary = False
    
    # Attach the pane
    pane_info = _registry.attach_pane(
        name=name,
        pane_id=pane_id,
        session=session,
        window=window,
        pane_index=pane_index,
        is_primary=is_primary
    )
    
    await ctx.info(
        f"Attached pane '{name}' -> {pane_id} "
        f"(session:{session}, window:{window}, index:{pane_index})"
    )
    
    return {
        "name": name,
        "pane_id": pane_id,
        "session": session,
        "window": window,
        "pane_index": pane_index,
        "attached_at": pane_info.attached_at.isoformat(),
        "is_primary": is_primary,
    }


@MCP_SERVER.tool()
async def detach_pane(
    ctx: Context[ServerSession, None],
    name: str,
) -> DetachResult:
    """Detach a previously attached pane and clean up its resources.
    
    Args:
        name: Name of the pane to detach
    """
    pane_info, cleared_subs = _registry.detach_pane(name)
    
    if pane_info:
        await ctx.info(
            f"Detached pane '{name}' ({pane_info.pane_id}), "
            f"cleared {cleared_subs} subscriptions"
        )
        return {
            "name": name,
            "pane_id": pane_info.pane_id,
            "was_attached": True,
            "active_subscriptions_cleared": cleared_subs,
        }
    else:
        return {
            "name": name,
            "pane_id": "",
            "was_attached": False,
            "active_subscriptions_cleared": 0,
        }


@MCP_SERVER.tool()
async def list_attached_panes(
    ctx: Context[ServerSession, None],
) -> ListPanesResult:
    """List all currently attached panes with their details."""
    primary = _registry.get_primary_pane()
    
    panes_list = []
    for name, pane in _registry.panes.items():
        pane_dict = pane.to_dict()
        # Add subscription info
        subs = _registry.pane_subscriptions.get(name, set())
        pane_dict["active_subscriptions"] = len(subs)
        panes_list.append(pane_dict)
    
    # Sort by attachment time (newest first)
    panes_list.sort(key=lambda x: x["attached_at"], reverse=True)
    
    return {
        "total_attached": len(_registry.panes),
        "primary_pane": primary.name if primary else None,
        "panes": panes_list,
    }


@MCP_SERVER.tool()
async def run_shell(
    ctx: Context[ServerSession, None],
    command: str,
    pane_name: str = "primary",
    send_enter: bool = True,
) -> ShellResult:
    """Send a command to a specific attached tmux pane.
    
    Args:
        command: Command to send to the pane
        pane_name: Name of the attached pane (default: "primary", uses origin/launch pane)
        send_enter: Whether to send Enter key after the command
    """
    # Initialize launch pane if needed
    await _initialize_launch_pane(ctx)
    
    # Get the pane (handles "primary" specially)
    pane = _registry.get_pane(pane_name, ctx)
    if not pane:
        if pane_name == "primary":
            raise ValueError(
                "No primary pane available. Either:\n"
                "1. Launch from within tmux for automatic detection\n"
                "2. Use 'attach_pane' to manually set a primary pane"
            )
        else:
            raise ValueError(
                f"Pane '{pane_name}' is not attached. "
                f"Available panes: {list(_registry.panes.keys())}"
            )
    
    # Send the command
    await _run_tmux_command("tmux", "send-keys", "-t", pane.pane_id, command)
    if send_enter:
        await _run_tmux_command("tmux", "send-keys", "-t", pane.pane_id, "C-m")
    
    note = f"Command dispatched to pane '{pane_name}'. Output will appear in that pane."
    if not send_enter:
        note = f"Command typed in pane '{pane_name}' without executing Enter."
    
    await ctx.info(f"Sent to {pane_name} ({pane.pane_id}): {command!r}")
    
    return {
        "command": command,
        "target_pane_name": pane_name,
        "target_pane_id": pane.pane_id,
        "submitted": True,
        "triggered_enter": send_enter,
        "note": note,
    }


@MCP_SERVER.tool()
async def read_pane(
    ctx: Context[ServerSession, None],
    pane_name: str,
    lines: int = 200,
    include_colors: bool = False,
) -> PaneReadResult:
    """Capture recent output from an attached tmux pane.
    
    Args:
        pane_name: Name of the attached pane to read from (or "primary")
        lines: Number of lines to capture (max 5000)
        include_colors: Whether to include ANSI color codes
    """
    # Initialize launch pane if needed
    await _initialize_launch_pane(ctx)
    
    # Get the pane (handles "primary" specially)
    pane = _registry.get_pane(pane_name, ctx)
    if not pane:
        if pane_name == "primary":
            raise ValueError(
                "No primary pane available. Either:\n"
                "1. Launch from within tmux for automatic detection\n"
                "2. Use 'attach_pane' to manually set a primary pane"
            )
        else:
            raise ValueError(f"Pane '{pane_name}' is not attached")
    
    # Enforce reasonable limits
    lines = min(lines, MAX_INITIAL_CAPTURE_LINES)
    
    content, truncated = await _capture_pane_lines(
        pane.pane_id,
        lines,
        include_colors
    )
    
    # Calculate approximate buffer usage
    buffer_usage = (lines / _registry.max_buffer_lines) * 100
    
    await ctx.info(
        f"Captured {len(content)} lines from '{pane_name}' "
        f"(truncated={truncated}, buffer_usage={buffer_usage:.1f}%)"
    )
    
    return {
        "pane_name": pane_name,
        "pane_id": pane.pane_id,
        "lines_requested": lines,
        "lines_returned": len(content),
        "truncated": truncated,
        "buffer_usage": buffer_usage,
        "content": content,
    }


@MCP_SERVER.tool()
async def subscribe_pane(
    ctx: Context[ServerSession, None],
    pane_name: str,
    include_colors: bool = False,
    initial_lines: int = 0,
) -> SubscriptionResult:
    """Begin tracking incremental updates from an attached pane.
    
    Args:
        pane_name: Name of the attached pane to subscribe to (or "primary")
        include_colors: Whether to include ANSI color codes
        initial_lines: Number of initial lines to capture (max 5000)
    """
    # Initialize launch pane if needed
    await _initialize_launch_pane(ctx)
    
    # Get the pane (handles "primary" specially)
    pane = _registry.get_pane(pane_name, ctx)
    if not pane:
        if pane_name == "primary":
            raise ValueError(
                "No primary pane available. Either:\n"
                "1. Launch from within tmux for automatic detection\n"
                "2. Use 'attach_pane' to manually set a primary pane"
            )
        else:
            raise ValueError(f"Pane '{pane_name}' is not attached")
    
    # Get current line count
    total_lines = await _get_pane_line_count(pane.pane_id)
    
    # Capture initial content if requested
    initial_lines = min(initial_lines, MAX_INITIAL_CAPTURE_LINES)
    initial_content: List[str] = []
    initial_truncated = False
    
    if initial_lines > 0:
        initial_content, initial_truncated = await _capture_pane_lines(
            pane.pane_id,
            initial_lines,
            include_colors
        )
    
    # Create subscription (use actual pane name, not "primary")
    token = _registry.create_subscription(
        pane_name=pane.name if pane_name == "primary" else pane_name,
        include_colors=include_colors,
        initial_lines=total_lines,
        initial_content=initial_content,
        ctx=ctx,
    )
    
    actual_name = pane.name if pane_name == "primary" else pane_name
    await ctx.info(
        f"Created subscription {token} for pane '{actual_name}' "
        f"(lines_recorded={total_lines})"
    )
    
    return {
        "token": token,
        "pane_name": actual_name,
        "pane_id": pane.pane_id,
        "lines_recorded": total_lines,
        "buffer_limit": _registry.max_buffer_lines,
        "initial_lines": initial_content,
        "initial_truncated": initial_truncated,
    }


@MCP_SERVER.tool()
async def fetch_pane_updates(
    ctx: Context[ServerSession, None],
    token: str,
    timeout_seconds: float = 1.0,
    max_lines: int = 200,
) -> UpdateResult:
    """Retrieve incremental updates for an active pane subscription.
    
    Args:
        token: Subscription token from subscribe_pane
        timeout_seconds: Maximum time to wait for new content
        max_lines: Maximum lines to return in a single update
    """
    if token not in _registry.subscriptions:
        raise KeyError(f"No active subscription for token {token}")
    
    sub = _registry.subscriptions[token]
    sub.last_accessed = datetime.now()
    
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    
    while True:
        # Get current line count
        total_lines = await _get_pane_line_count(sub.pane_id)
        diff = total_lines - sub.lines_recorded
        
        if diff > 0:
            # New content available
            capture_count = min(max_lines, diff)
            new_content, was_truncated = await _capture_pane_lines(
                sub.pane_id,
                capture_count,
                sub.include_colors
            )
            
            # Update subscription state
            sub.add_lines(new_content)
            sub.lines_recorded = total_lines
            sub.last_snapshot = new_content[-100:]  # Keep last 100 for comparison
            sub.snapshot_ready = True
            
            truncated = was_truncated or diff > max_lines
            
            await ctx.debug(
                f"Subscription {token} captured {len(new_content)} new lines "
                f"(buffer: {sub.get_buffer_usage():.1f}%)"
            )
            
            return {
                "token": token,
                "pane_name": sub.pane_name,
                "pane_id": sub.pane_id,
                "new_lines": new_content,
                "lines_recorded": total_lines,
                "buffer_usage": sub.get_buffer_usage(),
                "truncated": truncated,
                "timed_out": False,
            }
        
        # Check for pane redraws (e.g., screen clear)
        snapshot_limit = 100
        new_snapshot, _ = await _capture_pane_lines(
            sub.pane_id,
            snapshot_limit,
            sub.include_colors
        )
        
        if not sub.snapshot_ready:
            sub.last_snapshot = new_snapshot
            sub.snapshot_ready = True
            sub.lines_recorded = total_lines
        elif new_snapshot != sub.last_snapshot:
            # Pane was redrawn
            sub.last_snapshot = new_snapshot
            sub.lines_recorded = total_lines
            sub.add_lines(new_snapshot)
            
            await ctx.debug(f"Subscription {token} detected pane redraw")
            
            return {
                "token": token,
                "pane_name": sub.pane_name,
                "pane_id": sub.pane_id,
                "new_lines": new_snapshot,
                "lines_recorded": total_lines,
                "buffer_usage": sub.get_buffer_usage(),
                "truncated": False,
                "timed_out": False,
            }
        
        # Check timeout
        if time.monotonic() >= deadline:
            return {
                "token": token,
                "pane_name": sub.pane_name,
                "pane_id": sub.pane_id,
                "new_lines": [],
                "lines_recorded": sub.lines_recorded,
                "buffer_usage": sub.get_buffer_usage(),
                "truncated": False,
                "timed_out": True,
            }
        
        # Wait before next check
        await asyncio.sleep(min(DEFAULT_POLL_INTERVAL, deadline - time.monotonic()))


@MCP_SERVER.tool()
async def unsubscribe_pane(
    ctx: Context[ServerSession, None],
    token: str,
) -> bool:
    """Remove a pane subscription and free its resources.
    
    Args:
        token: Subscription token to remove
    """
    if token not in _registry.subscriptions:
        return False
    
    sub = _registry.subscriptions[token]
    del _registry.subscriptions[token]
    
    if sub.pane_name in _registry.pane_subscriptions:
        _registry.pane_subscriptions[sub.pane_name].discard(token)
    
    await ctx.info(f"Unsubscribed token {token} from pane '{sub.pane_name}'")
    return True


@MCP_SERVER.tool()
async def get_buffer_stats(
    ctx: Context[ServerSession, None],
) -> BufferStatsResult:
    """Get memory usage statistics for all attached panes and subscriptions."""
    stats = _registry.get_buffer_stats()
    
    # Run cleanup if memory usage is high
    if stats["memory_estimate_mb"] > 50:  # Threshold: 50MB
        cleaned = _registry.cleanup_idle_subscriptions()
        if cleaned > 0:
            await ctx.info(f"Auto-cleaned {cleaned} idle subscriptions")
            # Recalculate stats after cleanup
            stats = _registry.get_buffer_stats()
    
    return stats


@MCP_SERVER.tool()
async def cleanup_idle_resources(
    ctx: Context[ServerSession, None],
    max_age_hours: float = 1.0,
) -> Dict[str, int]:
    """Manually trigger cleanup of idle subscriptions.
    
    Args:
        max_age_hours: Maximum age in hours for idle subscriptions
    """
    max_age = timedelta(hours=max_age_hours)
    cleaned = _registry.cleanup_idle_subscriptions(max_age)
    
    await ctx.info(f"Cleaned up {cleaned} idle subscriptions older than {max_age_hours} hours")
    
    return {
        "subscriptions_cleaned": cleaned,
        "remaining_subscriptions": len(_registry.subscriptions),
        "attached_panes": len(_registry.panes),
    }


@MCP_SERVER.tool()
async def list_tmux_hierarchy(
    ctx: Context[ServerSession, None],
) -> TmuxHierarchyResult:
    """List all tmux sessions, windows, and panes in a hierarchical structure.
    
    Returns complete tmux hierarchy to help agents understand the layout and
    identify which panes might be relevant for their task.
    """
    # Get current session/window/pane if we're in tmux
    current_session = None
    current_window = None  
    current_pane = None
    
    try:
        if os.environ.get("TMUX"):
            current_info = await _run_tmux_command(
                "tmux", "display-message", "-p",
                "#{session_name},#{window_index},#{pane_id}"
            )
            parts = current_info.strip().split(',')
            if len(parts) >= 3:
                current_session = parts[0]
                current_window = f"{parts[0]}:{parts[1]}"
                current_pane = parts[2]
    except:
        pass
    
    # Get all sessions with their info
    sessions_output = await _run_tmux_command(
        "tmux", "list-sessions", "-F",
        "#{session_name},#{session_windows},#{session_attached}"
    )
    
    sessions = []
    total_windows = 0
    total_panes = 0
    
    for session_line in sessions_output.strip().split('\n'):
        if not session_line:
            continue
            
        session_parts = session_line.split(',')
        if len(session_parts) < 2:
            continue
            
        session_name = session_parts[0]
        window_count = int(session_parts[1]) if session_parts[1].isdigit() else 0
        is_attached = session_parts[2] == '1' if len(session_parts) > 2 else False
        
        # Get windows for this session
        windows_output = await _run_tmux_command(
            "tmux", "list-windows", "-t", session_name, "-F",
            "#{window_index},#{window_name},#{window_panes},#{window_active}"
        )
        
        windows = []
        session_pane_count = 0
        
        for window_line in windows_output.strip().split('\n'):
            if not window_line:
                continue
                
            window_parts = window_line.split(',')
            if len(window_parts) < 3:
                continue
                
            window_index = int(window_parts[0]) if window_parts[0].isdigit() else 0
            window_name = window_parts[1]
            pane_count = int(window_parts[2]) if window_parts[2].isdigit() else 0
            is_active = window_parts[3] == '1' if len(window_parts) > 3 else False
            
            # Get panes for this window
            panes_output = await _run_tmux_command(
                "tmux", "list-panes", "-t", f"{session_name}:{window_index}", "-F",
                "#{pane_id},#{pane_index},#{pane_current_command},#{pane_active}"
            )
            
            panes = []
            for pane_line in panes_output.strip().split('\n'):
                if not pane_line:
                    continue
                    
                pane_parts = pane_line.split(',')
                if len(pane_parts) < 2:
                    continue
                    
                pane_id = pane_parts[0]
                pane_index = int(pane_parts[1]) if pane_parts[1].isdigit() else 0
                current_command = pane_parts[2] if len(pane_parts) > 2 else ""
                is_pane_active = pane_parts[3] == '1' if len(pane_parts) > 3 else False
                
                # Check if this pane is attached
                attached_name = _registry.pane_id_to_name.get(pane_id)
                
                panes.append({
                    "pane_id": pane_id,
                    "pane_index": pane_index,
                    "current_command": current_command,
                    "is_active": is_pane_active,
                    "is_current": pane_id == current_pane,
                    "attached_as": attached_name,
                })
            
            session_pane_count += len(panes)
            
            windows.append({
                "window_index": window_index,
                "window_name": window_name,
                "window_id": f"{session_name}:{window_index}",
                "pane_count": len(panes),
                "is_active": is_active,
                "is_current": f"{session_name}:{window_index}" == current_window,
                "panes": panes,
            })
        
        total_windows += len(windows)
        total_panes += session_pane_count
        
        sessions.append({
            "session_name": session_name,
            "window_count": len(windows),
            "pane_count": session_pane_count,
            "is_attached": is_attached,
            "is_current": session_name == current_session,
            "windows": windows,
        })
    
    await ctx.info(
        f"Listed tmux hierarchy: {len(sessions)} sessions, "
        f"{total_windows} windows, {total_panes} panes"
    )
    
    return {
        "total_sessions": len(sessions),
        "total_windows": total_windows,
        "total_panes": total_panes,
        "current_session": current_session,
        "current_window": current_window,
        "current_pane": current_pane,
        "sessions": sessions,
    }


@MCP_SERVER.tool()
async def scan_all_panes(
    ctx: Context[ServerSession, None],
    preview_lines: int = 10,
    include_empty: bool = False,
) -> PaneScanResult:
    """Scan all tmux panes and show a preview of their content.
    
    This helps agents identify which pane contains what content, making it easier
    to decide which panes to attach for specific tasks.
    
    Args:
        preview_lines: Number of lines to capture from each pane (max 50)
        include_empty: Whether to include panes with no visible content
    """
    # Limit preview lines to be reasonable
    preview_lines = min(preview_lines, 50)
    
    # Get all panes with detailed info
    panes_output = await _run_tmux_command(
        "tmux", "list-panes", "-a", "-F",
        "#{pane_id},#{session_name},#{window_index},#{pane_index},"
        "#{pane_current_command},#{pane_width}x#{pane_height}"
    )
    
    scanned_panes = []
    
    for pane_line in panes_output.strip().split('\n'):
        if not pane_line:
            continue
            
        parts = pane_line.split(',')
        if len(parts) < 6:
            continue
            
        pane_id = parts[0]
        session = parts[1]
        window = int(parts[2]) if parts[2].isdigit() else 0
        pane_index = int(parts[3]) if parts[3].isdigit() else 0
        current_command = parts[4]
        dimensions = parts[5]
        
        # Capture content preview
        try:
            content, truncated = await _capture_pane_lines(
                pane_id,
                preview_lines,
                include_colors=False
            )
            
            # Filter out empty lines at the end
            while content and not content[-1].strip():
                content.pop()
            
            # Skip empty panes if requested
            if not include_empty and not any(line.strip() for line in content):
                continue
            
            # Check if this pane is attached
            attached_name = _registry.pane_id_to_name.get(pane_id)
            
            # Try to identify the content type
            content_hints = []
            full_content = '\n'.join(content)
            
            # Common patterns to identify content
            if 'vim' in current_command or 'vi' in current_command or 'nano' in current_command:
                content_hints.append("editor")
            elif any(prompt in full_content.lower() for prompt in ['$', '#', '>', '❯']):
                content_hints.append("shell")
            elif 'git' in full_content.lower():
                content_hints.append("git")
            elif any(lang in full_content.lower() for lang in ['error', 'warning', 'failed']):
                content_hints.append("errors")
            elif any(build in full_content.lower() for build in ['compiling', 'building', 'linking']):
                content_hints.append("build")
            elif 'test' in full_content.lower() or 'spec' in full_content.lower():
                content_hints.append("tests")
            elif current_command in ['python', 'python3', 'ipython', 'node', 'irb']:
                content_hints.append("repl")
            
            # Get the last non-empty line as a summary
            last_line = ""
            for line in reversed(content):
                if line.strip():
                    last_line = line.strip()[:100]  # Limit length
                    break
            
            scanned_panes.append({
                "pane_id": pane_id,
                "session": session,
                "window": window,
                "pane_index": pane_index,
                "identifier": f"{session}:{window}.{pane_index}",
                "current_command": current_command,
                "dimensions": dimensions,
                "attached_as": attached_name,
                "content_hints": content_hints,
                "last_line": last_line,
                "preview_lines": content,
                "has_content": bool(any(line.strip() for line in content)),
            })
            
        except Exception as e:
            await ctx.debug(f"Failed to scan pane {pane_id}: {e}")
            continue
    
    await ctx.info(f"Scanned {len(scanned_panes)} panes with content")
    
    return {
        "total_panes_scanned": len(scanned_panes),
        "scan_timestamp": datetime.now().isoformat(),
        "panes": scanned_panes,
    }


@MCP_SERVER.resource(DOC_RESOURCE_URI)
async def advanced_shell_guide() -> str:
    """Return the documentation for advanced tmux MCP server usage."""
    # Get launch pane info
    launch_info = "Not detected (external mode)"
    if _launch_pane_info:
        pane_id, session, window, _, method = _launch_pane_info
        launch_info = f"{pane_id} in {session}:{window} (via {method})"
    
    # Generate dynamic documentation based on current state
    doc = f"""# Advanced Tmux MCP Server Guide

## Overview
This MCP server provides professional-grade tmux integration with:
- Automatic launch pane detection for shortcuts
- Multiple named pane attachments (currently: {len(_registry.panes)}/{_registry.max_panes})
- Memory-managed buffers (limit: {_registry.max_buffer_lines} lines/pane)
- Cross-session/window pane support
- Automatic resource cleanup

## Current State
- Launch Pane: {launch_info}
- Attached Panes: {len(_registry.panes)}
- Active Subscriptions: {len(_registry.subscriptions)}
- Primary Pane: {_registry.get_primary_pane().name if _registry.get_primary_pane() else "Not set"}

## Launch Modes

### 1. Shortcut Mode (from within tmux)
When launched from a tmux shortcut, the server automatically detects the origin pane using:
- Environment variables (TOOLDEX_PRIMARY_PANE, TMUX_PANE)
- Parent process tracking
- TTY detection
- Socket/session tracking

The launch pane is automatically available as "origin" and set as primary.

### 2. External Mode
When launched from outside tmux (e.g., system service, IDE), no automatic pane detection occurs.
You must explicitly attach panes using their identifiers.

## Available Tools

### Pane Management
- `attach_pane`: Attach a tmux pane with a descriptive name
- `detach_pane`: Detach a pane and clean up resources
- `list_attached_panes`: List all attached panes

### Pane Discovery
- `list_tmux_hierarchy`: List all tmux sessions, windows, and panes
- `scan_all_panes`: Scan all panes to preview their content

### Command Execution
- `run_shell`: Send commands to any attached pane

### Output Monitoring
- `read_pane`: One-time capture of pane output
- `subscribe_pane`: Start tracking pane updates
- `fetch_pane_updates`: Get incremental updates
- `unsubscribe_pane`: Stop tracking a pane

### Resource Management
- `get_buffer_stats`: View memory usage statistics
- `cleanup_idle_resources`: Manual resource cleanup

## Best Practices

1. **Naming Convention**: Use descriptive names like "gdb_debugger", "build_output", "test_runner"
2. **Memory Management**: Monitor buffer stats and clean up unused subscriptions
3. **Primary Pane**: Set a primary pane for default operations
4. **Cross-Session**: Use full identifiers (session:window.pane) for clarity

## Examples

### Quick start with launch pane (shortcut mode)
```
# Automatically uses the pane where MCP was launched
run_shell(command="ls -la")  # Runs in primary/origin pane
read_pane(pane_name="primary", lines=50)  # Read from launch pane
```

### Attach current pane with custom name
```
attach_pane(name="build_output", pane_identifier="current")
```

### Attach multiple panes
```
attach_pane(name="compiler", pane_identifier="dev:0.1")
attach_pane(name="test_runner", pane_identifier="dev:1.0")
attach_pane(name="logs", pane_identifier="monitoring:0.0")
```

### Monitor build output
```
token = subscribe_pane(pane_name="compiler", initial_lines=100)
# ... run build command ...
updates = fetch_pane_updates(token=token, timeout_seconds=5.0)
```

## Detection Methods
The server uses these methods to detect the launch pane (in order):
1. **env:TOOLDEX_PRIMARY_PANE** - Explicitly set environment variable
2. **env:TMUX_PANE** - Standard tmux environment variable  
3. **process:parent** - Parent process PID tracking
4. **tty:match** - TTY device matching
5. **socket:active** - Active tmux socket/client detection
"""
    return doc


def run() -> None:
    """Entry point for the MCP server."""
    # Try to initialize launch pane detection on startup
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_initialize_launch_pane())
        loop.close()
    except Exception:
        # Ignore errors during startup detection
        pass
    
    MCP_SERVER.run()


__all__ = [
    "MCP_SERVER",
    "run",
    "attach_pane",
    "detach_pane",
    "list_attached_panes",
    "list_tmux_hierarchy",
    "scan_all_panes",
    "run_shell",
    "read_pane",
    "subscribe_pane",
    "fetch_pane_updates",
    "unsubscribe_pane",
    "get_buffer_stats",
    "cleanup_idle_resources",
]
