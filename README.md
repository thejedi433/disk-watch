# disk-watch

Monitor disk usage and alert when free space drops below threshold.

## Installation

```bash
pip install disk-watch
```

## Usage

### Check disk usage for a path

```bash
disk-watch check /
disk-watch check /home -t 20  # Alert if free < 20%
disk-watch check / --json     # JSON output
```

### Monitor multiple paths continuously

```bash
disk-watch monitor                    # Uses ~/.config/disk-watch/config.toml
disk-watch monitor -c config.toml     # Custom config
disk-watch monitor --once             # Run once and exit (for cron)
```

### Show status of all mounts

```bash
disk-watch status
disk-watch status --json
```

### Initialize config file

```bash
disk-watch init
disk-watch init --force  # Overwrite existing
```

## Configuration

Configuration is stored in `~/.config/disk-watch/config.toml`:

```toml
check_interval_seconds = 300
state_file = "~/.local/share/disk-watch/state.json"

[[monitors]]
path = "/"
threshold_percent = 10.0
enabled = true

[[monitors]]
path = "/home"
threshold_percent = 20.0
enabled = true

[[alerts]]
type = "log"  # Options: log, file, command, json

[[alerts]]
type = "file"
file_path = "/tmp/disk-alerts.log"

[[alerts]]
type = "command"
command = ["notify-send", "Disk Alert"]
```

## Alert Types

- **log**: Logs to stderr
- **file**: Appends to a log file
- **command**: Runs a command with the alert message
- **json**: Outputs JSON to stdout

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=disk_watch --cov-report=term-missing
```

## License

MIT
