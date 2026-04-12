from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from src.app.config import Config
from src.adapters.cmd.app import parse_command_line

logger = logging.getLogger(__name__)

DEFAULT_COMMAND_SERVICE_URL = "http://127.0.0.1:9000/"
STATUS_PATH = "/rest/status"
EXECUTE_PATH = "/rest/commands/execute"
LOCAL_SERVICE_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def resolve_command_service_url(cfg: Config, explicit_url: str | None = None) -> str:
    target_url = explicit_url or cfg.CommandServiceUrl or DEFAULT_COMMAND_SERVICE_URL
    return target_url.rstrip("/") + "/"


def is_local_service_url(base_url: str) -> bool:
    hostname = urlparse(base_url).hostname
    return hostname in LOCAL_SERVICE_HOSTS


async def execute_remote_command_once(
    cfg: Config,
    command_parts: list[str],
    explicit_url: str | None = None,
    verbose: bool = False,
) -> int:
    command_line = " ".join(part for part in command_parts if part).strip()
    if not command_line:
        return 0

    command, args = parse_command_line(command_line)
    base_url = resolve_command_service_url(cfg, explicit_url=explicit_url)
    ensure_command_service_ready(cfg, base_url, verbose=verbose)

    payload = json.dumps({"command": command, "args": args}).encode("utf-8")
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
) -> int | None:
    if not is_local_service_url(base_url):
        return None
    if response_payload.get("ok", False):
        return None

    output = str(response_payload.get("output", ""))
    if not output.startswith("❌ 未知命令:"):
        return None

    emit_verbose(f"本地命令服务未识别命令 {command}，回退到当前进程执行", verbose)

    from src.adapters.cmd.app import execute_registered_command
    from src.app.bootstrap_disk import build_context_from_disk

    ctx = await build_context_from_disk(cfg)
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
    request = Request(urljoin(base_url, STATUS_PATH.lstrip("/")), method="GET")
    try:
        with urlopen(request, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("status") == "ok"
    except (URLError, HTTPError, json.JSONDecodeError, TimeoutError, ValueError):
        return False


def wait_for_service_ready(base_url: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if service_is_healthy(base_url):
            return
        time.sleep(0.5)

    raise RuntimeError(f"本地命令服务启动超时: {base_url}")


def launch_detached_web_service(cfg: Config) -> None:
    python_executable = resolve_service_python(cfg.ProjectRoot)
    log_path = cfg.ProjectRoot / "data" / "local" / "command-service.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

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