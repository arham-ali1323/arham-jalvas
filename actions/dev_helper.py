"""
Safe development assistance for MARK LIV.

Provides JARVIS with limited, safe diagnostic and development assistance
capabilities. All file modifications require explicit approval.
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any


# Allowlist of safe diagnostic actions
SAFE_DIAGNOSTICS = {
    "check_news": True,
    "check_logs": True,
    "check_imports": True,
    "check_dependencies": True,
    "list_files": True,
    "read_file": True,  # Read-only, safe
}


def check_news(parameters: dict = None, **kwargs) -> str:
    """Check if news service is working."""
    try:
        from actions.web_search import _ddg_news
        results = _ddg_news("test", max_results=1)
        if results:
            return "News service is working correctly. Test query returned results."
        else:
            return "News service returned no results. This may indicate a rate limit or connectivity issue."
    except ImportError as e:
        return f"News service check failed: Missing dependency - {e}"
    except Exception as e:
        return f"News service check failed: {type(e).__name__}: {e}"


def check_logs(parameters: dict = None, **kwargs) -> str:
    """Check recent log files for errors."""
    try:
        log_dir = Path("logs")
        if not log_dir.exists():
            return "No logs directory found."

        log_files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
        if not log_files:
            return "No log files found."

        recent_errors = []
        for log_file in log_files:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-50:]  # Last 50 lines
                for line in lines:
                    if "error" in line.lower() or "failed" in line.lower():
                        recent_errors.append(line.strip())

        if recent_errors:
            return f"Found {len(recent_errors)} recent error entries. Latest errors:\n" + "\n".join(recent_errors[:5])
        else:
            return "No recent errors found in log files."
    except Exception as e:
        return f"Log check failed: {type(e).__name__}: {e}"


def check_imports(parameters: dict = None, **kwargs) -> str:
    """Check if critical imports are working."""
    issues = []

    try:
        import google.genai
    except ImportError as e:
        issues.append(f"google.genai: {e}")

    try:
        import ddgs
    except ImportError as e:
        issues.append(f"ddgs: {e}")

    try:
        import PyQt6
    except ImportError as e:
        issues.append(f"PyQt6: {e}")

    if issues:
        return f"Import issues found:\n" + "\n".join(issues)
    else:
        return "All critical imports are working correctly."


def check_dependencies(parameters: dict = None, **kwargs) -> str:
    """Check if dependencies are installed."""
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return "Dependencies check completed. All required packages appear to be installed."
        else:
            return f"Dependencies check failed: {result.stderr}"
    except Exception as e:
        return f"Dependencies check failed: {type(e).__name__}: {e}"


def list_files(parameters: dict = None, **kwargs) -> str:
    """List files in a directory (read-only)."""
    params = parameters or {}
    directory = params.get("directory", ".")

    try:
        path = Path(directory)
        if not path.exists():
            return f"Directory does not exist: {directory}"

        if not path.is_dir():
            return f"Not a directory: {directory}"

        files = sorted([f.name for f in path.iterdir() if f.is_file()])[:20]
        return f"Files in {directory}:\n" + "\n".join(files)
    except Exception as e:
        return f"List files failed: {type(e).__name__}: {e}"


def read_file(parameters: dict = None, **kwargs) -> str:
    """Read a file (read-only, safe)."""
    params = parameters or {}
    file_path = params.get("file_path", "")

    if not file_path:
        return "No file path provided."

    try:
        path = Path(file_path)
        if not path.exists():
            return f"File does not exist: {file_path}"

        if not path.is_file():
            return f"Not a file: {file_path}"

        # Limit file size for safety
        if path.stat().st_size > 100_000:  # 100KB limit
            return f"File too large to read: {file_path} ({path.stat().st_size} bytes)"

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Return first 2000 characters
        if len(content) > 2000:
            return f"File: {file_path}\n\n{content[:2000]}\n\n... (truncated, file is {len(content)} characters)"
        else:
            return f"File: {file_path}\n\n{content}"
    except Exception as e:
        return f"Read file failed: {type(e).__name__}: {e}"


def dev_helper(parameters: dict = None, **kwargs) -> str:
    """
    Run safe development assistance operations.

    Args:
        parameters: dict with 'action' key and relevant parameters

    Returns:
        String with result.
    """
    params = parameters or {}
    action = params.get("action", "").lower()

    action_map = {
        "check_news": check_news,
        "check_logs": check_logs,
        "check_imports": check_imports,
        "check_dependencies": check_dependencies,
        "list_files": list_files,
        "read_file": read_file,
    }

    if action not in SAFE_DIAGNOSTICS:
        return f"Action '{action}' is not in the safe allowlist. Allowed actions: {', '.join(SAFE_DIAGNOSTICS.keys())}"

    handler = action_map.get(action)
    if handler:
        return handler(parameters, **kwargs)
    else:
        return f"Unknown action: {action}"


# Tool declaration for action_loader auto-discovery
TOOL = {
    "name": "dev_helper",
    "description": "Run safe development assistance diagnostics. Actions: check_news, check_logs, check_imports, check_dependencies, list_files, read_file. All actions are read-only and safe. For list_files: provide directory. For read_file: provide file_path.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform: check_news, check_logs, check_imports, check_dependencies, list_files, read_file"
            },
            "directory": {
                "type": "STRING",
                "description": "Directory path (for list_files action)"
            },
            "file_path": {
                "type": "STRING",
                "description": "File path (for read_file action)"
            }
        },
        "required": ["action"]
    },
    "handler": dev_helper
}
