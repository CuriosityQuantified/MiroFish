"""
Task 5c — CLI smoke tests
Verify mirofish_cli.py subcommands are wired up and --help works without live API calls.
"""
import subprocess
import sys
import os

PYTHON = sys.executable
CLI = os.path.join(os.path.dirname(__file__), '..', 'mirofish_cli.py')


def run_cli(*args, **kwargs):
    return subprocess.run(
        [PYTHON, CLI] + list(args),
        capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': os.path.join(os.path.dirname(__file__), '..')}
    )


class TestCLIHelp:
    def test_top_level_help(self):
        r = run_cli('--help')
        assert r.returncode == 0
        assert 'run' in r.stdout or 'usage' in r.stdout.lower()

    def test_run_help(self):
        r = run_cli('run', '--help')
        assert r.returncode == 0
        assert '--config' in r.stdout

    def test_build_help(self):
        r = run_cli('build', '--help')
        assert r.returncode == 0

    def test_status_help(self):
        r = run_cli('status', '--help')
        assert r.returncode == 0


class TestCLIValidation:
    def test_run_missing_config(self):
        """run without --config should exit with error."""
        r = run_cli('run')
        assert r.returncode != 0

    def test_run_nonexistent_config(self):
        """run with a non-existent config file should exit with error."""
        r = run_cli('run', '--config', '/tmp/does_not_exist_mirofish.json')
        assert r.returncode != 0
