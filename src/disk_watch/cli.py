"""Command-line interface for disk-watch."""

import argparse
import sys
import time
from datetime import datetime
from typing import Sequence

from disk_watch import __version__
from disk_watch.alerts import Alert, create_handler
from disk_watch.config import Config, MonitorState
from disk_watch.monitor import check_all_mounts, check_disk


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser.

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="disk-watch",
        description="Monitor disk usage and alert when free space is low",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # check command
    check_parser = subparsers.add_parser("check", help="Check disk usage for a path")
    check_parser.add_argument(
        "path",
        nargs="?",
        default="/",
        help="Path to check (default: /)",
    )
    check_parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=10.0,
        help="Alert threshold percent (default: 10)",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # monitor command
    monitor_parser = subparsers.add_parser(
        "monitor", help="Monitor disk usage and alert on low space"
    )
    monitor_parser.add_argument(
        "-c",
        "--config",
        help="Path to config file",
    )
    monitor_parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (for cron)",
    )
    monitor_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # status command
    status_parser = subparsers.add_parser("status", help="Show status of all monitored paths")
    status_parser.add_argument(
        "-c",
        "--config",
        help="Path to config file",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # init command
    init_parser = subparsers.add_parser("init", help="Create default config file")
    init_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing config",
    )

    return parser


def cmd_check(args: argparse.Namespace) -> int:
    """Handle check command.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    usage, is_alert = check_disk(args.path, args.threshold)

    if args.json:
        import json

        data = {
            "path": usage.path,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent_used": usage.percent_used,
            "percent_free": usage.percent_free,
            "threshold": args.threshold,
            "alert": is_alert,
        }
        print(json.dumps(data, indent=2))
    else:
        print(usage.summary())
        if is_alert:
            print(f"\n⚠️  ALERT: Free space below {args.threshold}%!")
            return 1

    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    """Handle monitor command.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    config = Config.load(args.config)
    state = MonitorState.load(config.state_file)

    # Create alert handlers
    handlers = []
    for alert_config in config.alerts:
        kwargs = {}
        if alert_config.file_path:
            kwargs["path"] = alert_config.file_path
        if alert_config.command:
            kwargs["command"] = alert_config.command
        handlers.append(create_handler(alert_config.type, **kwargs))

    alerts_sent = 0

    for monitor in config.monitors:
        if not monitor.enabled:
            continue

        try:
            usage, is_alert = check_disk(monitor.path, monitor.threshold_percent)
        except FileNotFoundError:
            continue

        if is_alert and state.should_alert(monitor.path):
            alert = Alert(
                path=usage.path,
                percent_free=usage.percent_free,
                threshold_percent=monitor.threshold_percent,
                timestamp=datetime.now(),
            )

            if args.json:
                import json

                data = alert.to_dict()
                data["message"] = alert.message()
                print(json.dumps(data))
            else:
                for handler in handlers:
                    handler.send(alert.message())

            state.record_alert(monitor.path)
            alerts_sent += 1

    state.last_check_time = time.time()
    state.save(config.state_file)

    if args.once:
        return 1 if alerts_sent > 0 else 0

    # Continuous monitoring
    try:
        while True:
            time.sleep(config.check_interval_seconds)
            state = MonitorState.load(config.state_file)

            for monitor in config.monitors:
                if not monitor.enabled:
                    continue

                try:
                    usage, is_alert = check_disk(monitor.path, monitor.threshold_percent)
                except FileNotFoundError:
                    continue

                if is_alert and state.should_alert(monitor.path):
                    alert = Alert(
                        path=usage.path,
                        percent_free=usage.percent_free,
                        threshold_percent=monitor.threshold_percent,
                        timestamp=datetime.now(),
                    )

                    if args.json:
                        import json

                        data = alert.to_dict()
                        data["message"] = alert.message()
                        print(json.dumps(data))
                    else:
                        for handler in handlers:
                            handler.send(alert.message())

                    state.record_alert(monitor.path)
                    alerts_sent += 1

            state.last_check_time = time.time()
            state.save(config.state_file)

    except KeyboardInterrupt:
        pass

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Handle status command.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    config = Config.load(args.config)
    results = check_all_mounts()

    if args.json:
        import json

        data = []
        for usage, is_alert in results:
            data.append(
                {
                    "path": usage.path,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent_used": usage.percent_used,
                    "percent_free": usage.percent_free,
                    "alert": is_alert,
                }
            )
        print(json.dumps(data, indent=2))
    else:
        for usage, is_alert in results:
            status = "⚠️ " if is_alert else "✓"
            print(f"{status} {usage.path}")
            print(f"  Free: {usage.format_bytes(usage.free)} ({usage.percent_free:.1f}%)")
            print()

    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Handle init command.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    from disk_watch.config import DEFAULT_CONFIG_PATH

    config_path = DEFAULT_CONFIG_PATH

    if config_path.exists() and not args.force:
        print(f"Config already exists: {config_path}")
        print("Use --force to overwrite")
        return 1

    config = Config()
    if config.save(config_path):
        print(f"Created config: {config_path}")
        return 0
    else:
        print(f"Failed to create config: {config_path}")
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments

    Returns:
        Exit code
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "check": cmd_check,
        "monitor": cmd_monitor,
        "status": cmd_status,
        "init": cmd_init,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
