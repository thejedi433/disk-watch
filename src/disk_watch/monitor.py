"""Disk usage monitoring and threshold checking."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DiskUsage:
    """Represents disk usage statistics for a path."""

    path: str
    total: int  # bytes
    used: int  # bytes
    free: int  # bytes
    percent_used: float  # 0-100
    percent_free: float  # 0-100

    @classmethod
    def from_path(cls, path: str | Path) -> "DiskUsage":
        """Create DiskUsage from a filesystem path.

        Args:
            path: Path to check (file or directory)

        Returns:
            DiskUsage with current stats

        Raises:
            FileNotFoundError: If path doesn't exist
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        stat = os.statvfs(str(p))
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free

        if total == 0:
            percent_used = 0.0
            percent_free = 0.0
        else:
            percent_used = (used / total) * 100
            percent_free = (free / total) * 100

        return cls(
            path=str(p.resolve()),
            total=total,
            used=used,
            free=free,
            percent_used=percent_used,
            percent_free=percent_free,
        )

    def is_below_threshold(self, threshold_percent: float) -> bool:
        """Check if free space is below threshold.

        Args:
            threshold_percent: Minimum free percent (0-100)

        Returns:
            True if free space is below threshold
        """
        return self.percent_free < threshold_percent

    def format_bytes(self, value: int) -> str:
        """Format bytes to human-readable string.

        Args:
            value: Bytes to format

        Returns:
            Human-readable string (e.g., "1.5 GB")
        """
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(value)
        for unit in units:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def summary(self) -> str:
        """Get human-readable summary.

        Returns:
            Multi-line summary string
        """
        lines = [
            f"Path: {self.path}",
            f"Total: {self.format_bytes(self.total)}",
            f"Used:  {self.format_bytes(self.used)} ({self.percent_used:.1f}%)",
            f"Free:  {self.format_bytes(self.free)} ({self.percent_free:.1f}%)",
        ]
        return "\n".join(lines)


def check_disk(
    path: str | Path,
    threshold_percent: float = 10.0,
) -> tuple[DiskUsage, bool]:
    """Check disk usage and whether it's below threshold.

    Args:
        path: Path to check
        threshold_percent: Minimum free percent (0-100)

    Returns:
        Tuple of (DiskUsage, is_alert) where is_alert is True if free < threshold
    """
    usage = DiskUsage.from_path(path)
    is_alert = usage.is_below_threshold(threshold_percent)
    return usage, is_alert


def get_mount_points() -> list[str]:
    """Get list of mount points from /proc/mounts.

    Returns:
        List of mount point paths
    """
    mounts = []
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mounts.append(parts[1])
    except (FileNotFoundError, PermissionError):
        # Fallback to root
        mounts = ["/"]
    return mounts


def check_all_mounts(threshold_percent: float = 10.0) -> list[tuple[DiskUsage, bool]]:
    """Check all mount points for disk usage.

    Args:
        threshold_percent: Minimum free percent (0-100)

    Returns:
        List of (DiskUsage, is_alert) tuples, deduplicated by device
    """
    results = []
    seen_paths = set()

    for mount in get_mount_points():
        # Skip virtual filesystems
        if mount.startswith(("/proc", "/sys", "/dev", "/run")):
            continue

        try:
            # Resolve to real path to deduplicate bind mounts
            real_path = str(Path(mount).resolve())
            if real_path in seen_paths:
                continue
            seen_paths.add(real_path)

            usage, is_alert = check_disk(mount, threshold_percent)
            results.append((usage, is_alert))
        except (FileNotFoundError, PermissionError, OSError):
            continue

    return results
