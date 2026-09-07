"""Tests for disk_watch.alerts module."""

import json
import subprocess
import sys
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from disk_watch.alerts import (
    Alert,
    CommandAlert,
    FileAlert,
    JsonAlert,
    LogAlert,
    create_handler,
)


class TestAlert:
    """Test Alert class."""

    def test_message(self) -> None:
        """Test alert message format."""
        alert = Alert(
            path="/test/path",
            percent_free=5.5,
            threshold_percent=10.0,
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
        )
        message = alert.message()
        assert "DISK ALERT" in message
        assert "/test/path" in message
        assert "5.5%" in message
        assert "10.0%" in message

    def test_to_dict(self) -> None:
        """Test alert to_dict serialization."""
        alert = Alert(
            path="/test/path",
            percent_free=5.5,
            threshold_percent=10.0,
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
        )
        data = alert.to_dict()
        assert data["path"] == "/test/path"
        assert data["percent_free"] == 5.5
        assert data["threshold_percent"] == 10.0
        assert data["timestamp"] == "2026-01-01T12:00:00"

    def test_from_dict(self) -> None:
        """Test alert from_dict deserialization."""
        data = {
            "path": "/test/path",
            "percent_free": 5.5,
            "threshold_percent": 10.0,
            "timestamp": "2026-01-01T12:00:00",
        }
        alert = Alert.from_dict(data)
        assert alert.path == "/test/path"
        assert alert.percent_free == 5.5
        assert alert.threshold_percent == 10.0
        assert alert.timestamp == datetime(2026, 1, 1, 12, 0, 0)

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test alert serialization roundtrip."""
        original = Alert(
            path="/test/path",
            percent_free=5.5,
            threshold_percent=10.0,
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
        )
        data = original.to_dict()
        restored = Alert.from_dict(data)
        assert restored.path == original.path
        assert restored.percent_free == original.percent_free
        assert restored.threshold_percent == original.threshold_percent
        assert restored.timestamp == original.timestamp


class TestLogAlert:
    """Test LogAlert handler."""

    def test_send_prints_to_stderr(self, capsys: pytest.CaptureFixture) -> None:
        """Test LogAlert sends to stderr."""
        handler = LogAlert()
        result = handler.send("Test message")

        assert result is True
        captured = capsys.readouterr()
        assert "[disk-watch] Test message" in captured.err

    def test_send_returns_true(self) -> None:
        """Test LogAlert always returns True."""
        handler = LogAlert()
        assert handler.send("Any message") is True


class TestFileAlert:
    """Test FileAlert handler."""

    def test_send_creates_file(self, tmp_path: Path) -> None:
        """Test FileAlert creates log file."""
        log_file = tmp_path / "alerts.log"
        handler = FileAlert(log_file)
        handler.send("Test message")

        assert log_file.exists()

    def test_send_appends_to_file(self, tmp_path: Path) -> None:
        """Test FileAlert appends to log file."""
        log_file = tmp_path / "alerts.log"
        handler = FileAlert(log_file)

        handler.send("First message")
        handler.send("Second message")

        content = log_file.read_text()
        assert "First message" in content
        assert "Second message" in content

    def test_send_includes_timestamp(self, tmp_path: Path) -> None:
        """Test FileAlert includes timestamp."""
        log_file = tmp_path / "alerts.log"
        handler = FileAlert(log_file)
        handler.send("Test message")

        content = log_file.read_text()
        # Should have ISO format timestamp
        assert "[" in content
        assert "]" in content

    def test_send_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test FileAlert creates parent directories."""
        log_file = tmp_path / "subdir" / "nested" / "alerts.log"
        handler = FileAlert(log_file)
        handler.send("Test message")

        assert log_file.exists()

    def test_send_returns_true_on_success(self, tmp_path: Path) -> None:
        """Test FileAlert returns True on success."""
        log_file = tmp_path / "alerts.log"
        handler = FileAlert(log_file)
        assert handler.send("Test message") is True

    def test_send_returns_false_on_error(self, tmp_path: Path) -> None:
        """Test FileAlert returns False on error."""
        # Create a directory where file should be
        log_file = tmp_path / "alerts.log"
        log_file.mkdir()
        handler = FileAlert(log_file)
        assert handler.send("Test message") is False


