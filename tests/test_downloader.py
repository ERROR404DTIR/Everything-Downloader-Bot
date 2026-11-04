"""Tests for the yt-dlp / aiohttp download engine."""

from __future__ import annotations

import pytest

from bot.downloader import Downloader
from bot.errors import TooLargeError, UnsupportedURLError
from bot.models import MediaInfo

@pytest.fixture
async def downloader(config):
    engine = Downloader(config)
    await engine.start()
    try:
        yield engine
    finally:
        await engine.close()


class TestAnalyzeAndDownloadDirect:
    async def test_pdf_is_detected_and_downloaded(self, downloader, file_server, tmp_path):
        body = b"%PDF-1.4 fake pdf content" * 100
        url = file_server.add("/docs/report.pdf", body, "application/pdf", "report.pdf")

        info = await downloader.analyze(url)
        assert info.kind == "file"
        assert info.title == "report.pdf"
        assert info.filesize == len(body)

        progress = []
        result = await downloader.download(url, downloader.default_choice(info), info,
                                           progress=progress.append, job_dir=tmp_path / "job")
        assert len(result.files) == 1
        file_path = result.files[0]
        assert file_path.name == "report.pdf"
        assert file_path.read_bytes() == body
        assert progress, "at least one progress callback expected"
        assert progress[-1].downloaded == len(body)

    async def test_video_extension_is_recognized(self, downloader, file_server, tmp_path):
        body = b"\x00" * 5000
        url = file_server.add("/clip.mp4", body, "video/mp4")
        info = await downloader.analyze(url)
        assert info.kind == "video"
        assert info.ext == "mp4"

        result = await downloader.download(url, downloader.default_choice(info), info,
                                           job_dir=tmp_path / "job")
        assert result.kind == "video"
        assert result.files[0].suffix == ".mp4"

    async def test_works_without_head_support(self, downloader, file_server, tmp_path):
        """Many servers reject HEAD; the ranged-GET fallback must kick in."""
        body = b"abc" * 1000
        url = file_server.add("/no-head.bin", body, "application/octet-stream", head=False)
        info = await downloader.analyze(url)
        assert info.filesize == len(body)
        assert info.kind == "file"

    async def test_filename_from_content_disposition(self, downloader, file_server, tmp_path):
        url = file_server.add(
            "/download?id=7", b"hello world", "text/plain", "سلام دنیا.txt"
        )
        info = await downloader.analyze(url)
        assert "سلام دنیا" in info.title

        result = await downloader.download(url, downloader.default_choice(info), info,
                                           job_dir=tmp_path / "job")
        assert "سلام دنیا" in result.files[0].name


class TestLimits:
    async def test_too_large_is_refused(self, downloader, file_server):
        body = b"x" * (3 * 1024 * 1024)  # config limit is 2 MB
        url = file_server.add("/big.mp4", body, "video/mp4")
        info = await downloader.analyze(url)
        assert info.filesize == len(body)
        with pytest.raises(TooLargeError):
            await downloader.download(url, downloader.default_choice(info), info)


class TestBadInput:
    async def test_non_http_url(self, downloader):
        with pytest.raises(UnsupportedURLError):
            await downloader.analyze("ftp://example.com/a.mp4")

    async def test_bale_links_are_rejected(self, downloader):
        with pytest.raises(UnsupportedURLError):
            await downloader.analyze("https://tapi.bale.ai/bot123/getMe")

    async def test_html_page_without_media(self, downloader, file_server):
        url = file_server.add("/page", b"<html>hi</html>", "text/html")
        with pytest.raises(UnsupportedURLError):
            await downloader.analyze(url)

    async def test_404(self, downloader, file_server):
        with pytest.raises(UnsupportedURLError):
            await downloader.analyze(file_server.base_url + "/missing.mp4")


class TestMisc:
    def test_choices_for_video(self, config):
        engine = Downloader(config)
        info = MediaInfo(url="https://x/y", kind="video")
        choices = engine.build_choices(info)
        keys = [c.key for c in choices]
        assert keys[0] == "best"
        assert "720" in keys
        assert "audio" in keys

    def test_no_choices_for_direct_file(self, config):
        engine = Downloader(config)
        assert engine.build_choices(MediaInfo(url="https://x/y.pdf", kind="file")) == []
        assert engine.build_choices(MediaInfo(url="https://x/y.jpg", kind="image")) == []

    def test_cleanup_removes_job_dir(self, config, tmp_path):
        engine = Downloader(config)
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        (job_dir / "a.txt").write_text("x")
        config.keep_downloaded_files = False
        engine.cleanup(job_dir)
        assert not job_dir.exists()

    def test_cleanup_keeps_files_when_configured(self, config, tmp_path):
        engine = Downloader(config)  # fixture sets keep_downloaded_files=True
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        (job_dir / "a.txt").write_text("x")
        engine.cleanup(job_dir)
        assert job_dir.exists()
