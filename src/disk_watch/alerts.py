"""Alert notification handlers."""

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


class AlertHandler(Protocol):
    """Protocol for alert handlers."""

    def send(self, message: str) -> bool:  # pragma: no cover
        """Send an alert message.

        Args:
            message: Alert message to send

        Returns:
            True if sent successfully
        """
        ...


@dataclass
class Alert:
    """Represents a disk usage alert."""

    path: str
    percent_free: float
    threshold_percent: float
    timestamp: datetime

    def message(self) -> str:
        """Get human-readable alert message.

        Returns:
            Alert message string
        """
        return (
            f"DISK ALERT: {self.path} has only {self.percent_free:.1f}% free "
            f"(threshold: {self.threshold_percent:.1f}%)"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization.

        Returns:
            Dict representation
        """
        return {
            "path": self.path,
            "percent_free": self.percent_free,
            "threshold_percent": self.threshold_percent,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Alert":
        """Create from dictionary.

        Args:
            data: Dict with alert fields

        Returns:
            Alert instance
        """
        return cls(
            path=data["path"],
            percent_free=data["percent_free"],
            threshold_percent=data["threshold_percent"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


class LogAlert:
    """Alert handler that logs to stderr."""

    def send(self, message: str) -> bool:
        """Log alert to stderr.

        Args:
            message: Alert message

        Returns:
            Always True
        """
        print(f"[disk-watch] {message}", file=sys.stderr)
        return True


class FileAlert:
    """Alert handler that appends to a log file."""

    def __init__(self, path: str | Path):
        """Initialize with log file path.

        Args:
            path: Path to log file
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, message: str) -> bool:
        """Append alert to log file.

        Args:
            message: Alert message

        Returns:
            True if written successfully
        """
        try:
            timestamp = datetime.now().isoformat()
            with open(self.path, "a") as f:
                f.write(f"[{timestamp}] {message}\n")
            return True
        except OSError:
            return False


class CommandAlert:
    """Alert handler that runs a command."""

    def __init__(self, command: list[str]):
        """Initialize with command to run.

        Args:
            command: Command and arguments to execute
        """
        self.command = command

    def send(self, message: str) -> bool:
        """Run command with message as argument.

        Args:
            message: Alert message passed as last argument

        Returns:
            True if command succeeded
        """
        try:
            result = subprocess.run(
                [*self.command, message],
                capture_output=True,
                timeout=30,
                check=True,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False


class JsonAlert:
    """Alert handler that outputs JSON to stdout."""

    def __init__(self, alert: Alert | None = None):
        """Initialize with optional alert data.

        Args:
            alert: Alert data to serialize
        """
        self.alert = alert

    def send(self, message: str) -> bool:
        """Output JSON to stdout.

        Args:
            message: Alert message

        Returns:
            True if written successfully
        """
        try:
            if self.alert:
                data = self.alert.to_dict()
                data["message"] = message
            else:
                data = {"message": message, "timestamp": datetime.now().isoformat()}
            print(json.dumps(data))
            return True
        except OSError:
            return False


def create_handler(handler_type: str, **kwargs) -> AlertHandler:
    """Factory function to create alert handlers.

    Args:
        handler_type: Type of handler ("log", "file", "command", "json")
        **kwargs: Handler-specific arguments

    Returns:
        AlertHandler instance

    Raises:
        ValueError: If handler_type is unknown
    """
    handlers = {
        "log": LogAlert,
        "file": FileAlert,
        "command": CommandAlert,
        "json": JsonAlert,
    }

    if handler_type not in handlers:
        raise ValueError(f"Unknown handler type: {handler_type}")

    handler_cls = handlers[handler_type]

    if handler_type == "file":
        return handler_cls(kwargs.get("path", "~/.local/share/disk-watch/alerts.log"))
    elif handler_type == "command":
        return handler_cls(kwargs.get("command", ["echo"]))
    elif handler_type == "json":
        return handler_cls(kwargs.get("alert"))
    else:
        return handler_cls()
