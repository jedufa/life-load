from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List


def codex_turn_command_from_env() -> List[str]:
    raw = str(os.environ.get("LIFE_LOAD_CODEX_TURN_CMD") or "").strip()
    if raw:
        return shlex.split(raw)
    if shutil.which("codex"):
        return ["codex", "exec"]
    return []


def _looks_like_codex_cli(cmd: List[str]) -> bool:
    return any(Path(str(part)).name == "codex" or str(part) == "codex" for part in cmd[:2])


def _apply_model_to_codex_command(cmd: List[str], *, model: str) -> List[str]:
    out = list(cmd or [])
    model_name = str(model or "").strip()
    if not model_name or not _looks_like_codex_cli(out):
        return out
    normalized: List[str] = []
    skip_next = False
    for part in out:
        if skip_next:
            skip_next = False
            continue
        token = str(part or "")
        if token in {"-m", "--model"}:
            skip_next = True
            continue
        if token.startswith("--model="):
            continue
        normalized.append(token)
    try:
        exec_idx = normalized.index("exec")
    except ValueError:
        normalized.extend(["--model", model_name])
        return normalized
    normalized[exec_idx + 1:exec_idx + 1] = ["--model", model_name]
    return normalized


def _apply_reasoning_effort_to_codex_command(cmd: List[str], *, reasoning_effort: str) -> List[str]:
    out = list(cmd or [])
    effort = str(reasoning_effort or "").strip().lower()
    if not effort or not _looks_like_codex_cli(out):
        return out
    normalized: List[str] = []
    idx = 0
    while idx < len(out):
        token = str(out[idx] or "")
        if token in {"-c", "--config"} and idx + 1 < len(out):
            cfg = str(out[idx + 1] or "")
            if cfg.startswith("model_reasoning_effort="):
                idx += 2
                continue
            normalized.extend([token, cfg])
            idx += 2
            continue
        if token.startswith("model_reasoning_effort="):
            idx += 1
            continue
        normalized.append(token)
        idx += 1
    try:
        exec_idx = normalized.index("exec")
    except ValueError:
        normalized.extend(["-c", f'model_reasoning_effort="{effort}"'])
        return normalized
    normalized[exec_idx + 1:exec_idx + 1] = ["-c", f'model_reasoning_effort="{effort}"']
    return normalized


def _apply_cwd_to_codex_command(cmd: List[str], *, cwd: Path) -> List[str]:
    out = list(cmd or [])
    if not _looks_like_codex_cli(out):
        return out
    normalized: List[str] = []
    skip_next = False
    for part in out:
        if skip_next:
            skip_next = False
            continue
        token = str(part or "")
        if token in {"-C", "--cd", "--cwd"}:
            skip_next = True
            continue
        if token.startswith("--cd=") or token.startswith("--cwd="):
            continue
        normalized.append(token)
    try:
        exec_idx = normalized.index("exec")
    except ValueError:
        return normalized
    normalized[exec_idx + 1:exec_idx + 1] = ["-C", str(Path(cwd).resolve())]
    return normalized


def run_codex_oneshot(
    *,
    worker_id: str,
    binding_type: str,
    binding_id: str,
    role: str,
    message: str,
    bootstrap_text: str,
    cwd: Path,
    timeout_s: int,
    command: List[str] | None = None,
) -> Dict[str, Any]:
    cmd = _apply_cwd_to_codex_command(list(command or codex_turn_command_from_env()), cwd=Path(cwd))
    if not cmd:
        return {
            "ok": False,
            "content": "",
            "stderr": "LIFE_LOAD_CODEX_TURN_CMD is required for Codex diary extraction",
            "returncode": 127,
        }
    prompt = (
        str(bootstrap_text or "").strip()
        + "\n\n"
        + f"worker_id={worker_id}\nbinding_type={binding_type}\nbinding_id={binding_id}\nrole={role}\n\n"
        + str(message or "")
    ).strip()
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(cwd).resolve()),
            timeout=max(1, int(timeout_s)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "content": str(exc.stdout or ""), "stderr": "Codex diary extraction timed out", "returncode": 124}
    return {
        "ok": proc.returncode == 0,
        "content": str(proc.stdout or "").strip(),
        "stderr": str(proc.stderr or "").strip(),
        "returncode": int(proc.returncode),
    }
