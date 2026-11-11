"""The MCP server object and the decorator every AutoCAD tool is registered with."""

from __future__ import annotations

import functools
import json
import traceback
from collections.abc import Callable
from typing import Any

import anyio.to_thread
import pywintypes
from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from .com import AcadError, AcadTimeout, describe_attribute_error, describe_com_error, worker
from .session import is_busy_error, session
from .winui import describe_blockers

INSTRUCTIONS = """\
Drives the AutoCAD session already running on this PC (acad_status reports the version).

Units: coordinates and lengths are drawing units (acad_status and drawing_info
report what a unit is, e.g. millimeters). Points are [x, y] or [x, y, z] in the
World Coordinate System. Angles are degrees, counter-clockwise from +X.

Safety: the user has real production drawings open. Only drawings created
through this server (new_drawing) are editable. Never call allow_edit_document
unless the user explicitly asked to change that existing drawing. Read-only
tools work on any open drawing.

Typical workflow: acad_status -> new_drawing -> add_layer -> draw_* / add_text /
add_dimension / insert_block -> capture_view to check the result visually ->
save_document. Each drawing tool is one undo step and is rolled back
automatically if it fails. Results report entity handles; use them with
get_entity, move_entities, change_properties and delete_entities.

Templates and sheets: add_text_style, add_dimension_style and add_multileader_style make
styles (give the dimension and multileader styles the plot scale factor); set_page_setup
sets a sheet's paper size; insert_block with layout= puts a title block on a sheet.

If AutoCAD keeps rejecting calls because a command or prompt the server started
is still open in a server-created drawing, cancel_command cancels it there. It
never acts in the user's drawings; if the user is busy, ask them instead. When a
busy error names an AutoCAD dialog, only the user can answer it.
"""

mcp = MCPServer(name="autocad", title="Autodesk AutoCAD", instructions=INSTRUCTIONS, version="0.1.5")


def _where(err: BaseException) -> str:
    """' [at draw.py:120 _locate: <source line>]' for the innermost frame in our package."""
    frames = [f for f in traceback.extract_tb(err.__traceback__) if "autocad_mcp" in f.filename]
    if not frames:
        return ""
    f = frames[-1]
    return f" [at {f.filename.rsplit(chr(92), 1)[-1]}:{f.lineno} {f.name}: {(f.line or '').strip()[:120]}]"


def _blockers(err: BaseException) -> str:
    """For a busy or timed-out call: which AutoCAD dialog is in the way, if one is (no COM)."""
    if isinstance(err, AcadTimeout) or is_busy_error(err):
        return describe_blockers(session.hwnd)
    return ""


def _render(result: Any) -> Any:
    if isinstance(result, (str, Image)) or result is None:
        return result if result is not None else "ok"
    return json.dumps(result, indent=1, ensure_ascii=False, default=str)


def acad_tool(*, read_only: bool = False, destructive: bool = False,
              timeout: float = 180.0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a function as an MCP tool whose whole body runs on the COM thread."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def handler(*args: Any, **kwargs: Any) -> Any:
            def run() -> Any:
                return _render(fn(*args, **kwargs))
            run.__name__ = fn.__name__
            try:
                return await anyio.to_thread.run_sync(
                    lambda: worker.call(run, timeout=timeout), abandon_on_cancel=True)
            except AcadError as err:
                raise ToolError(str(err) + _blockers(err)) from None
            except pywintypes.com_error as err:
                raise ToolError(describe_com_error(err) + _blockers(err) + _where(err)) from None
            except AttributeError as err:
                raise ToolError(describe_attribute_error(err) + _blockers(err) + _where(err)) from None
            except (ValueError, KeyError, IndexError, TypeError) as err:
                raise ToolError(f"{type(err).__name__}: {err}{_where(err)}") from None

        annotations = ToolAnnotations(read_only_hint=read_only, destructive_hint=destructive,
                                      open_world_hint=False)
        mcp.tool(annotations=annotations, structured_output=False)(handler)
        return fn

    return decorator
