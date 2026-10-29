"""
Tool executor for MARK LIV.

Executes registered tools with argument validation, permission checks, error
handling and structured results. A tool result is only ever reported as
"success" after the handler has actually returned a value.
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Dict, List, Optional

from .registry import get_tool, get_tool_permissions
from . import permissions


class ToolExecutionError(Exception):
    """Error raised when tool execution fails."""
    pass


class ToolValidationError(Exception):
    """Error raised when tool arguments fail validation."""
    pass


class ToolPermissionError(Exception):
    """Error raised when a tool's required permissions are not granted."""
    pass


def validate_arguments(tool_def: Dict[str, Any], arguments: Dict[str, Any]) -> None:
    """
    Validate tool arguments against the tool's parameter schema.

    Raises:
        ToolValidationError: If validation fails
    """
    schema = tool_def.get("parameters", {})
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for param in required:
        if param not in arguments:
            raise ToolValidationError(f"Missing required parameter: {param}")

    for param in arguments:
        if param not in properties:
            print(f"[ToolExecutor] Warning: Unknown parameter '{param}' in arguments")


def check_tool_permissions(name: str) -> List[str]:
    """
    Return the permissions for `name` that still need approval.

    Empty list = the tool may run.
    """
    return permissions.check_permissions(name)


def execute_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execute a registered tool.

    Returns a dict:
        {"success": True,  "result": <handler return value>}
        {"success": False, "error": <str>}
    """
    tool = get_tool(name)
    if not tool:
        return {
            "success": False,
            "error": f"Tool '{name}' not found in registry",
            "tool": name,
        }

    arguments = arguments or {}

    # Permission check — never execute without granted permissions.
    blocked = check_tool_permissions(name)
    if blocked:
        return {
            "success": False,
            "error": (
                f"Tool '{name}' requires approval for: {', '.join(blocked)}. "
                "Request permission before running."
            ),
            "tool": name,
            "approval_required": blocked,
        }

    try:
        validate_arguments(tool, arguments)

        handler = tool.get("handler")
        if not handler or not callable(handler):
            return {
                "success": False,
                "error": f"Tool '{name}' has no callable handler",
                "tool": name,
            }

        print(f"[ToolExecutor] Executing tool: {name} with arguments: {arguments}")
        result = handler(**arguments)

        return {
            "success": True,
            "result": result,
            "tool": name,
        }

    except ToolValidationError as e:
        print(f"[ToolExecutor] Validation error for tool '{name}': {e}")
        return {
            "success": False,
            "error": f"Validation error: {e}",
            "tool": name,
        }
    except Exception as e:
        print(f"[ToolExecutor] Execution error for tool '{name}': {e}")
        print(f"[ToolExecutor] Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Execution error: {type(e).__name__}: {e}",
            "tool": name,
        }


def format_tool_result(result: Dict[str, Any]) -> str:
    """
    Format a tool execution result for display.

    Returns a JSON string when the result is structured, otherwise a plain
    string — so Gemini always receives a parseable, truthful value.
    """
    if not result["success"]:
        return f"Tool execution failed: {result.get('error', 'Unknown error')}"

    output = result.get("result")
    if isinstance(output, (dict, list)):
        return json.dumps(output, indent=2)
    if isinstance(output, str):
        return output
    return str(output)
