"""Tests for the small pure helpers."""

from __future__ import annotations

import pytest

from bot.utils import (
    extract_url,
    guess_extension,
    human_duration,
    human_size,
    pretty_host,
    safe_filename,
    shorten,
)


class TestExtractUrl:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("https://www.youtube.com/watch?v=abc123", "https://www.youtube.com/watch?v=abc123"),
            ("سلام اینو دانلود کن https://youtu.be/xyz خوبه", "https://youtu.be/xyz"),
            ("youtu.be/xyz", "https://youtu.be/xyz"),
            ("www.example.com/file.mp4", "https://www.example.com/file.mp4"),
            ("(https://example.com/a.mp4).", "https://example.com/a.mp4"),
            ("بدون لینک", None),
            ("", None),
        ],
    )
    def test_extract(self, text, expected):
        assert extract_url(text) == expected

    def test_does_not_eat_persian_punctuation(self):
        assert extract_url("ببین https://example.com/v.mp4، ممنون") == "https://example.com/v.mp4"


class TestHumanSize:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, "نامشخص"),
            (0, "0 B"),
            (512, "512 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (5 * 1024**2, "5.0 MB"),
            (2.5 * 1024**3, "2.5 GB"),
        ],
    )
    def test_human_size(self, value, expected):
        assert human_size(value) == expected


class TestHumanDuration:
    @pytest.mark.parametrize(
        "value,expected",
        [(None, "نامشخص"), (0, "نامشخص"), (59, "0:59"), (125, "2:05"), (3725, "1:02:05")],
    )
    def test_durations(self, value, expected):
        assert human_duration(value) == expected


class TestSafeFilename:
    def test_strips_bad_characters(self):
        assert safe_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"

    def test_keeps_persian(self):
        assert safe_filename("دانلود ویدیو") == "دانلود ویدیو"

    def test_truncates_but_keeps_extension(self):
        name = safe_filename("x" * 300 + ".mp4", max_length=50)
        assert len(name) <= 50
        assert name.endswith(".mp4")

    def test_empty_falls_back(self):
        assert safe_filename("", fallback="file") == "file"
        assert safe_filename("   ", fallback="file") == "file"


class TestMisc:
    def test_pretty_host(self):
        assert pretty_host("https://www.YouTube.com/watch?v=1") == "youtube.com"
        assert pretty_host("not a url") == "لینک"

    def test_shorten(self):
        assert shorten("hello", 10) == "hello"
        assert len(shorten("a" * 100, 10)) == 10

    def test_guess_extension(self):
        assert guess_extension("video/mp4") == ".mp4"
        assert guess_extension("application/pdf") == ".pdf"
        assert guess_extension(None, "http://x/a.MKV") == ".mkv"
        assert guess_extension("application/octet-stream", "http://x/a") == ""
