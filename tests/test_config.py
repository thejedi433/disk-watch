"""Tests for disk_watch.config module."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from disk_watch.config import (
    AlertConfig,
    Config,
    MonitorConfig,
    MonitorState,
)


class TestMonitorConfig:
    """Test MonitorConfig class."""

    def test_default_values(self) -> None:
        """Test default values."""
        config = MonitorConfig(path="/")
        assert config.path == "/"
        assert config.threshold_percent == 10.0
        assert config.enabled is True

    def test_custom_values(self) -> None:
        """Test custom values."""
        config = MonitorConfig(path="/home", threshold_percent=20.0, enabled=False)
        assert config.path == "/home"
        assert config.threshold_percent == 20.0
        assert config.enabled is False


class TestAlertConfig:
    """Test AlertConfig class."""

    def test_default_values(self) -> None:
        """Test default values."""
        config = AlertConfig()
        assert config.type == "log"
        assert config.file_path is None
        assert config.command is None

    def test_custom_values(self) -> None:
        """Test custom values."""
        config = AlertConfig(type="file", file_path="/tmp/alerts.log")
        assert config.type == "file"
        assert config.file_path == "/tmp/alerts.log"

    def test_command_config(self) -> None:
        """Test command configuration."""
        config = AlertConfig(type="command", command=["echo", "alert"])
        assert config.type == "command"
        assert config.command == ["echo", "alert"]


class TestConfig:
    """Test Config class."""

    def test_default_values(self) -> None:
        """Test default values."""
        config = Config()
        assert len(config.monitors) == 1
        assert config.monitors[0].path == "/"
        assert len(config.alerts) == 1
        assert config.alerts[0].type == "log"
        assert config.check_interval_seconds == 300

    def test_load_nonexistent_file(self) -> None:
        """Test loading non-existent file returns default config."""
        config = Config.load("/nonexistent/config.toml")
        assert config.monitors[0].path == "/"

    def test_load_valid_file(self, tmp_path: Path) -> None:
        """Test loading valid config file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
check_interval_seconds = 600
state_file = "/tmp/state.json"

[[monitors]]
path = "/home"
threshold_percent = 20.0
enabled = true

[[monitors]]
path = "/var"
threshold_percent = 15.0
enabled = false

[[alerts]]
type = "file"
file_path = "/tmp/alerts.log"
"""
        )

        config = Config.load(config_file)
        assert config.check_interval_seconds == 600
        assert config.state_file == "/tmp/state.json"
        assert len(config.monitors) == 2
        assert config.monitors[0].path == "/home"
        assert config.monitors[0].threshold_percent == 20.0
        assert config.monitors[0].enabled is True
        assert config.monitors[1].path == "/var"
        assert config.monitors[1].enabled is False
        assert len(config.alerts) == 1
        assert config.alerts[0].type == "file"

    def test_load_invalid_toml(self, tmp_path: Path) -> None:
        """Test loading invalid TOML returns default config."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid toml [[[")

        config = Config.load(config_file)
        assert config.monitors[0].path == "/"

    def test_load_empty_monitors(self, tmp_path: Path) -> None:
        """Test loading config with no monitors uses default."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("check_interval_seconds = 600\n")

        config = Config.load(config_file)
        assert len(config.monitors) == 1
        assert config.monitors[0].path == "/"

    def test_load_monitor_as_string(self, tmp_path: Path) -> None:
        """Test loading monitor specified as string."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[[monitors]]
path = "/home"
"""
        )

        config = Config.load(config_file)
        assert len(config.monitors) == 1
        assert config.monitors[0].path == "/home"
        assert config.monitors[0].threshold_percent == 10.0

    def test_from_dict_monitor_as_string(self) -> None:
        """Test _from_dict with monitor as bare string."""
        data = {
            "monitors": ["/custom/path"],
            "alerts": [],
        }
        config = Config._from_dict(data)
        assert len(config.monitors) == 1
        assert config.monitors[0].path == "/custom/path"
        assert config.monitors[0].threshold_percent == 10.0

    def test_from_dict_mixed_monitors(self) -> None:
        """Test _from_dict with mix of dict and string monitors."""
        data = {
            "monitors": [
                {"path": "/home", "threshold_percent": 5.0},
                "/var",
            ],
            "alerts": [],
        }
        config = Config._from_dict(data)
        assert len(config.monitors) == 2
        assert config.monitors[0].path == "/home"
        assert config.monitors[0].threshold_percent == 5.0
        assert config.monitors[1].path == "/var"
        assert config.monitors[1].threshold_percent == 10.0

    def test_from_dict_alert_non_dict_skipped(self) -> None:
        """Test _from_dict skips non-dict alert entries."""
        data = {
            "monitors": [],
            "alerts": ["not-a-dict", 42, None],
        }
        config = Config._from_dict(data)
        # Non-dict alerts should be skipped, leaving defaults
        assert len(config.alerts) == 1
        assert config.alerts[0].type == "log"

    def test_from_dict_skips_non_string_non_dict_monitors(self) -> None:
        """Test _from_dict skips monitor entries that are neither dict nor str."""
        data = {
            "monitors": [42, None, ["/bad"]],
            "alerts": [],
        }
        config = Config._from_dict(data)
        # All skipped, defaults applied
        assert len(config.monitors) == 1
        assert config.monitors[0].path == "/"

    def test_load_with_string_monitor(self, tmp_path: Path) -> None:
        """Test loading a TOML with inline monitor table that parses as string."""
        # TOML array entries that are just strings
        config_file = tmp_path / "config.toml"
        # Using _from_dict directly is easier; exercise via load by
        # writing TOML that yields string entries is hard since [[monitors]]
        # always yields dicts. So test the branch via _from_dict above.
        config_file.write_text(
            """
