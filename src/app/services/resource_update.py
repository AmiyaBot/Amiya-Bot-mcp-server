from __future__ import annotations

import fcntl
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.app.config import Config
from src.app.runtime_state import resource_update_lock_path
from src.app.runtime_state import resource_update_log_path
from src.app.runtime_state import resource_update_status_path
from src.data.loader._git_gamedata_maintainer import GitGameDataMaintainer
from src.data.loader._git_gamedata_maintainer import PreparedResourceRelease
from src.data.models.bundle import DataBundle
from src.data.repository.bundle.bundle_builder import load_bundle_from_disk
from src.data.repository.bundle.bundle_validation import validate_data_bundle

log = logging.getLogger(__name__)

RESOURCE_NOT_READY_MESSAGE = (
    "❌ 本地资源暂未就绪，服务正在自动恢复；"
    "可执行 resource-update-status 查看进度。"
)


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
    bundle: DataBundle | None = None
    resource_root: Path | None = None

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
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(
            json.dumps(asdict(status), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


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


def perform_resource_update(
    cfg: Config,
    trigger: str,
    *,
    current_bundle_valid: bool = False,
    current_version: str | None = None,
    force_rebuild: bool = False,
) -> ResourceUpdateExecutionResult:
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
        prepared: PreparedResourceRelease | None = None
        try:
            prepared = maintainer.prepare_release(
                force_rebuild=force_rebuild,
            )
            bundle = _build_required_bundle(
                cfg,
                prepared,
                current_bundle_valid=current_bundle_valid,
                current_version=current_version,
            )
        except Exception as first_error:
            if prepared is not None:
                maintainer.discard_prepared_release(prepared.transaction_dir)
            if force_rebuild or (prepared is not None and prepared.needs_publish):
                return _finish_failed_update(cfg, status, str(first_error))

            log.warning(
                "当前资源校验失败，改为重建独立候选版本: %s",
                first_error,
            )
            try:
                prepared = maintainer.prepare_release(force_rebuild=True)
                bundle = _build_required_bundle(
                    cfg,
                    prepared,
                    current_bundle_valid=False,
                    current_version=current_version,
                )
            except Exception as recovery_error:
                if prepared is not None:
                    maintainer.discard_prepared_release(prepared.transaction_dir)
                return _finish_failed_update(cfg, status, str(recovery_error))

        try:
            release = maintainer.publish_prepared_release(prepared)
        except Exception as exc:
            maintainer.discard_prepared_release(prepared.transaction_dir)
            return _finish_failed_update(cfg, status, f"发布候选资源失败: {exc}")

        if bundle is not None and bundle.resource_root != release.root:
            bundle = replace(bundle, resource_root=release.root)

        message = (
            "资源已完成校验并原子切换"
            if prepared.needs_publish
            else prepared.message
        )
        status.current_state = "idle"
        status.last_finished_at = _now_iso()
        status.last_success_at = status.last_finished_at
        status.last_result = prepared.result
        status.message = message
        status.pid = None
        status.trigger = trigger
        status.version = prepared.version
        status.version_date = prepared.version_date
        write_resource_update_status(cfg, status)
        return ResourceUpdateExecutionResult(
            ok=True,
            result=prepared.result,
            message=message,
            version=prepared.version,
            version_date=prepared.version_date,
            bundle=bundle,
            resource_root=release.root,
        )


def resource_update_in_progress(cfg: Config) -> bool:
    """以 flock 为权威信号判断资源事务是否仍在执行。"""
    lock_path = resource_update_lock_path(cfg)
    try:
        lock_file = lock_path.open("a+b")
    except OSError:
        log.warning("资源更新锁不可访问，按事务仍在执行处理: %s", lock_path, exc_info=True)
        return True
    with lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            log.warning("资源更新锁状态不可确认，按事务仍在执行处理", exc_info=True)
            return True
        finally:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    return False


def wait_for_resource_update(cfg: Config, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while resource_update_in_progress(cfg):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)
    return True


def _build_required_bundle(
    cfg: Config,
    prepared: PreparedResourceRelease,
    *,
    current_bundle_valid: bool,
    current_version: str | None,
) -> DataBundle | None:
    if (
        not prepared.needs_publish
        and current_bundle_valid
        and current_version == prepared.version
    ):
        return None
    bundle = load_bundle_from_disk(
        cfg,
        version=prepared.version,
        resource_root=prepared.root,
    )
    validate_data_bundle(bundle)
    return bundle


def _finish_failed_update(
    cfg: Config,
    status: ResourceUpdateStatus,
    message: str,
) -> ResourceUpdateExecutionResult:
    status.current_state = "idle"
    status.last_finished_at = _now_iso()
    status.last_result = "failed"
    status.message = message or "资源更新失败"
    status.pid = None
    write_resource_update_status(cfg, status)
    return ResourceUpdateExecutionResult(
        ok=False,
        result="failed",
        message=status.message,
        version=status.version,
        version_date=status.version_date,
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
        "recovered": "成功（已恢复）",
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
