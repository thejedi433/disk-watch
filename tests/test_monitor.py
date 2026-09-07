"""Tests for disk_watch.monitor module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from disk_watch.monitor import DiskUsage, check_all_mounts, check_disk, get_mount_points


class TestDiskUsage:
    """Test DiskUsage class."""

    def test_from_path_file(self, tmp_path: Path) -> None:
        """Test creating DiskUsage from a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        usage = DiskUsage.from_path(test_file)

        assert usage.path == str(test_file.resolve())
        assert usage.total > 0
        assert usage.used > 0
        assert usage.free > 0
        assert 0 <= usage.percent_used <= 100
        assert 0 <= usage.percent_free <= 100

    def test_from_path_directory(self, tmp_path: Path) -> None:
        """Test creating DiskUsage from a directory."""
        usage = DiskUsage.from_path(tmp_path)

        assert usage.path == str(tmp_path.resolve())
        assert usage.total > 0
        assert usage.used >= 0
        assert usage.free >= 0

    def test_from_path_not_exists(self) -> None:
        """Test creating DiskUsage from non-existent path raises error."""
        with pytest.raises(FileNotFoundError, match="Path does not exist"):
            DiskUsage.from_path("/nonexistent/path/xyz123")

    def test_is_below_threshold_true(self, tmp_path: Path) -> None:
        """Test is_below_threshold returns True when free < threshold."""
        usage = DiskUsage.from_path(tmp_path)
        # Set a high threshold that should be above free space
        assert usage.is_below_threshold(100.0) is True

    def test_is_below_threshold_false(self, tmp_path: Path) -> None:
        """Test is_below_threshold returns False when free >= threshold."""
        usage = DiskUsage.from_path(tmp_path)
        # Set a low threshold that should be below free space
        assert usage.is_below_threshold(0.0) is False

    def test_format_bytes_bytes(self, tmp_path: Path) -> None:
        """Test format_bytes for bytes."""
        usage = DiskUsage.from_path(tmp_path)
        assert usage.format_bytes(500) == "500.0 B"

    def test_format_bytes_kilobytes(self, tmp_path: Path) -> None:
        """Test format_bytes for kilobytes."""
        usage = DiskUsage.from_path(tmp_path)
        assert usage.format_bytes(1536) == "1.5 KB"

    def test_format_bytes_megabytes(self, tmp_path: Path) -> None:
        """Test format_bytes for megabytes."""
        usage = DiskUsage.from_path(tmp_path)
        assert usage.format_bytes(1572864) == "1.5 MB"

    def test_format_bytes_gigabytes(self, tmp_path: Path) -> None:
        """Test format_bytes for gigabytes."""
        usage = DiskUsage.from_path(tmp_path)
        assert usage.format_bytes(1610612736) == "1.5 GB"

    def test_format_bytes_terabytes(self, tmp_path: Path) -> None:
        """Test format_bytes for terabytes."""
        usage = DiskUsage.from_path(tmp_path)
        assert usage.format_bytes(1649267441664) == "1.5 TB"

    def test_format_bytes_petabytes(self, tmp_path: Path) -> None:
        """Test format_bytes for petabytes."""
        usage = DiskUsage.from_path(tmp_path)
        assert usage.format_bytes(1688849860263936) == "1.5 PB"

    def test_summary(self, tmp_path: Path) -> None:
        """Test summary output format."""
        usage = DiskUsage.from_path(tmp_path)
        summary = usage.summary()

        assert "Path:" in summary
        assert "Total:" in summary
        assert "Used:" in summary
        assert "Free:" in summary

    def test_zero_total(self) -> None:
        """Test handling of zero total space."""
        usage = DiskUsage(
            path="/test",
            total=0,
            used=0,
            free=0,
            percent_used=0.0,
            percent_free=0.0,
        )
        assert usage.is_below_threshold(10.0) is True

    def test_from_path_zero_total(self, tmp_path: Path) -> None:
        """Test from_path when statvfs returns zero blocks."""
        # Mock os.statvfs to return zero blocks
        mock_stat = MagicMock()
        mock_stat.f_blocks = 0
        mock_stat.f_frsize = 4096
        mock_stat.f_bavail = 0

        with patch("os.statvfs", return_value=mock_stat):
            usage = DiskUsage.from_path(tmp_path)
            assert usage.total == 0
            assert usage.percent_used == 0.0
            assert usage.percent_free == 0.0


