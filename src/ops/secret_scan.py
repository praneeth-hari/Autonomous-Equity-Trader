"""
src/ops/secret_scan.py — Find secrets before they are committed or pushed.

  python -m src.ops.secret_scan            # scans every tracked and new (not ignored) file
  python -m src.ops.secret_scan --staged   # only what is staged for the next commit

It reports file and line, never the secret itself. A line that is a deliberate fake (a test
fixture) can carry the marker  secret-scan: allow  to be skipped.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
ALLOW_MARKER = "secret-scan: allow"
MAX_BYTES = 1_000_000
SKIP_NAMES = {"package-lock.json", "requirements.lock.txt"}
# Tests whose whole purpose is to check that secrets get redacted, so they must contain fake ones.
FAKE_SECRET_TESTS = {"tests/pipeline/test_workflow_summary.py"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".woff", ".woff2", ".joblib", ".db", ".pdf", ".zip", ".mp4"}

PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    # In a URL the token follows the word "bot" directly ("bot123456789:AA..."), so no word boundary before the digits.
    ("Telegram bot token", re.compile(r"(?<!\d)\d{8,12}:[A-Za-z0-9_-]{34,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # host after the @ must not be a placeholder: localhost, 127.0.0.1, example.*, [REF] or <name>
    ("Database URL with a password", re.compile(
        r"postgres(?:ql)?(?:\+\w+)?://[^:\s/@]+:(?!\*+@)(?!password@)(?!pass@)(?!xxx)(?!<)[^@\s/]{4,}@"
        r"(?!localhost)(?!127\.0\.0\.1)(?![^/\s:]*\[)(?!<)(?![^/\s:]*example\.)")),
]


def scan_text(text: str) -> List[Tuple[int, str]]:
    """(line number, kind) for each suspicious line. Never returns the secret."""
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARKER in line:
            continue
        for kind, pat in PATTERNS:
            if pat.search(line):
                hits.append((n, kind))
                break
    return hits


def candidate_files(staged: bool = False, root: Path = ROOT) -> Iterable[Path]:
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged else ["git", "ls-files", "-co", "--exclude-standard"]
    out = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=True).stdout.splitlines()
    for rel in out:
        p = root / rel
        if p.is_file() and p.name not in SKIP_NAMES and p.suffix.lower() not in SKIP_SUFFIXES and rel not in FAKE_SECRET_TESTS:
            yield p


def scan_files(paths: Iterable[Path], root: Path = ROOT) -> List[str]:
    findings: List[str] = []
    for p in paths:
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for n, kind in scan_text(text):
            findings.append(f"{p.relative_to(root).as_posix()}:{n}: possible {kind}")
    return findings


def tracked_env_files(root: Path = ROOT) -> List[str]:
    """A real .env must never be tracked; the example file is fine."""
    out = subprocess.run(["git", "ls-files", ".env", ".env.*", "*.env"], cwd=root, capture_output=True, text=True, check=True).stdout.split()
    return [f for f in out if not f.endswith((".example", ".sample", ".template"))]


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Scan for committed secrets.")
    p.add_argument("--staged", action="store_true", help="only files staged for commit")
    a = p.parse_args(argv)
    findings = scan_files(candidate_files(a.staged))
    findings += [f"{f}: a real environment file is tracked by git" for f in tracked_env_files()]
    if findings:
        print("SECRET SCAN FAILED:")
        for f in findings:
            print("  " + f)
        print("Remove the secret (and rotate it if it was ever pushed), or mark a deliberate fake with: " + ALLOW_MARKER)
        return 1
    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
