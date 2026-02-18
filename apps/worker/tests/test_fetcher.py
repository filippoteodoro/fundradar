"""Tests for the URL fetcher."""

from fundradar_worker.fetcher import compute_content_hash, extract_text_from_html


class TestExtractText:
    """Test HTML text extraction."""

    def test_extracts_body_text(self):
        html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Welcome</h1>
            <p>This is the main content.</p>
        </body>
        </html>
        """
        text, title = extract_text_from_html(html)
        assert "Welcome" in text
        assert "main content" in text
        assert title == "Test Page"

    def test_removes_script_tags(self):
        html = """
        <html>
        <body>
            <p>Content</p>
            <script>var x = 1;</script>
        </body>
        </html>
        """
        text, _ = extract_text_from_html(html)
        assert "var x" not in text
        assert "Content" in text

    def test_removes_style_tags(self):
        html = """
        <html>
        <body>
            <style>.class { color: red; }</style>
            <p>Content</p>
        </body>
        </html>
        """
        text, _ = extract_text_from_html(html)
        assert "color: red" not in text
        assert "Content" in text

    def test_removes_nav_and_footer(self):
        html = """
        <html>
        <body>
            <nav>Menu items here</nav>
            <main>Main content here</main>
            <footer>Footer links</footer>
        </body>
        </html>
        """
        text, _ = extract_text_from_html(html)
        assert "Menu items" not in text
        assert "Footer links" not in text
        assert "Main content" in text


class TestContentHash:
    """Test content hashing."""

    def test_same_content_same_hash(self):
        text = "Hello world"
        hash1 = compute_content_hash(text)
        hash2 = compute_content_hash(text)
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        hash1 = compute_content_hash("Hello")
        hash2 = compute_content_hash("World")
        assert hash1 != hash2

    def test_hash_is_short(self):
        hash1 = compute_content_hash("Test content")
        assert len(hash1) == 16  # Truncated to 16 chars
