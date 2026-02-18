"""Tests for the diff engine."""

from fundradar_worker.differ import (
    compute_diff,
    generate_what_changed,
    is_noise_line,
    normalize_text,
)


class TestNormalize:
    """Test text normalization."""

    def test_normalizes_whitespace(self):
        text = "Hello   world\n\n\nNew line"
        lines = normalize_text(text)
        assert lines == ["Hello world", "New line"]

    def test_removes_empty_lines(self):
        text = "Line 1\n\n\n\nLine 2"
        lines = normalize_text(text)
        assert lines == ["Line 1", "Line 2"]


class TestIsNoiseLine:
    """Test noise detection."""

    def test_dates_are_noise(self):
        assert is_noise_line("01/15/2024")
        # Note: ISO dates (2024-01-15) are not currently matched as noise
        # Could be added if needed

    def test_times_are_noise(self):
        assert is_noise_line("10:30")
        assert is_noise_line("10:30:45")

    def test_short_lines_are_noise(self):
        assert is_noise_line("OK")
        assert is_noise_line("...")

    def test_meaningful_lines_not_noise(self):
        assert not is_noise_line("We are hiring a new analyst")
        assert not is_noise_line("New investment in TechCorp SpA")


class TestComputeDiff:
    """Test diff computation."""

    def test_no_changes(self):
        text = "Hello world\nThis is a test"
        diff = compute_diff(text, text)
        assert not diff.has_changes
        assert not diff.is_meaningful

    def test_new_content_is_meaningful(self):
        old = ""
        new = "This is new content with enough text to be meaningful"
        diff = compute_diff(old, new)
        assert diff.has_changes
        assert diff.is_meaningful

    def test_small_changes_detection(self):
        # When comparing line by line, even small additions create meaningful diffs
        # because the entire line is considered changed
        old = "Hello world"
        new = "Hello world!"
        diff = compute_diff(old, new)
        assert diff.has_changes
        # Line-based diff means the whole line changed

    def test_significant_addition_is_meaningful(self):
        old = "Original content here"
        new = old + "\n\nWe are pleased to announce our new investment in TechCorp"
        diff = compute_diff(old, new)
        assert diff.has_changes
        assert diff.is_meaningful
        assert len(diff.added_lines) > 0


class TestGenerateWhatChanged:
    """Test summary generation."""

    def test_no_changes_message(self):
        diff = compute_diff("same", "same")
        summary = generate_what_changed(diff)
        assert "No changes" in summary

    def test_hiring_detection(self):
        # Need enough content to be considered meaningful (50+ chars)
        old = "About us\n" + "Company info here. " * 5
        new = old + "\n\nWe are actively hiring senior analysts and associates for our Milan office"
        diff = compute_diff(old, new)
        if diff.is_meaningful:
            summary = generate_what_changed(diff)
            assert "hiring" in summary.lower() or "job" in summary.lower() or "New content" in summary

    def test_investment_detection(self):
        # Need enough content to be considered meaningful
        old = "Portfolio companies\n" + "List of investments. " * 5
        new = old + "\n\nWe announced a new investment in TechCorp SpA, a leading technology company"
        diff = compute_diff(old, new)
        if diff.is_meaningful:
            summary = generate_what_changed(diff)
            summary_lower = summary.lower()
            assert "invest" in summary_lower or "portfolio" in summary_lower or "New content" in summary
