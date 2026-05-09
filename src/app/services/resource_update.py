from __future__ import annotations

import fcntl
import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.app.config import Config
from src.app.runtime_state import resource_update_lock_path
from src.app.runtime_state import resource_update_log_path
from src.app.runtime_state import resource_update_status_path
from src.data.loader._git_gamedata_maintainer import GitGameDataMaintainer

log = logging.getLogger(__name__)

RESOURCE_NOT_READY_MESSAGE = "❌ 本地资源尚未初始化，请先执行 resource-update 启动一次资源更新。"


@dataclass(slots=True)
class ResourceUpdateStatus:
    current_state: str = "idle"
    last_result: str = "never"
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success_at: str | None = None
    message: str | None = None
    version: str | None = None
    version_date: str | None = None
    pid: int | None = None
    trigger: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceUpdateExecutionResult:
    ok: bool
    result: str
    message: str
    version: str | None = None
    version_date: str | None = None

def is_resource_initialized(cfg: Config) -> bool:
    maintainer = GitGameDataMaintainer(cfg.GameDataRepo or "", cfg.ResourcePath)
    return maintainer.is_initialized()


def read_resource_update_status(cfg: Config) -> ResourceUpdateStatus:
    path = resource_update_status_path(cfg)
    if not path.exists():
        return ResourceUpdateStatus()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("读取资源更新状态失败: %s", path)
        return ResourceUpdateStatus(message="资源更新状态文件读取失败")

    if not isinstance(payload, dict):
        return ResourceUpdateStatus(message="资源更新状态文件格式无效")

    status = ResourceUpdateStatus(
        current_state=str(payload.get("current_state", "idle") or "idle"),
        last_result=str(payload.get("last_result", "never") or "never"),
        last_started_at=_optional_str(payload.get("last_started_at")),
        last_finished_at=_optional_str(payload.get("last_finished_at")),
        last_success_at=_optional_str(payload.get("last_success_at")),
        message=_optional_str(payload.get("message")),
        version=_optional_str(payload.get("version")),
        version_date=_optional_str(payload.get("version_date")),
        pid=_optional_int(payload.get("pid")),
        trigger=_optional_str(payload.get("trigger")),
    )
    return _normalize_resource_update_status(cfg, status)


def write_resource_update_status(cfg: Config, status: ResourceUpdateStatus) -> None:
    path = resource_update_status_path(cfg)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(asdict(status), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def launch_resource_update_worker(cfg: Config) -> ResourceUpdateExecutionResult:
    status = read_resource_update_status(cfg)
    if status.current_state == "running":
        return ResourceUpdateExecutionResult(
            ok=True,
            result="already_running",
            message="资源更新已在进行中，可稍后执行 resource-update-status 查看结果。",
            version=status.version,
            version_date=status.version_date,
        )

    python_executable = _resolve_worker_python(cfg.ProjectRoot)
    log_path = resource_update_log_path(cfg)

    try:
        with log_path.open("ab") as log_file:
            process = subprocess.Popen(
                [str(python_executable), "-m", "src.entrypoints.resource_update_worker"],
                cwd=str(cfg.ProjectRoot),
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
    except OSError as exc:
        return ResourceUpdateExecutionResult(
            ok=False,
            result="failed_to_launch",
            message=f"无法启动资源更新进程: {exc}",
        )

    running_status = read_resource_update_status(cfg)
    running_status.current_state = "running"
    running_status.last_started_at = _now_iso()
    running_status.message = "手动触发的资源更新已启动"
    running_status.pid = process.pid
    running_status.trigger = "manual"
    write_resource_update_status(cfg, running_status)
    return ResourceUpdateExecutionResult(
        ok=True,
        result="started",
        message="已启动资源更新，可稍后执行 resource-update-status 查看结果。",
        version=running_status.version,
        version_date=running_status.version_date,
    )


def perform_resource_update(cfg: Config, trigger: str) -> ResourceUpdateExecutionResult:
    lock_path = resource_update_lock_path(cfg)
    with lock_path.open("a+b") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return ResourceUpdateExecutionResult(
                ok=False,
                result="already_running",
                message="另一项资源更新正在进行中",
            )

        status = read_resource_update_status(cfg)
        status.current_state = "running"
        status.last_started_at = _now_iso()
        status.message = f"资源更新进行中（触发方式: {trigger}）"
        status.pid = os.getpid()
        status.trigger = trigger
        write_resource_update_status(cfg, status)

        maintainer = GitGameDataMaintainer(cfg.GameDataRepo or "", cfg.ResourcePath)
        result = maintainer.update()
        version = maintainer.get_version(short=True, with_dirty=True)
        version_date = maintainer.get_version_date()

        status.current_state = "idle"
        status.last_finished_at = _now_iso()
        status.pid = None
        status.trigger = trigger
        status.version = version
        status.version_date = version_date

        if result.ok:
            status.last_result = result.result
            status.last_success_at = status.last_finished_at
            status.message = result.message
            write_resource_update_status(cfg, status)
            return ResourceUpdateExecutionResult(
                ok=True,
                result=result.result,
                message=result.message,
                version=version,
                version_date=version_date,
            )

        status.last_result = "failed"
        status.message = result.message
        write_resource_update_status(cfg, status)
        return ResourceUpdateExecutionResult(
            ok=False,
            result="failed",
            message=result.message,
            version=version,
            version_date=version_date,
        )


def format_resource_update_status(cfg: Config, status: ResourceUpdateStatus) -> str:
    state_label = {
        "idle": "空闲",
        "running": "运行中",
    }.get(status.current_state, status.current_state)
    result_label = {
        "never": "从未执行",
        "updated": "成功（已更新）",
        "up_to_date": "成功（已是最新）",
        "failed": "失败",
    }.get(status.last_result, status.last_result)

    lines = [
        "📦 资源更新状态",
        f"本地资源: {'已初始化' if is_resource_initialized(cfg) else '未初始化'}",
        f"当前状态: {state_label}",
        f"上次结果: {result_label}",
    ]
    if status.last_started_at:
        lines.append(f"上次开始: {status.last_started_at}")
    if status.last_finished_at:
        lines.append(f"上次结束: {status.last_finished_at}")
    if status.last_success_at:
        lines.append(f"最近成功: {status.last_success_at}")
    if status.version:
        lines.append(f"资源版本: {status.version}")
    if status.version_date:
        lines.append(f"提交日期: {status.version_date}")
    if status.message:
        lines.append(f"详情: {status.message}")
    return "\n".join(lines)


def _normalize_resource_update_status(cfg: Config, status: ResourceUpdateStatus) -> ResourceUpdateStatus:
    if status.current_state != "running":
        return status
    if status.pid is not None and _is_process_alive(status.pid):
        return status

    status.current_state = "idle"
    status.pid = None
    if status.last_finished_at is None:
        status.last_finished_at = _now_iso()
    if status.last_result == "never":
        status.last_result = "failed"
    status.message = "更新进程已退出，但未写入最终状态"
    write_resource_update_status(cfg, status)
    return status


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _resolve_worker_python(project_root: Path) -> Path:
    venv_python = project_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)