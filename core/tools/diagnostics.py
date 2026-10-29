"""
Structured network and service diagnostics for MARK LIV.

Every check returns a dict:

    {
        "tool": "check_internet_connection",
        "success": True,
        "message": "Internet connection is available",
        "detail": {...}
    }

A news-provider failure is reported separately from a general internet
connection failure so the two are never confused.
"""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from core.tools import permissions


def _result(tool: str, success: bool, message: str,
            detail: Optional[Dict[str, Any]] = None,
            error: Optional[str] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "tool": tool,
        "success": bool(success),
        "message": message,
    }
    if detail is not None:
        out["detail"] = detail
    if error is not None:
        out["error"] = error
    return out


def check_internet_connection(parameters: Optional[dict] = None,
                              **kwargs) -> Dict[str, Any]:
    """
    Check whether a general internet connection is available.

    Connects to 8.8.8.8:53 (TCP) with a 5 second timeout. This tests
    connectivity, not DNS and not any specific provider.
    """
    tool = "check_internet_connection"
    host, port = "8.8.8.8", 53
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        start = time.monotonic()
        sock.connect((host, port))
        sock.close()
        elapsed = (time.monotonic() - start) * 1000.0
        return _result(
            tool, True,
            "Internet connection is available",
            detail={"host": host, "port": port, "latency_ms": round(elapsed, 1)},
        )
    except socket.timeout:
        return _result(
            tool, False,
            f"Internet connection check timed out connecting to {host}:{port}.",
            detail={"host": host, "port": port, "timeout_s": 5.0},
            error="timeout",
        )
    except OSError as e:
        return _result(
            tool, False,
            f"Internet connection check failed: {type(e).__name__}: {e}",
            detail={"host": host, "port": port},
            error=type(e).__name__,
        )


def check_dns_resolution(parameters: Optional[dict] = None,
                         **kwargs) -> Dict[str, Any]:
    """
    Check whether DNS resolution works by resolving www.google.com.
    """
    tool = "check_dns_resolution"
    hostname = "www.google.com"
    try:
        socket.setdefaulttimeout(5.0)
        start = time.monotonic()
        ip = socket.gethostbyname(hostname)
        elapsed = (time.monotonic() - start) * 1000.0
        return _result(
            tool, True,
            "DNS resolution is working",
            detail={"hostname": hostname, "resolved_ip": ip, "latency_ms": round(elapsed, 1)},
        )
    except socket.gaierror as e:
        return _result(
            tool, False,
            f"DNS resolution failed: could not resolve {hostname}: {e}",
            detail={"hostname": hostname},
            error="gaierror",
        )
    except socket.timeout:
        return _result(
            tool, False,
            f"DNS resolution timed out for {hostname}.",
            detail={"hostname": hostname, "timeout_s": 5.0},
            error="timeout",
        )
    except Exception as e:
        return _result(
            tool, False,
            f"DNS check error: {type(e).__name__}: {e}",
            detail={"hostname": hostname},
            error=type(e).__name__,
        )


def check_news_provider(parameters: Optional[dict] = None,
                        **kwargs) -> Dict[str, Any]:
    """
    Check whether the configured news provider (DuckDuckGo News) returns real
    headlines. Reports the provider's own status independent of the general
    internet connection.
    """
    tool = "check_news_provider"
    try:
        from actions.web_search import _ddg_news
        start = time.monotonic()
        results = _ddg_news("test", max_results=1)
        elapsed = (time.monotonic() - start) * 1000.0
        if results:
            return _result(
                tool, True,
                "News provider is working",
                detail={
                    "provider": "duckduckgo_news",
                    "results": len(results),
                    "latency_ms": round(elapsed, 1),
                    "sample_title": results[0].get("title", ""),
                },
            )
        return _result(
            tool, False,
            "News provider returned no results — may be rate-limited or blocked.",
            detail={"provider": "duckduckgo_news", "results": 0,
                    "latency_ms": round(elapsed, 1)},
            error="empty_results",
        )
    except ImportError as e:
        return _result(
            tool, False,
            f"News provider check failed: required module not installed: {e}",
            detail={"provider": "duckduckgo_news"},
            error="import_error",
        )
    except Exception as e:
        return _result(
            tool, False,
            f"News provider check failed: {type(e).__name__}: {e}",
            detail={"provider": "duckduckgo_news"},
            error=type(e).__name__,
        )


