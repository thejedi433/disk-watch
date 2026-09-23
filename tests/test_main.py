"""Tests for __main__ module."""

import subprocess
import sys


def test_python_m_invocation():
    """Test that python -m disk_watch works."""
    result = subprocess.run(
        [sys.executable, "-m", "disk_watch", "--version"],
        capture_output=True,
        text=True,
        cwd="src",
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


def test_python_m_help():
    """Test that python -m disk_watch --help works."""
    result = subprocess.run(
        [sys.executable, "-m", "disk_watch", "--help"],
        capture_output=True,
        text=True,
        cwd="src",
    )
    assert result.returncode == 0
    assert "disk-watch" in result.stdout.lower() or "usage" in result.stdout.lower()
