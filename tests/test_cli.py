"""Tests for disk_watch.cli module."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from disk_watch.cli import (
    cmd_check,
    cmd_init,
    cmd_monitor,
    cmd_status,
    create_parser,
    main,
)
from disk_watch.config import AlertConfig, Config, MonitorConfig
from disk_watch.monitor import DiskUsage


class TestCreateParser:
    """Test argument parser creation."""

    def test_parser_has_version(self) -> None:
        """Test parser has version option."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])

    def test_parser_check_command(self) -> None:
        """Test parser handles check command."""
        parser = create_parser()
        args = parser.parse_args(["check", "/home"])
        assert args.command == "check"
        assert args.path == "/home"

    def test_parser_check_default_path(self) -> None:
        """Test parser check uses default path."""
        parser = create_parser()
        args = parser.parse_args(["check"])
        assert args.path == "/"

    def test_parser_check_threshold(self) -> None:
        """Test parser handles threshold option."""
        parser = create_parser()
        args = parser.parse_args(["check", "-t", "20"])
        assert args.threshold == 20.0

    def test_parser_check_json(self) -> None:
        """Test parser handles json option."""
        parser = create_parser()
        args = parser.parse_args(["check", "--json"])
        assert args.json is True

    def test_parser_monitor_command(self) -> None:
        """Test parser handles monitor command."""
        parser = create_parser()
        args = parser.parse_args(["monitor"])
        assert args.command == "monitor"

    def test_parser_monitor_config(self) -> None:
        """Test parser handles monitor config option."""
        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", "/path/to/config"])
        assert args.config == "/path/to/config"

    def test_parser_monitor_once(self) -> None:
        """Test parser handles monitor once option."""
        parser = create_parser()
        args = parser.parse_args(["monitor", "--once"])
        assert args.once is True

    def test_parser_status_command(self) -> None:
        """Test parser handles status command."""
        parser = create_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_parser_status_json(self) -> None:
        """Test parser handles status json option."""
        parser = create_parser()
        args = parser.parse_args(["status", "--json"])
        assert args.json is True

    def test_parser_init_command(self) -> None:
        """Test parser handles init command."""
        parser = create_parser()
        args = parser.parse_args(["init"])
        assert args.command == "init"

    def test_parser_init_force(self) -> None:
        """Test parser handles init force option."""
        parser = create_parser()
        args = parser.parse_args(["init", "--force"])
        assert args.force is True