def check_backend_health(parameters: Optional[dict] = None,
                         **kwargs) -> Dict[str, Any]:
    """
    Overall backend health: internet, DNS, and news provider. Each check is
    reported separately so a news failure is not mistaken for an internet
    failure.
    """
    tool = "check_backend_health"
    checks: Dict[str, Dict[str, Any]] = {
        "internet": check_internet_connection(),
        "dns": check_dns_resolution(),
        "news_provider": check_news_provider(),
    }

    failed = [name for name, c in checks.items() if not c["success"]]

    if not failed:
        return _result(
            tool, True,
            "All backend services are healthy and operational.",
            detail={name: c for name, c in checks.items()},
        )
    return _result(
        tool, False,
        f"Some backend services are failing: {', '.join(failed)}.",
        detail={name: c for name, c in checks.items()},
        error="; ".join(failed),
    )


def get_service_status(parameters: Optional[dict] = None,
                       **kwargs) -> Dict[str, Any]:
    """
    Report basic service/runtime status. Read-only.
    """
    tool = "get_service_status"
    try:
        import platform as _platform
        return _result(
            tool, True,
            "Service status retrieved.",
            detail={
                "platform": _platform.platform(),
                "python": sys.version.split()[0],
                "executable": sys.executable,
            },
        )
    except Exception as e:
        return _result(
            tool, False,
            f"Service status check failed: {type(e).__name__}: {e}",
            error=type(e).__name__,
        )


def run_development_diagnostics(parameters: Optional[dict] = None,
                                **kwargs) -> Dict[str, Any]:
    """
    Full development diagnostic: internet, DNS, news provider, backend health,
    plus the Gemini API key configuration state (without revealing the key).

    Used to answer "why isn't news working?" with verified information.
    """
    tool = "dev_diagnostics"
    backend = check_backend_health()
    configured = bool(_gemini_key_configured())
    return _result(
        tool, backend["success"],
        backend["message"],
        detail={
            "backend": backend,
            "gemini_api_key_configured": configured,
        },
        error=backend.get("error"),
    )


def _gemini_key_configured() -> bool:
    try:
        data = json_load(Path(__file__).resolve().parent.parent.parent
                         / "config" / "api_keys.json")
        return bool(str(data.get("gemini_api_key") or "").strip())
    except Exception:
        return False


def json_load(path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


# Tool declaration (auto-discovery friendly) — the dispatcher returns JSON.
def diagnostics(parameters: Optional[dict] = None,
                **kwargs) -> str:
    """
    Dispatcher for diagnostic checks. Returns a JSON string so Gemini receives
    a structured result.

    parameters.check_type: internet | dns | news_provider | backend_health |
        service_status | dev_diagnostics
    """
    import json
    params = parameters or {}
    check_type = str(params.get("check_type", "")).lower()

    handlers = {
        "internet": check_internet_connection,
        "dns": check_dns_resolution,
        "news_provider": check_news_provider,
        "backend_health": check_backend_health,
        "service_status": get_service_status,
        "dev_diagnostics": run_development_diagnostics,
    }

    handler = handlers.get(check_type)
    if not handler:
        valid = ", ".join(sorted(handlers))
        return json.dumps({
            "tool": "diagnostics",
            "success": False,
            "message": f"Invalid check_type '{check_type}'. Valid options: {valid}",
            "error": "invalid_check_type",
        })

    result = handler(params, **kwargs)
    return json.dumps(result)
