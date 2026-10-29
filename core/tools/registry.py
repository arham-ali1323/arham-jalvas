"""
Tool registry for MARK LIV.

Manages registration and discovery of tools that JARVIS can use.
"""
from typing import Dict, List, Callable, Any, Optional
import threading


class ToolRegistry:
    """Registry for tools that JARVIS can invoke."""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(self, tool_def: Dict[str, Any]) -> None:
        """
        Register a tool.

        Args:
            tool_def: Tool definition dict with keys:
                - name: str
                - description: str
                - parameters: dict (JSON Schema)
                - handler: callable
                - permissions: list[str]
        """
        with self._lock:
            name = tool_def.get("name")
            if not name:
                raise ValueError("Tool must have a name")

            if name in self._tools:
                print(f"[ToolRegistry] Tool '{name}' already registered, overwriting")

            self._tools[name] = tool_def
            print(f"[ToolRegistry] Registered tool: {name}")

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a tool by name."""
        with self._lock:
            return self._tools.get(name)

    def list_all(self) -> List[Dict[str, Any]]:
        """List all registered tools."""
        with self._lock:
            return list(self._tools.values())

    def get_names(self) -> List[str]:
        """Get list of all tool names."""
        with self._lock:
            return list(self._tools.keys())

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        with self._lock:
            return name in self._tools

    def get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """Get the parameter schema for a tool."""
        tool = self.get(name)
        if tool:
            return tool.get("parameters")
        return None

    def get_permissions(self, name: str) -> List[str]:
        """Get the required permissions for a tool."""
        tool = self.get(name)
        if tool:
            return tool.get("permissions", [])
        return []

    def get_declarations(self) -> List[Dict[str, Any]]:
        """Gemini Live function declarations for every registered tool."""
        out: List[Dict[str, Any]] = []
        with self._lock:
            for tool in self._tools.values():
                out.append({
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "OBJECT", "properties": {}}),
                })
        return out


# Global registry instance
_registry = ToolRegistry()


def register_tool(tool_def: Dict[str, Any]) -> None:
    """Register a tool with the global registry."""
    _registry.register(tool_def)


def get_tool(name: str) -> Optional[Dict[str, Any]]:
    """Get a tool from the global registry."""
    return _registry.get(name)


def list_tools() -> List[Dict[str, Any]]:
    """List all tools from the global registry."""
    return _registry.list_all()


def get_tool_names() -> List[str]:
    """Get all tool names from the global registry."""
    return _registry.get_names()


def has_tool(name: str) -> bool:
    """Check if a tool exists in the global registry."""
    return _registry.has(name)


def get_tool_schema(name: str) -> Optional[Dict[str, Any]]:
    """Get the parameter schema for a tool."""
    return _registry.get_schema(name)


def get_tool_permissions(name: str) -> List[str]:
    """Get the required permissions for a tool."""
    return _registry.get_permissions(name)


def get_declarations() -> List[Dict[str, Any]]:
    """Gemini Live function declarations for every registered tool."""
    return _registry.get_declarations()