class TestCmdCheck:
    """Test check command."""

    def test_check_no_alert(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test check with no alert."""
        parser = create_parser()
        args = parser.parse_args(["check", str(tmp_path), "-t", "0"])

        result = cmd_check(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Path:" in captured.out
        assert "Total:" in captured.out

    def test_check_with_alert(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test check with alert."""
        parser = create_parser()
        args = parser.parse_args(["check", str(tmp_path), "-t", "100"])

        result = cmd_check(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "ALERT" in captured.out

    def test_check_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test check with JSON output."""
        parser = create_parser()
        args = parser.parse_args(["check", str(tmp_path), "--json"])

        result = cmd_check(args)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "path" in data
        assert "total" in data
        assert "free" in data
        assert "alert" in data


class TestCmdMonitor:
    """Test monitor command."""

    def test_monitor_once_no_alert(self, tmp_path: Path) -> None:
        """Test monitor once with no alert."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=0.0)],
            alerts=[AlertConfig(type="log")],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once"])

        result = cmd_monitor(args)
        assert result == 0

    def test_monitor_once_with_alert(self, tmp_path: Path) -> None:
        """Test monitor once with alert."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0)],
            alerts=[AlertConfig(type="log")],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once"])

        result = cmd_monitor(args)
        assert result == 1

    def test_monitor_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test monitor with JSON output."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0)],
            alerts=[AlertConfig(type="log")],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once", "--json"])

        result = cmd_monitor(args)

        assert result == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "path" in data
        assert "message" in data

    def test_monitor_skips_disabled(self, tmp_path: Path) -> None:
        """Test monitor skips disabled monitors."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0, enabled=False)],
            alerts=[AlertConfig(type="log")],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once"])

        result = cmd_monitor(args)
        assert result == 0

    def test_monitor_handles_missing_path(self, tmp_path: Path) -> None:
        """Test monitor handles missing path."""
        config = Config(
            monitors=[MonitorConfig(path="/nonexistent/path", threshold_percent=10.0)],
            alerts=[AlertConfig(type="log")],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once"])

        result = cmd_monitor(args)
        assert result == 0

    def test_monitor_respects_cooldown(self, tmp_path: Path) -> None:
        """Test monitor respects alert cooldown."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0)],
            alerts=[AlertConfig(type="log")],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        # Create state with recent alert
        from disk_watch.config import MonitorState
        import time
        state = MonitorState(last_alert_times={str(tmp_path.resolve()): time.time()})
        state.save(config.state_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once"])

        result = cmd_monitor(args)
        # Should return 0 because cooldown prevents alert
        assert result == 0

    def test_monitor_with_file_alert(self, tmp_path: Path) -> None:
        """Test monitor with file alert handler."""
        alert_file = tmp_path / "alerts.log"
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0)],
            alerts=[AlertConfig(type="file", file_path=str(alert_file))],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once"])

        result = cmd_monitor(args)
        assert result == 1
        assert alert_file.exists()

    def test_monitor_with_command_alert(self, tmp_path: Path) -> None:
        """Test monitor with command alert handler."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0)],
            alerts=[AlertConfig(type="command", command=["true"])],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once"])

        result = cmd_monitor(args)
        assert result == 1

    def test_monitor_continuous_with_keyboard_interrupt(self, tmp_path: Path) -> None:
        """Test monitor continuous mode exits on KeyboardInterrupt."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=0.0)],
            alerts=[AlertConfig(type="log")],
            check_interval_seconds=1,
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file)])

        # Mock time.sleep to raise KeyboardInterrupt
        with patch("disk_watch.cli.time.sleep", side_effect=KeyboardInterrupt):
            result = cmd_monitor(args)

        assert result == 0

    def test_monitor_continuous_with_alert(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test monitor continuous mode sends alerts."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0)],
            alerts=[AlertConfig(type="log")],
            check_interval_seconds=1,
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file)])

        call_count = [0]

        def mock_sleep(seconds: float) -> None:
            call_count[0] += 1
            if call_count[0] >= 2:
                raise KeyboardInterrupt()

        # Mock time.time to advance past cooldown
        import time
        original_time = time.time
        time_offset = [0]
        def mock_time() -> float:
            return original_time() + time_offset[0]

        with patch("disk_watch.cli.time.sleep", side_effect=mock_sleep):
            with patch("disk_watch.cli.time.time", side_effect=mock_time):
                # Advance time by 2 hours to pass cooldown
                def mock_sleep_with_time(seconds: float) -> None:
                    call_count[0] += 1
                    time_offset[0] = 7200  # 2 hours
                    if call_count[0] >= 2:
                        raise KeyboardInterrupt()
                
                # Reset and re-patch
                call_count[0] = 0
                with patch("disk_watch.cli.time.sleep", side_effect=mock_sleep_with_time):
                    result = cmd_monitor(args)

        assert result == 0
        captured = capsys.readouterr()
        # Should have sent an alert (either JSON or text)
        assert "DISK ALERT" in captured.err or "alert" in captured.out.lower()

    def test_monitor_continuous_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test monitor continuous mode with JSON output."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0)],
            alerts=[AlertConfig(type="log")],
            check_interval_seconds=1,
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--json"])

        call_count = [0]

        def mock_sleep(seconds: float) -> None:
            call_count[0] += 1
            if call_count[0] >= 2:
                raise KeyboardInterrupt()

        # Mock time.time to advance past cooldown
        import time
        original_time = time.time
        time_offset = [0]
        def mock_time() -> float:
            return original_time() + time_offset[0]

        with patch("disk_watch.cli.time.sleep", side_effect=mock_sleep):
            with patch("disk_watch.cli.time.time", side_effect=mock_time):
                # Advance time by 2 hours to pass cooldown
                def mock_sleep_with_time(seconds: float) -> None:
                    call_count[0] += 1
                    time_offset[0] = 7200  # 2 hours
                    if call_count[0] >= 2:
                        raise KeyboardInterrupt()
                
                # Reset and re-patch
                call_count[0] = 0
                with patch("disk_watch.cli.time.sleep", side_effect=mock_sleep_with_time):
                    result = cmd_monitor(args)

        assert result == 0
        captured = capsys.readouterr()
        # Should have output JSON with alert data
        assert "path" in captured.out

    def test_monitor_continuous_missing_path(self, tmp_path: Path) -> None:
        """Test monitor continuous mode handles missing paths."""
        config = Config(
            monitors=[MonitorConfig(path="/nonexistent/path", threshold_percent=10.0)],
            alerts=[AlertConfig(type="log")],
            check_interval_seconds=1,
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file)])

        call_count = [0]

        def mock_sleep(seconds: float) -> None:
            call_count[0] += 1
            if call_count[0] >= 2:
                raise KeyboardInterrupt()

        with patch("disk_watch.cli.time.sleep", side_effect=mock_sleep):
            result = cmd_monitor(args)

        assert result == 0

    def test_monitor_continuous_disabled_skipped(self, tmp_path: Path) -> None:
        """Test monitor continuous mode skips disabled monitors."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0, enabled=False)],
            alerts=[AlertConfig(type="log")],
            check_interval_seconds=1,
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file)])

        call_count = [0]

        def mock_sleep(seconds: float) -> None:
            call_count[0] += 1
            if call_count[0] >= 2:
                raise KeyboardInterrupt()

        with patch("disk_watch.cli.time.sleep", side_effect=mock_sleep):
            result = cmd_monitor(args)

        assert result == 0

    def test_monitor_with_file_path_alert(self, tmp_path: Path) -> None:
        """Test monitor with file_path alert config."""
        log_file = tmp_path / "alerts.log"
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0)],
            alerts=[AlertConfig(type="file", file_path=str(log_file))],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once"])

        result = cmd_monitor(args)
        assert result == 1
        assert log_file.exists()

    def test_monitor_with_command_alert(self, tmp_path: Path) -> None:
        """Test monitor with command alert config."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=100.0)],
            alerts=[AlertConfig(type="command", command=["echo"])],
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file), "--once"])

        result = cmd_monitor(args)
        assert result == 1

    def test_monitor_continuous_mode(self, tmp_path: Path) -> None:
        """Test monitor continuous mode with KeyboardInterrupt."""
        config = Config(
            monitors=[MonitorConfig(path=str(tmp_path), threshold_percent=0.0)],
            alerts=[AlertConfig(type="log")],
            check_interval_seconds=1,
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)

        parser = create_parser()
        args = parser.parse_args(["monitor", "-c", str(config_file)])

        # Mock time.sleep to raise KeyboardInterrupt after first iteration
        with patch("time.sleep") as mock_sleep:
            mock_sleep.side_effect = [None, KeyboardInterrupt()]
            result = cmd_monitor(args)

        assert result == 0


class TestCmdStatus:
    """Test status command."""

    def test_status_text_output(self, capsys: pytest.CaptureFixture) -> None:
        """Test status with text output."""
        parser = create_parser()
        args = parser.parse_args(["status"])

        result = cmd_status(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "/" in captured.out

    def test_status_json_output(self, capsys: pytest.CaptureFixture) -> None:
        """Test status with JSON output."""
        parser = create_parser()
        args = parser.parse_args(["status", "--json"])

        result = cmd_status(args)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "path" in data[0]

    def test_status_with_alert(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test status shows alert indicator."""
        # Mock check_all_mounts to return an alert
        from disk_watch.monitor import DiskUsage

        usage = DiskUsage(
            path=str(tmp_path),
            total=1000,
            used=950,
            free=50,
            percent_used=95.0,
            percent_free=5.0,
        )

        with patch("disk_watch.cli.check_all_mounts") as mock_check:
            mock_check.return_value = [(usage, True)]

            parser = create_parser()
            args = parser.parse_args(["status"])

            result = cmd_status(args)

            assert result == 0
            captured = capsys.readouterr()
            assert "⚠️" in captured.out


