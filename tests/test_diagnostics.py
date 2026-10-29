"""
Tests for diagnostic tools.
"""
import pytest
from unittest.mock import patch, MagicMock
from actions.diagnostics import (
    check_internet_connection,
    check_dns_resolution,
    check_news_provider,
    check_backend_health,
    get_service_status,
    diagnostics
)
from actions.web_search import _ddg_news


class TestInternetConnection:
    """Test internet connection diagnostics."""

    @patch('socket.socket')
    def test_internet_success(self, mock_socket):
        """Test successful internet connection check."""
        mock_socket_instance = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_socket_instance

        result = check_internet_connection()
        assert "Internet connection is available" in result

    @patch('socket.socket')
    def test_internet_timeout(self, mock_socket):
        """Test internet connection timeout."""
        import socket
        mock_socket.side_effect = socket.timeout()

        result = check_internet_connection()
        assert "timed out" in result.lower()

    @patch('socket.socket')
    def test_internet_error(self, mock_socket):
        """Test internet connection error."""
        mock_socket.side_effect = Exception("Network error")

        result = check_internet_connection()
        assert "failed" in result.lower()


class TestDNSResolution:
    """Test DNS resolution diagnostics."""

    @patch('socket.gethostbyname')
    def test_dns_success(self, mock_gethostbyname):
        """Test successful DNS resolution."""
        mock_gethostbyname.return_value = "142.250.185.238"

        result = check_dns_resolution()
        assert "DNS resolution is working" in result

    @patch('socket.gethostbyname')
    def test_dns_timeout(self, mock_gethostbyname):
        """Test DNS resolution timeout."""
        import socket
        mock_gethostbyname.side_effect = socket.timeout()

        result = check_dns_resolution()
        assert "timed out" in result.lower()

    @patch('socket.gethostbyname')
    def test_dns_failure(self, mock_gethostbyname):
        """Test DNS resolution failure."""
        import socket
        mock_gethostbyname.side_effect = socket.gaierror("Name resolution failed")

        result = check_dns_resolution()
        assert "failed" in result.lower()


class TestNewsProvider:
    """Test news provider diagnostics."""

    @patch('actions.web_search._ddg_news')
    def test_news_provider_success(self, mock_news):
        """Test successful news provider check."""
        mock_news.return_value = [{"title": "Test"}]

        result = check_news_provider()
        assert "working" in result.lower()

    @patch('actions.web_search._ddg_news')
    def test_news_provider_empty(self, mock_news):
        """Test news provider with empty results."""
        mock_news.return_value = []

        result = check_news_provider()
        assert "empty" in result.lower()

    @patch('actions.web_search._ddg_news')
    def test_news_provider_import_error(self, mock_news):
        """Test news provider with import error."""
        mock_news.side_effect = ImportError("No module named 'primp'")

        result = check_news_provider()
        assert "module" in result.lower()

    @patch('actions.web_search._ddg_news')
    def test_news_provider_error(self, mock_news):
        """Test news provider with generic error."""
        mock_news.side_effect = Exception("Network error")

        result = check_news_provider()
        assert "failed" in result.lower()


class TestBackendHealth:
    """Test backend health diagnostics."""

    @patch('actions.diagnostics.check_internet_connection')
    @patch('actions.diagnostics.check_dns_resolution')
    @patch('actions.diagnostics.check_news_provider')
    def test_backend_health_all_pass(self, mock_news, mock_dns, mock_internet):
        """Test backend health when all checks pass."""
        mock_internet.return_value = "Internet connection is available"
        mock_dns.return_value = "DNS resolution is working"
        mock_news.return_value = "News provider is working"

        result = check_backend_health()
        assert "healthy" in result.lower()

    @patch('actions.diagnostics.check_internet_connection')
    @patch('actions.diagnostics.check_dns_resolution')
    @patch('actions.diagnostics.check_news_provider')
    def test_backend_health_some_fail(self, mock_news, mock_dns, mock_internet):
        """Test backend health when some checks fail."""
        mock_internet.return_value = "Internet connection failed"
        mock_dns.return_value = "DNS resolution is working"
        mock_news.return_value = "News provider is working"

        result = check_backend_health()
        assert "failing" in result.lower()


class TestServiceStatus:
    """Test service status."""

    def test_service_status(self):
        """Test service status retrieval."""
        result = get_service_status()
        assert "Platform" in result
        assert "Python" in result


class TestDiagnosticsTool:
    """Test the diagnostics tool dispatcher."""

    @patch('actions.diagnostics.check_internet_connection')
    def test_diagnostics_internet(self, mock_check):
        """Test diagnostics tool with internet check."""
        mock_check.return_value = "Internet OK"

        result = diagnostics({"check_type": "internet"})
        assert result == "Internet OK"

    @patch('actions.diagnostics.check_dns_resolution')
    def test_diagnostics_dns(self, mock_check):
        """Test diagnostics tool with DNS check."""
        mock_check.return_value = "DNS OK"

        result = diagnostics({"check_type": "dns"})
        assert result == "DNS OK"

    @patch('actions.diagnostics.check_news_provider')
    def test_diagnostics_news_provider(self, mock_check):
        """Test diagnostics tool with news provider check."""
        mock_check.return_value = "News OK"

        result = diagnostics({"check_type": "news_provider"})
        assert result == "News OK"

    def test_diagnostics_invalid_type(self):
        """Test diagnostics tool with invalid check type."""
        result = diagnostics({"check_type": "invalid"})
        assert "Invalid" in result

    def test_diagnostics_no_type(self):
        """Test diagnostics tool without check type."""
        result = diagnostics({})
        assert "Invalid" in result
