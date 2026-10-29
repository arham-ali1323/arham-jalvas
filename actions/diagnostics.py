"""
Diagnostic tools for MARK LIV.

Provides safe system and network diagnostics that JARVIS can call to
troubleshoot issues.
"""
import socket
import sys
from typing import Dict, Any


def check_internet_connection(parameters: dict = None, **kwargs) -> str:
    """
    Check if internet connection is available.

    Returns:
        String with check result.
    """
    try:
        socket.setdefaulttimeout(5)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return "Internet connection is available and working. Successfully connected to 8.8.8.8:53."
    except socket.timeout:
        return "Internet connection check failed: Connection to 8.8.8.8:53 timed out after 5 seconds."
    except Exception as e:
        return f"Internet connection check failed: {type(e).__name__}: {e}"


def check_dns_resolution(parameters: dict = None, **kwargs) -> str:
    """
    Check if DNS resolution is working.

    Returns:
        String with check result.
    """
    try:
        socket.setdefaulttimeout(5)
        socket.gethostbyname("www.google.com")
        return "DNS resolution is working. Successfully resolved www.google.com."
    except socket.timeout:
        return "DNS resolution check failed: DNS lookup for www.google.com timed out."
    except socket.gaierror as e:
        return f"DNS resolution check failed: Could not resolve www.google.com: {e}"
    except Exception as e:
        return f"DNS check error: {type(e).__name__}: {e}"


def check_news_provider(parameters: dict = None, **kwargs) -> str:
    """
    Check if the news provider (DuckDuckGo) is accessible.

    Returns:
        String with check result.
    """
    try:
        from actions.web_search import _ddg_news
        results = _ddg_news("test", max_results=1)
        if results:
            return f"News provider is working. Successfully retrieved {len(results)} test result(s)."
        else:
            return "News provider check failed: DDG news search returned empty results - may be rate-limited or blocked."
    except ImportError as e:
        return f"News provider check failed: Required module not installed: {e}"
    except Exception as e:
        return f"News provider check failed: {type(e).__name__}: {e}"


def check_backend_health(parameters: dict = None, **kwargs) -> str:
    """
    Check the health of the backend services.

    Returns:
        String with overall health status.
    """
    checks = {
        "internet": check_internet_connection(),
        "dns": check_dns_resolution(),
        "news_provider": check_news_provider()
    }

    all_passed = all("failed" not in c.lower() for c in checks.values())

    if all_passed:
        return "All backend services are healthy and operational."
    else:
        failed = [name for name, result in checks.items() if "failed" in result.lower()]
        return f"Some backend services are failing: {', '.join(failed)}. Check individual diagnostics for details."


def get_service_status(parameters: dict = None, **kwargs) -> str:
    """
    Get overall service status.

    Returns:
        String with service status.
    """
    return f"Service status: Platform {sys.platform}, Python {sys.version.split()[0]}"


def diagnostics(parameters: dict = None, **kwargs) -> str:
    """
    Run diagnostic checks on system and network services.

    Args:
        parameters: dict with 'check_type' key

    Returns:
        String with diagnostic result.
    """
    params = parameters or {}
    check_type = params.get("check_type", "").lower()

    check_map = {
        "internet": check_internet_connection,
        "dns": check_dns_resolution,
        "news_provider": check_news_provider,
        "backend_health": check_backend_health,
        "service_status": get_service_status
    }

    handler = check_map.get(check_type)
    if handler:
        return handler(parameters, **kwargs)
    else:
        return f"Invalid check_type '{check_type}'. Valid options: {', '.join(check_map.keys())}"


# Tool declaration for action_loader auto-discovery
TOOL = {
    "name": "diagnostics",
    "description": "Run diagnostic checks on system and network services. Use check_type: 'internet', 'dns', 'news_provider', 'backend_health', or 'service_status'",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "check_type": {
                "type": "STRING",
                "description": "Type of diagnostic check to run: internet, dns, news_provider, backend_health, service_status"
            }
        },
        "required": ["check_type"]
    },
    "handler": diagnostics
}
