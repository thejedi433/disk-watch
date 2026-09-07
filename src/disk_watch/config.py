"""Configuration management for disk-watch."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover (Python < 3.11 fallback)
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "disk-watch" / "config.toml"
DEFAULT_STATE_PATH = Path.home() / ".local" / "share" / "disk-watch" / "state.json"


@dataclass
class MonitorConfig:
    """Configuration for a single monitored path."""

    path: str
    threshold_percent: float = 10.0
    enabled: bool = True


@dataclass
class AlertConfig:
    """Configuration for alert handlers."""

    type: str = "log"  # "log", "file", "command", "json"
    file_path: str | None = None
    command: list[str] | None = None


@dataclass
class Config:
    """Main configuration for disk-watch."""

    monitors: list[MonitorConfig] = field(default_factory=lambda: [MonitorConfig(path="/")])
    alerts: list[AlertConfig] = field(default_factory=lambda: [AlertConfig()])
    check_interval_seconds: int = 300  # 5 minutes
    state_file: str = str(DEFAULT_STATE_PATH)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        """Load configuration from TOML file.

        Args:
            path: Path to config file (default: ~/.config/disk-watch/config.toml)

        Returns:
            Config instance
        """
        config_path = Path(path) if path else DEFAULT_CONFIG_PATH

        if not config_path.exists():
            return cls()

        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return cls()

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create Config from dictionary.

        Args:
            data: Config dictionary

        Returns:
            Config instance
        """
        monitors = []
        for m in data.get("monitors", []):
            if isinstance(m, dict):
                monitors.append(
                    MonitorConfig(
                        path=m.get("path", "/"),
                        threshold_percent=m.get("threshold_percent", 10.0),
                        enabled=m.get("enabled", True),
                    )
                )
            elif isinstance(m, str):
                monitors.append(MonitorConfig(path=m))

        alerts = []
        for a in data.get("alerts", []):
            if isinstance(a, dict):
                alerts.append(
                    AlertConfig(
                        type=a.get("type", "log"),
                        file_path=a.get("file_path"),
                        command=a.get("command"),
                    )
                )

        return cls(
            monitors=monitors or [MonitorConfig(path="/")],
            alerts=alerts or [AlertConfig()],
            check_interval_seconds=data.get("check_interval_seconds", 300),
            state_file=data.get("state_file", str(DEFAULT_STATE_PATH)),
        )

    def save(self, path: str | Path | None = None) -> bool:
        """Save configuration to TOML file.

        Args:
            path: Path to config file (default: ~/.config/disk-watch/config.toml)

        Returns:
            True if saved successfully
        """
        config_path = Path(path) if path else DEFAULT_CONFIG_PATH

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            lines = [
                "# disk-watch configuration",
                "",
                f"check_interval_seconds = {self.check_interval_seconds}",
                f'state_file = "{self.state_file}"',
                "",
                "[[monitors]]",
            ]

            for m in self.monitors:
                lines.append(f'path = "{m.path}"')
                lines.append(f"threshold_percent = {m.threshold_percent}")
                lines.append(f"enabled = {'true' if m.enabled else 'false'}")
                lines.append("")
                lines.append("[[monitors]]")

            # Always have a trailing [[monitors]] marker from either
            # the initial list setup or the last loop iteration.
            lines.pop()

            lines.append("")
            lines.append("[[alerts]]")

            for a in self.alerts:
                lines.append(f'type = "{a.type}"')
                if a.file_path:
                    lines.append(f'file_path = "{a.file_path}"')
                if a.command:
                    lines.append(f"command = {json.dumps(a.command)}")
                lines.append("")
                lines.append("[[alerts]]")

            lines.pop()

            with open(config_path, "w") as f:
                f.write("\n".join(lines))

            return True
        except OSError:
            return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dict representation
        """
        return {
            "monitors": [asdict(m) for m in self.monitors],
            "alerts": [asdict(a) for a in self.alerts],
            "check_interval_seconds": self.check_interval_seconds,
            "state_file": self.state_file,
        }


@dataclass
class MonitorState:
    """State for tracking alert history (avoid duplicate alerts)."""

    last_alert_times: dict[str, float] = field(default_factory=dict)
    last_check_time: float | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> "MonitorState":
        """Load state from JSON file.

        Args:
            path: Path to state file

        Returns:
            MonitorState instance
        """
        state_path = Path(path) if path else DEFAULT_STATE_PATH

        if not state_path.exists():
            return cls()

        try:
            with open(state_path) as f:
                data = json.load(f)
            return cls(
                last_alert_times=data.get("last_alert_times", {}),
                last_check_time=data.get("last_check_time"),
            )
        except (OSError, json.JSONDecodeError):
            return cls()

    def save(self, path: str | Path | None = None) -> bool:
        """Save state to JSON file.

        Args:
            path: Path to state file

        Returns:
            True if saved successfully
        """
        state_path = Path(path) if path else DEFAULT_STATE_PATH

        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "last_alert_times": self.last_alert_times,
                "last_check_time": self.last_check_time,
            }
            with open(state_path, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except OSError:
            return False

    def should_alert(self, path: str, cooldown_seconds: int = 3600) -> bool:
        """Check if we should send an alert for this path.

        Args:
            path: Path to check
            cooldown_seconds: Minimum time between alerts for same path

        Returns:
            True if enough time has passed since last alert
        """
        import time

        last_time = self.last_alert_times.get(path, 0)
        return (time.time() - last_time) >= cooldown_seconds

    def record_alert(self, path: str) -> None:
        """Record that an alert was sent for this path.

        Args:
            path: Path that was alerted
        """
        import time

        self.last_alert_times[path] = time.time()
