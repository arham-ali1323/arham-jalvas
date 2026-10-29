"""
Tests for news search functionality.
"""
import pytest
from actions.web_search import _format_news, _format_ddg


class TestFormatters:
    """Test result formatting functions."""

    def test_format_ddg_success(self):
        """Test formatting DDG search results."""
        results = [
            {"title": "Title 1", "snippet": "Snippet 1", "url": "http://url1.com"},
            {"title": "Title 2", "snippet": "Snippet 2", "url": "http://url2.com"}
        ]
        formatted = _format_ddg("test query", results)

        assert "Search results for: test query" in formatted
        assert "Title 1" in formatted
        assert "Snippet 1" in formatted
        assert "http://url1.com" in formatted

    def test_format_ddg_empty(self):
        """Test formatting empty DDG results."""
        formatted = _format_ddg("test query", [])
        assert formatted == "No results found for: test query"

    def test_format_news_success(self):
        """Test formatting news results."""
        results = [
            {
                "title": "News 1",
                "snippet": "Snippet 1",
                "url": "http://news1.com",
                "source": "Source 1"
            }
        ]
        formatted = _format_news("news query", results)

        assert "Latest news: news query" in formatted
        assert "News 1" in formatted
        assert "[Source 1]" in formatted
        assert "Snippet 1" in formatted

    def test_format_news_empty(self):
        """Test formatting empty news results."""
        formatted = _format_news("news query", [])
        assert formatted == "No news found for: news query"


class TestWebSearchIntegration:
    """Integration tests for web_search tool."""

    def test_web_search_news_mode(self):
        """Test web_search in news mode."""
        with pytest.skip("Requires live DDG connection"):
            from actions.web_search import web_search
            result = web_search({"query": "test", "mode": "news"})
            assert "News" in result or "No news" in result

    def test_web_search_default_mode(self):
        """Test web_search in default search mode."""
        with pytest.skip("Requires live DDG connection"):
            from actions.web_search import web_search
            result = web_search({"query": "test"})
            assert "test" in result.lower() or "No results" in result
