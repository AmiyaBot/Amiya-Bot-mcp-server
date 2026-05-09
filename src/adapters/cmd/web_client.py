from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from src.app.config import Config
from src.app.runtime_state import command_service_log_path
from src.adapters.cmd.app import parse_command_line

logger = logging.getLogger(__name__)

DEFAULT_COMMAND_SERVICE_URL = "http://127.0.0.1:9000/"
STATUS_PATH = "/rest/status"
EXECUTE_PATH = "/rest/commands/execute"
LOCAL_SERVICE_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
SERVICE_GIT_SHA_ENV_KEYS = ("AMIYA_GIT_SHA", "GIT_SHA", "SOURCE_COMMIT")


def resolve_command_service_url(cfg: Config, explicit_url: str | None = None) -> str:
    target_url = explicit_url or cfg.CommandServiceUrl or DEFAULT_COMMAND_SERVICE_URL
    return target_url.rstrip("/") + "/"


def is_local_service_url(base_url: str) -> bool:
    hostname = urlparse(base_url).hostname
    return hostname in LOCAL_SERVICE_HOSTS


def compute_service_code_revision(project_root: Path) -> str:
    hasher = hashlib.sha1()
    candidates = [project_root / "main.py"]
    src_root = project_root / "src"
    if src_root.exists():
        candidates.extend(sorted(src_root.rglob("*.py")))

    for path in candidates:
        try:
            stat = path.stat()
            relative_path = path.relative_to(project_root).as_posix()
        except OSError:
            continue
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(str(stat.st_mtime_ns).encode("utf-8"))
        hasher.update(str(stat.st_size).encode("utf-8"))
    return hasher.hexdigest()[:12]


def resolve_service_git_sha(project_root: Path) -> str:
    for env_key in SERVICE_GIT_SHA_ENV_KEYS:
        value = os.environ.get(env_key, "").strip()
        if value:
            return value

    git_dir = project_root / ".git"
    if not git_dir.exists():
        return "unknown"

    try:
        completed = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"

    value = completed.stdout.strip()
    return value or "unknown"


async def execute_remote_command_once(
    cfg: Config,
    command_parts: list[str],
    explicit_url: str | None = None,
    verbose: bool = False,
    output_format: str = "markdown",
) -> int:
    command_line = " ".join(part for part in command_parts if part).strip()
    if not command_line:
        return 0

    command, args = parse_command_line(command_line)
    base_url = resolve_command_service_url(cfg, explicit_url=explicit_url)
    ensure_command_service_ready(cfg, base_url, verbose=verbose)

    if should_execute_locally_for_current_runtime(cfg, base_url):
        emit_verbose("检测到本地命令服务版本落后，回退到当前进程执行", verbose)
        return await execute_local_command(
            cfg=cfg,
            command=command,
            args=args,
            output_format=output_format,
            prefer_local_artifact_path=True,
        )

    payload = json.dumps({"command": command, "args": args, "output_format": output_format}).encode("utf-8")
    request = Request(
        urljoin(base_url, EXECUTE_PATH.lstrip("/")),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"❌ 命令服务返回 HTTP {exc.code}: {detail}")
        return 1
    except URLError as exc:
        print(f"❌ 无法连接命令服务: {exc}")
        return 1

    fallback_exit_code = await try_execute_locally_when_service_is_stale(
        cfg=cfg,
        base_url=base_url,
        command=command,
        args=args,
        response_payload=response_payload,
        verbose=verbose,
        output_format=output_format,
    )
    if fallback_exit_code is not None:
        return fallback_exit_code

    output = response_payload.get("output", "")
    if output:
        print(output)
    return 0 if response_payload.get("ok", False) else 1


async def try_execute_locally_when_service_is_stale(
    cfg: Config,
    base_url: str,
    command: str,
    args: str,
    response_payload: dict,
    verbose: bool = False,
    output_format: str = "markdown",
) -> int | None:
    if not is_local_service_url(base_url):
        return None
    if response_payload.get("ok", False):
        return None

    output = str(response_payload.get("output", ""))
    if not output.startswith("❌ 未知命令:"):
        return None

    emit_verbose(f"本地命令服务未识别命令 {command}，回退到当前进程执行", verbose)

    return await execute_local_command(
        cfg=cfg,
        command=command,
        args=args,
        output_format=output_format,
        prefer_local_artifact_path=True,
    )


async def execute_local_command(
    cfg: Config,
    command: str,
    args: str,
    output_format: str,
    prefer_local_artifact_path: bool,
) -> int:
    from src.adapters.cmd.app import execute_registered_command
    from src.app.bootstrap_disk import build_context_from_disk

    ctx = await build_context_from_disk(cfg)
    ctx = replace(
        ctx,
        prefer_local_artifact_path=prefer_local_artifact_path,
        output_format=output_format,
    )
    result = await execute_registered_command(ctx, command, args)
    if result.output:
        print(result.output)
    return 0 if result.ok else 1


def ensure_command_service_ready(cfg: Config, base_url: str, verbose: bool = False) -> None:
    if service_is_healthy(base_url):
        return

    if not is_local_service_url(base_url):
        raise RuntimeError(f"目标命令服务不可用: {base_url}")

    emit_verbose(f"本地命令服务不可用，正在后台启动: {base_url}", verbose)
    launch_detached_web_service(cfg)
    wait_for_service_ready(base_url, timeout_seconds=30.0)
    emit_verbose(f"本地命令服务已就绪: {base_url}", verbose)


def service_is_healthy(base_url: str) -> bool:
    payload = fetch_service_status(base_url)
    return bool(payload and payload.get("status") == "ok")


def fetch_service_status(base_url: str) -> dict | None:
    request = Request(urljoin(base_url, STATUS_PATH.lstrip("/")), method="GET")
    try:
        with urlopen(request, timeout=1.5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError, TimeoutError, ValueError):
        return None


def should_execute_locally_for_current_runtime(cfg: Config, base_url: str) -> bool:
    if not is_local_service_url(base_url):
        return False

    payload = fetch_service_status(base_url)
    if not payload or payload.get("status") != "ok":
        return False

    expected_revision = compute_service_code_revision(cfg.ProjectRoot)
    running_revision = payload.get("code_revision")
    return running_revision != expected_revision


def wait_for_service_ready(base_url: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if service_is_healthy(base_url):
            return
        time.sleep(0.5)

    raise RuntimeError(f"本地命令服务启动超时: {base_url}")


def launch_detached_web_service(cfg: Config) -> None:
    python_executable = resolve_service_python(cfg.ProjectRoot)
    log_path = command_service_log_path(cfg)

    logger.info("尝试在后台启动本地 Web 服务: %s", log_path)
    with log_path.open("ab") as log_file:
        subprocess.Popen(
            [str(python_executable), "-m", "src.cli_entry", "web"],
            cwd=str(cfg.ProjectRoot),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )


def resolve_service_python(project_root: Path) -> Path:
    venv_python = project_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def emit_verbose(message: str, verbose: bool) -> None:
    if verbose:
        print(message, file=sys.stderr)