class TestCmdInit:
    """Test init command."""

    def test_init_creates_config(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test init creates config file."""
        config_file = tmp_path / "config.toml"
        with patch("disk_watch.config.DEFAULT_CONFIG_PATH", config_file):
            parser = create_parser()
            args = parser.parse_args(["init"])

            result = cmd_init(args)

            assert result == 0
            captured = capsys.readouterr()
            assert "Created config" in captured.out

    def test_init_exists_no_force(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test init refuses to overwrite without force."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("existing")

        with patch("disk_watch.config.DEFAULT_CONFIG_PATH", config_file):
            parser = create_parser()
            args = parser.parse_args(["init"])

            result = cmd_init(args)

            assert result == 1
            captured = capsys.readouterr()
            assert "already exists" in captured.out

    def test_init_exists_with_force(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test init overwrites with force."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("existing")

        with patch("disk_watch.config.DEFAULT_CONFIG_PATH", config_file):
            parser = create_parser()
            args = parser.parse_args(["init", "--force"])

            result = cmd_init(args)

            assert result == 0
            captured = capsys.readouterr()
            assert "Created config" in captured.out

    def test_init_save_fails(self, capsys: pytest.CaptureFixture) -> None:
        """Test init handles save failure."""
        with patch("disk_watch.config.DEFAULT_CONFIG_PATH", Path("/proc/invalid/config.toml")):
            parser = create_parser()
            args = parser.parse_args(["init"])

            result = cmd_init(args)

            assert result == 1
            captured = capsys.readouterr()
            assert "Failed to create config" in captured.out


class TestMain:
    """Test main entry point."""

    def test_main_no_command(self, capsys: pytest.CaptureFixture) -> None:
        """Test main with no command shows help."""
        result = main([])
        assert result == 0

    def test_main_check_command(self, tmp_path: Path) -> None:
        """Test main with check command."""
        result = main(["check", str(tmp_path)])
        assert result == 0

    def test_main_status_command(self) -> None:
        """Test main with status command."""
        result = main(["status"])
        assert result == 0

    def test_main_version(self, capsys: pytest.CaptureFixture) -> None:
        """Test main with version."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