class TestCheckDisk:
    """Test check_disk function."""

    def test_check_disk_below_threshold(self, tmp_path: Path) -> None:
        """Test check_disk returns alert when below threshold."""
        usage, is_alert = check_disk(tmp_path, threshold_percent=100.0)

        assert usage.path == str(tmp_path.resolve())
        assert is_alert is True

    def test_check_disk_above_threshold(self, tmp_path: Path) -> None:
        """Test check_disk returns no alert when above threshold."""
        usage, is_alert = check_disk(tmp_path, threshold_percent=0.0)

        assert usage.path == str(tmp_path.resolve())
        assert is_alert is False

    def test_check_disk_default_threshold(self, tmp_path: Path) -> None:
        """Test check_disk uses default threshold."""
        usage, is_alert = check_disk(tmp_path)

        assert usage is not None
        # Default threshold is 10%


class TestGetMountPoints:
    """Test get_mount_points function."""

    def test_get_mount_points_returns_list(self) -> None:
        """Test get_mount_points returns a list."""
        mounts = get_mount_points()
        assert isinstance(mounts, list)
        assert len(mounts) > 0

    def test_get_mount_points_includes_root(self) -> None:
        """Test get_mount_points includes root."""
        mounts = get_mount_points()
        assert "/" in mounts

    def test_get_mount_points_parses_correctly(self, tmp_path: Path) -> None:
        """Test get_mount_points parses /proc/mounts format correctly."""
        # Create a fake /proc/mounts file
        fake_mounts = tmp_path / "mounts"
        fake_mounts.write_text(
            "/dev/sda1 / ext4 rw 0 0\n"
            "/dev/sda2 /home ext4 rw 0 0\n"
            "tmpfs /tmp tmpfs rw 0 0\n"
        )
        
        with patch("builtins.open", return_value=open(fake_mounts)):
            mounts = get_mount_points()
            assert "/" in mounts
            assert "/home" in mounts
            assert "/tmp" in mounts

    @patch("builtins.open")
    def test_get_mount_points_file_not_found(self, mock_open: MagicMock) -> None:
        """Test get_mount_points handles missing /proc/mounts."""
        mock_open.side_effect = FileNotFoundError()
        mounts = get_mount_points()
        assert mounts == ["/"]

    @patch("builtins.open")
    def test_get_mount_points_permission_error(self, mock_open: MagicMock) -> None:
        """Test get_mount_points handles permission error."""
        mock_open.side_effect = PermissionError()
        mounts = get_mount_points()
        assert mounts == ["/"]

    def test_get_mount_points_skips_short_lines(self, tmp_path: Path) -> None:
        """Test get_mount_points skips lines with fewer than 2 fields."""
        fake_mounts = tmp_path / "mounts"
        fake_mounts.write_text(
            "/dev/sda1 / ext4 rw 0 0\n"
            "shortline\n"
            "\n"
            "/dev/sda2 /home ext4 rw 0 0\n"
        )

        with patch("builtins.open", return_value=open(fake_mounts)):
            mounts = get_mount_points()
            assert "/" in mounts
            assert "/home" in mounts
            # Short lines skipped
            assert len(mounts) == 2


class TestCheckAllMounts:
    """Test check_all_mounts function."""

    def test_check_all_mounts_returns_list(self) -> None:
        """Test check_all_mounts returns a list."""
        results = check_all_mounts()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_check_all_mounts_returns_tuples(self) -> None:
        """Test check_all_mounts returns (DiskUsage, bool) tuples."""
        results = check_all_mounts()
        for usage, is_alert in results:
            assert isinstance(usage, DiskUsage)
            assert isinstance(is_alert, bool)

    def test_check_all_mounts_deduplicates(self) -> None:
        """Test check_all_mounts deduplicates by resolved path."""
        with patch("disk_watch.monitor.get_mount_points") as mock_mounts:
            mock_mounts.return_value = ["/", "/"]
            results = check_all_mounts()
            # Should only have one entry for root
            paths = [usage.path for usage, _ in results]
            assert paths.count(str(Path("/").resolve())) == 1

    def test_check_all_mounts_skips_virtual(self) -> None:
        """Test check_all_mounts skips virtual filesystems."""
        with patch("disk_watch.monitor.get_mount_points") as mock_mounts:
            mock_mounts.return_value = ["/proc", "/sys", "/dev", "/run", "/"]
            results = check_all_mounts()
            paths = [usage.path for usage, _ in results]
            # Should only have root, not virtual filesystems
            assert not any(p.startswith(("/proc", "/sys", "/dev", "/run")) for p in paths)

    def test_check_all_mounts_handles_errors(self) -> None:
        """Test check_all_mounts handles errors gracefully."""
        with patch("disk_watch.monitor.get_mount_points") as mock_mounts:
            mock_mounts.return_value = ["/nonexistent/path"]
            results = check_all_mounts()
            # Should return empty list on error
            assert results == []