[[monitors]]
path = "/data"
threshold_percent = 7.5
enabled = false

[[alerts]]
type = "command"
command = ["echo", "disk alert"]
"""
        )
        config = Config.load(config_file)
        assert len(config.monitors) == 1
        assert config.monitors[0].path == "/data"
        assert config.monitors[0].threshold_percent == 7.5
        assert config.monitors[0].enabled is False
        assert config.alerts[0].type == "command"
        assert config.alerts[0].command == ["echo", "disk alert"]

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """Test save creates config file."""
        config_file = tmp_path / "config.toml"
        config = Config()

        assert config.save(config_file) is True
        assert config_file.exists()

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test save creates parent directories."""
        config_file = tmp_path / "subdir" / "config.toml"
        config = Config()

        assert config.save(config_file) is True
        assert config_file.exists()

    def test_save_content(self, tmp_path: Path) -> None:
        """Test save writes correct content."""
        config_file = tmp_path / "config.toml"
        config = Config(
            monitors=[MonitorConfig(path="/home", threshold_percent=20.0)],
            alerts=[AlertConfig(type="file", file_path="/tmp/alerts.log")],
            check_interval_seconds=600,
        )

        config.save(config_file)
        content = config_file.read_text()

        assert "check_interval_seconds = 600" in content
        assert 'path = "/home"' in content
        assert "threshold_percent = 20.0" in content
        assert 'type = "file"' in content
        assert 'file_path = "/tmp/alerts.log"' in content

    def test_save_returns_false_on_error(self) -> None:
        """Test save returns False on error."""
        config = Config()
        # Try to save to invalid path
        result = config.save("/proc/invalid/config.toml")
        assert result is False

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        config = Config(
            monitors=[MonitorConfig(path="/home", threshold_percent=20.0)],
            alerts=[AlertConfig(type="file", file_path="/tmp/alerts.log")],
            check_interval_seconds=600,
            state_file="/tmp/state.json",
        )

        data = config.to_dict()
        assert data["check_interval_seconds"] == 600
        assert data["state_file"] == "/tmp/state.json"
        assert len(data["monitors"]) == 1
        assert data["monitors"][0]["path"] == "/home"
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["type"] == "file"


class TestMonitorState:
    """Test MonitorState class."""

    def test_default_values(self) -> None:
        """Test default values."""
        state = MonitorState()
        assert state.last_alert_times == {}
        assert state.last_check_time is None

    def test_load_nonexistent_file(self) -> None:
        """Test loading non-existent file returns default state."""
        state = MonitorState.load("/nonexistent/state.json")
        assert state.last_alert_times == {}

    def test_load_valid_file(self, tmp_path: Path) -> None:
        """Test loading valid state file."""
        state_file = tmp_path / "state.json"
        data = {
            "last_alert_times": {"/home": 1234567890.0},
            "last_check_time": 1234567890.0,
        }
        state_file.write_text(json.dumps(data))

        state = MonitorState.load(state_file)
        assert state.last_alert_times["/home"] == 1234567890.0
        assert state.last_check_time == 1234567890.0

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Test loading invalid JSON returns default state."""
        state_file = tmp_path / "state.json"
        state_file.write_text("invalid json")

        state = MonitorState.load(state_file)
        assert state.last_alert_times == {}

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """Test save creates state file."""
        state_file = tmp_path / "state.json"
        state = MonitorState()

        assert state.save(state_file) is True
        assert state_file.exists()

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test save creates parent directories."""
        state_file = tmp_path / "subdir" / "state.json"
        state = MonitorState()

        assert state.save(state_file) is True
        assert state_file.exists()

    def test_save_content(self, tmp_path: Path) -> None:
        """Test save writes correct content."""
        state_file = tmp_path / "state.json"
        state = MonitorState(
            last_alert_times={"/home": 1234567890.0},
            last_check_time=1234567890.0,
        )

        state.save(state_file)
        content = state_file.read_text()
        data = json.loads(content)

        assert data["last_alert_times"]["/home"] == 1234567890.0
        assert data["last_check_time"] == 1234567890.0

    def test_save_returns_false_on_error(self) -> None:
        """Test save returns False on error."""
        state = MonitorState()
        # Try to save to invalid path
        result = state.save("/proc/invalid/state.json")
        assert result is False

    def test_should_alert_no_previous(self) -> None:
        """Test should_alert returns True when no previous alert."""
        state = MonitorState()
        assert state.should_alert("/home") is True

    def test_should_alert_within_cooldown(self) -> None:
        """Test should_alert returns False within cooldown."""
        state = MonitorState(last_alert_times={"/home": time.time()})
        assert state.should_alert("/home", cooldown_seconds=3600) is False

    def test_should_alert_after_cooldown(self) -> None:
        """Test should_alert returns True after cooldown."""
        state = MonitorState(last_alert_times={"/home": time.time() - 7200})
        assert state.should_alert("/home", cooldown_seconds=3600) is True

    def test_record_alert(self) -> None:
        """Test record_alert updates timestamp."""
        state = MonitorState()
        state.record_alert("/home")
        assert "/home" in state.last_alert_times
        assert state.last_alert_times["/home"] > 0