class TestCommandAlert:
    """Test CommandAlert handler."""

    def test_send_runs_command(self) -> None:
        """Test CommandAlert runs command."""
        handler = CommandAlert(["echo"])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = handler.send("Test message")

        assert result is True
        mock_run.assert_called_once()

    def test_send_passes_message_as_arg(self) -> None:
        """Test CommandAlert passes message as argument."""
        handler = CommandAlert(["echo"])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            handler.send("Test message")

        call_args = mock_run.call_args[0][0]
        assert "Test message" in call_args

    def test_send_returns_true_on_success(self) -> None:
        """Test CommandAlert returns True on success."""
        handler = CommandAlert(["echo"])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = handler.send("Test message")

        assert result is True

    def test_send_returns_false_on_failure(self) -> None:
        """Test CommandAlert returns False on command failure."""
        handler = CommandAlert(["false"])
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "false")
            result = handler.send("Test message")

        assert result is False

    def test_send_returns_false_on_timeout(self) -> None:
        """Test CommandAlert returns False on timeout."""
        handler = CommandAlert(["sleep", "100"])
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("sleep", 30)
            result = handler.send("Test message")

        assert result is False

    def test_send_returns_false_on_os_error(self) -> None:
        """Test CommandAlert returns False on OSError."""
        handler = CommandAlert(["/nonexistent/command"])
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError()
            result = handler.send("Test message")

        assert result is False


class TestJsonAlert:
    """Test JsonAlert handler."""

    def test_send_outputs_json(self, capsys: pytest.CaptureFixture) -> None:
        """Test JsonAlert outputs JSON."""
        handler = JsonAlert()
        handler.send("Test message")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_send_with_alert_data(self, capsys: pytest.CaptureFixture) -> None:
        """Test JsonAlert includes alert data."""
        alert = Alert(
            path="/test/path",
            percent_free=5.5,
            threshold_percent=10.0,
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
        )
        handler = JsonAlert(alert)
        handler.send("Test message")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["path"] == "/test/path"
        assert data["percent_free"] == 5.5
        assert data["message"] == "Test message"

    def test_send_returns_true_on_success(self, capsys: pytest.CaptureFixture) -> None:
        """Test JsonAlert returns True on success."""
        handler = JsonAlert()
        assert handler.send("Test message") is True

    def test_send_returns_false_on_error(self) -> None:
        """Test JsonAlert returns False on error."""
        handler = JsonAlert()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.write.side_effect = OSError()
            result = handler.send("Test message")

        assert result is False


class TestCreateHandler:
    """Test create_handler factory function."""

    def test_create_log_handler(self) -> None:
        """Test creating log handler."""
        handler = create_handler("log")
        assert isinstance(handler, LogAlert)

    def test_create_file_handler(self, tmp_path: Path) -> None:
        """Test creating file handler."""
        log_file = tmp_path / "alerts.log"
        handler = create_handler("file", path=log_file)
        assert isinstance(handler, FileAlert)

    def test_create_file_handler_default_path(self) -> None:
        """Test creating file handler with default path."""
        handler = create_handler("file")
        assert isinstance(handler, FileAlert)

    def test_create_command_handler(self) -> None:
        """Test creating command handler."""
        handler = create_handler("command", command=["echo"])
        assert isinstance(handler, CommandAlert)

    def test_create_command_handler_default(self) -> None:
        """Test creating command handler with default command."""
        handler = create_handler("command")
        assert isinstance(handler, CommandAlert)

    def test_create_json_handler(self) -> None:
        """Test creating json handler."""
        handler = create_handler("json")
        assert isinstance(handler, JsonAlert)

    def test_create_json_handler_with_alert(self) -> None:
        """Test creating json handler with alert."""
        alert = Alert(
            path="/test",
            percent_free=5.0,
            threshold_percent=10.0,
            timestamp=datetime.now(),
        )
        handler = create_handler("json", alert=alert)
        assert isinstance(handler, JsonAlert)

    def test_create_unknown_handler(self) -> None:
        """Test creating unknown handler raises error."""
        with pytest.raises(ValueError, match="Unknown handler type"):
            create_handler("unknown")
