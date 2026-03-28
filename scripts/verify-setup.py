"""
MiroFish Setup Verification Script

Validates that the MiroFish installation is correctly configured before running
the backend. Uses only Python stdlib so it can be run before `pip install`.

Usage:
    python scripts/verify-setup.py   (from the repo root)

Exits 0 if all required checks pass, 1 if any required check fails.
"""

import os, sys, importlib

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_FILE  = os.path.join(REPO_ROOT, ".env")
VENV_DIR  = os.path.join(REPO_ROOT, ".venv")
DATA_DIR  = os.path.join(REPO_ROOT, "data")
REQUIRED_PACKAGES = ["mcp", "graphiti_core", "anthropic", "camel"]


def load_dotenv_simple(path):
    """Parse a .env file and return a dict of key=value pairs (stdlib only)."""
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def main():
    failures = []
    print("MiroFish Setup Verification")
    print("=" * 40)

    # 1. Python version >= 3.11
    ok = sys.version_info >= (3, 11)
    ver = "{}.{}.{}".format(*sys.version_info[:3])
    print(f"{'✓' if ok else '✗'} Python {ver}" + ("" if ok else " — need >= 3.11"))
    if not ok:
        failures.append("python-version")

    # 2. .env file exists
    env_exists = os.path.isfile(ENV_FILE)
    if env_exists:
        print("✓ .env file found")
    else:
        print("✗ .env file not found — run: cp .env.example .env")
        failures.append("env-file")

    # Parse .env for subsequent checks
    env_vars = {}
    if env_exists:
        try:
            env_vars = load_dotenv_simple(ENV_FILE)
        except Exception as e:
            print(f"  (Warning: could not parse .env — {e})")

    # 3. ANTHROPIC_API_KEY set and not a bare placeholder
    key      = env_vars.get("ANTHROPIC_API_KEY", "")
    base_url = env_vars.get("ANTHROPIC_BASE_URL", "")
    placeholder_terms = ("placeholder", "your_", "xxx")
    is_placeholder = not key or any(p in key.lower() for p in placeholder_terms)
    has_local_proxy = any(h in base_url for h in ("localhost", "127.0.0.1"))
    if not is_placeholder:
        print("✓ ANTHROPIC_API_KEY is set")
    elif is_placeholder and has_local_proxy:
        print("✓ ANTHROPIC_API_KEY is a placeholder but a localhost proxy is configured")
    else:
        print("✗ ANTHROPIC_API_KEY is not set or is a placeholder (and no localhost proxy found)")
        failures.append("anthropic-key")

    # 4. Virtual environment at .venv/
    venv_ok = os.path.isdir(VENV_DIR)
    print(f"{'✓' if venv_ok else '✗'} .venv/ directory" + ("" if venv_ok else " missing — run: python -m venv .venv"))
    if not venv_ok:
        failures.append("venv")

    # 5. Key packages importable
    pkg_all_ok = True
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
            print(f"  ✓ import {pkg}")
        except ImportError:
            print(f"  ✗ import {pkg} — not installed")
            pkg_all_ok = False
    if not pkg_all_ok:
        failures.append("packages")

    # 6. data/ directory exists and is writable
    if not os.path.isdir(DATA_DIR):
        print("✗ data/ directory missing — run: mkdir data")
        failures.append("data-dir")
    elif not os.access(DATA_DIR, os.W_OK):
        print("✗ data/ directory exists but is not writable")
        failures.append("data-dir")
    else:
        print("✓ data/ directory exists and is writable")

    # 7. Optional: OPENAI_API_KEY (improves vector search quality)
    oai = env_vars.get("OPENAI_API_KEY", "")
    if oai and "your_" not in oai:
        print("✓ (optional) OPENAI_API_KEY is set — vector search enabled")
    else:
        print("~ (optional) OPENAI_API_KEY not set — semantic search quality may be reduced")

    # Summary
    print("=" * 40)
    if not failures:
        print("All checks passed. MiroFish is ready to run.")
        sys.exit(0)
    else:
        print(f"Failed checks: {', '.join(failures)}")
        print("Fix the issues above, then re-run this script.")
        sys.exit(1)


if __name__ == "__main__":
    main()
