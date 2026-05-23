"""GcClient: subprocess wrapper for gc and bd CLI tools.

All calls validate exit code, parse JSON safely, log stderr as warning.
"""
from __future__ import annotations

import glob
import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger("invokerai.gc_client")

_TMP_PERSONA_PATTERN = "/tmp/invokerai-*.persona.md"
_PERSONA_MAX_AGE_SECS = 7200  # 2 hours


@dataclass
class GcError(Exception):
    cmd: list[str]
    exit_code: int
    stdout: str
    stderr: str

    def __str__(self) -> str:
        return (
            f"GcError: cmd={self.cmd!r} exit={self.exit_code} "
            f"stderr={self.stderr!r}"
        )


def _invalidate_gc_cache() -> None:
    """Clear the gc binary cache so the next call to gc_client() re-probes."""
    _gc_cache.clear()


# Module-level cache with TTL 300s.
# Shape: {"client": GcClient | None, "ts": float}
_gc_cache: dict = {}

_GC_CACHE_TTL = 300.0


class GcClient:
    """Thin subprocess wrapper around the gc and bd CLI tools."""

    def run(self, cmd: list[str], parse_json: bool = True) -> dict | str:
        """Execute cmd, return parsed JSON dict or raw string.

        Raises GcError on non-zero exit code.
        Logs stderr as WARNING on every call where stderr is non-empty.
        Returns {"raw": stdout} if stdout cannot be parsed as JSON and parse_json=True.
        """
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            # Binary vanished — invalidate cache so next gc_client() re-probes.
            _invalidate_gc_cache()
            raise GcError(
                cmd=cmd,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
            ) from exc

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if stderr:
            _logger.warning("gc stderr [%s]: %s", " ".join(cmd), stderr.strip())
            # Invalidate cache if the binary reports itself missing.
            if "executable not found" in stderr or "no such file" in stderr.lower():
                _invalidate_gc_cache()

        if proc.returncode != 0:
            raise GcError(
                cmd=cmd,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
            )

        if not parse_json:
            return stdout

        try:
            return json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            return {"raw": stdout}


def gc_client() -> GcClient | None:
    """Return cached GcClient if gc binary is available, else None.

    Cache TTL: 300s. Invalidated when gc binary reports itself missing
    (handled inside GcClient.run).
    """
    now = time.monotonic()
    if _gc_cache:
        age = now - _gc_cache.get("ts", 0.0)
        if age < _GC_CACHE_TTL:
            return _gc_cache.get("client")
        # TTL expired — fall through to re-probe.

    found = shutil.which("gc")
    client: GcClient | None = GcClient() if found else None
    _gc_cache.clear()
    _gc_cache["client"] = client
    _gc_cache["ts"] = now
    return client


def _sweep_tmp_personas(tmp_dir: str = "/tmp") -> None:
    """Delete /tmp/invokerai-*.persona.md files older than 2 hours.

    The tmp_dir parameter exists for testing — in production leave as default.
    """
    pattern = f"{tmp_dir}/invokerai-*.persona.md"
    cutoff = time.time() - _PERSONA_MAX_AGE_SECS
    for path_str in glob.glob(pattern):
        p = Path(path_str)
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
        except OSError:
            pass
