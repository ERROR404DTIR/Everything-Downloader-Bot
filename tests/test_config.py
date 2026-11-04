"""Tests for config.json loading / validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bot.config import BALE_HARD_UPLOAD_LIMIT_MB, Config, ConfigError

VALID = {"token": "123456789:abCdEfGhIjKlMnOpQrStUvWxYz"}


def write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class TestConfigLoad:
    def test_minimal_config_gets_defaults(self, tmp_path):
        config = Config.load(write(tmp_path, VALID))
        assert config.token == VALID["token"]
        assert config.base_url == "https://tapi.bale.ai"
        assert config.max_file_size_mb == BALE_HARD_UPLOAD_LIMIT_MB
        assert config.download_dir == "downloads"
        assert config.allow_playlists is False

    def test_full_config(self, tmp_path):
        raw = {
            **VALID,
            "base_url": "https://tapi.bale.ai/",
            "download_dir": "tmp/files",
            "max_file_size_mb": 20,
            "max_concurrent_downloads": 2,
            "allow_playlists": True,
            "max_playlist_items": 5,
            "log_level": "DEBUG",
            "cookies_file": "~/cookies.txt",
        }
        config = Config.load(write(tmp_path, raw))
        assert config.base_url == "https://tapi.bale.ai"  # trailing slash removed
        assert config.max_file_size_mb == 20
        assert config.max_file_size_bytes == 20 * 1024 * 1024
        assert config.max_concurrent_downloads == 2
        assert config.allow_playlists is True
        assert config.max_playlist_items == 5
        assert config.cookies_file.endswith("cookies.txt")

    def test_size_is_capped_to_bale_limit(self, tmp_path):
        config = Config.load(write(tmp_path, {**VALID, "max_file_size_mb": 500}))
        assert config.max_file_size_mb == BALE_HARD_UPLOAD_LIMIT_MB

    def test_unknown_keys_are_reported_but_ignored(self, tmp_path):
        config = Config.load(write(tmp_path, {**VALID, "typo_key": 1}))
        assert config.unknown_keys == ["typo_key"]


class TestConfigErrors:
    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError, match="پیدا نشد"):
            Config.load(tmp_path / "nope.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ConfigError, match="JSON"):
            Config.load(path)

    def test_placeholder_token(self, tmp_path):
        with pytest.raises(ConfigError, match="placeholder"):
            Config.load(write(tmp_path, {"token": "PUT_YOUR_BOT_TOKEN_HERE"}))

    def test_empty_token(self, tmp_path):
        with pytest.raises(ConfigError, match="توکن"):
            Config.load(write(tmp_path, {"token": ""}))

    def test_malformed_token(self, tmp_path):
        with pytest.raises(ConfigError, match="ساختاری"):
            Config.load(write(tmp_path, {"token": "abcdef"}))
