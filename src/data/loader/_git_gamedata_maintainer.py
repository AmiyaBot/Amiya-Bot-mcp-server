import ctypes
import errno
import json
import logging
import os
import shutil
import stat
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.app.config import Config
from src.app.resource_releases import ResourceRelease
from src.app.resource_releases import publish_active_release
from src.app.resource_releases import prune_inactive_releases
from src.app.resource_releases import read_active_release
from src.app.resource_releases import read_published_releases
from src.app.resource_releases import releases_dir
from src.app.resource_releases import resource_update_transactions_dir

log = logging.getLogger("asset")

_AT_FDCWD = -100
_RENAME_EXCHANGE = 2


def _exchange_directories(left: Path, right: Path) -> bool:
    """在支持 renameat2 的 Linux 文件系统上原子交换两个目录。"""
    if os.name != "posix":
        return False

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError):
        return False

    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(left),
        _AT_FDCWD,
        os.fsencode(right),
        _RENAME_EXCHANGE,
    )
    if result == 0:
        return True

    error_number = ctypes.get_errno()
    if error_number in {errno.ENOSYS, errno.EINVAL, errno.EXDEV, errno.EOPNOTSUPP}:
        return False
    raise OSError(error_number, os.strerror(error_number))


@dataclass(frozen=True, slots=True)
class GameDataUpdateResult:
    ok: bool
    result: str
    message: str


@dataclass(frozen=True, slots=True)
class PreparedResourceRelease:
    release_id: str
    root: Path
    transaction_dir: Path | None
    version: str | None
    version_date: str | None
    result: str
    message: str
    fallback_assets: Path | None = None

    @property
    def needs_publish(self) -> bool:
        return self.transaction_dir is not None

class GitGameDataMaintainer:
    def __init__(self, repo_url: str, base_dir: Path):
        self.repo_url = repo_url
        self.base_dir = base_dir
        self.assets_dir = base_dir / "assets"
        self.gamedata_dir = base_dir / "gamedata"

    def is_initialized(self) -> bool:
        return (
            read_active_release(self._config()).root
            / "gamedata"
            / "excel"
            / "character_table.json"
        ).exists()

    def current_release(self) -> ResourceRelease:
        return read_active_release(self._config())

    def current_resource_root(self) -> Path:
        return self.current_release().root

    def _run_git(self, args, cwd=None) -> int:
        p = subprocess.Popen(["git"] + args, cwd=cwd,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if p.stdout:
            for line in p.stdout:
                log.info(line.strip())
        p.wait()
        return p.returncode

    def _git_output(self, args, cwd=None) -> str | None:
        """执行 git 命令并返回 stdout（失败返回 None）。"""
        p = subprocess.Popen(["git"] + args, cwd=cwd,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out_lines = []
        if p.stdout:
            for line in p.stdout:
                line = line.rstrip("\n")
                out_lines.append(line)
                log.info(line)
        p.wait()
        if p.returncode != 0:
            return None
        return "\n".join(out_lines)

    def _is_dirty(self) -> bool:
        """
        assets_dir 工作区是否有改动（对浅克隆也适用）。
        """
        out = self._git_output(
            ["status", "--porcelain"],
            cwd=self.current_resource_root() / "assets",
        )
        return bool(out and out.strip())

    def get_version(self, short: bool = True, with_dirty: bool = True) -> str | None:
        """
        返回用于 bundle.version 的版本串：
        - 默认：<short_head> 或 <short_head>-dirty
        """
        assets_dir = self.current_resource_root() / "assets"
        if not self._is_git_repo(assets_dir):
            return None

        args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
        out = self._git_output(args, cwd=assets_dir)
        if not out:
            return None

        head = out.strip().splitlines()[-1].strip()  # 防御性：取最后一行
        if not head:
            return None

        if with_dirty and self._is_dirty():
            return f"{head}-dirty"
        return head

    def get_version_date(self) -> str | None:
        """
        返回当前 HEAD 提交日期（YYYY-MM-DD）。
        """
        assets_dir = self.current_resource_root() / "assets"
        if not self._is_git_repo(assets_dir):
            return None

        out = self._git_output(["show", "-s", "--format=%cs", "HEAD"], cwd=assets_dir)
        if not out:
            return None

        commit_date = out.strip().splitlines()[-1].strip()
        return commit_date or None

    def _is_git_repo(self, assets_dir: Path | None = None) -> bool:
        target = assets_dir or self.current_resource_root() / "assets"
        return target.exists() and (target / ".git").exists()

    def _local_head_hash(self, assets_dir: Path | None = None) -> str | None:
        target = assets_dir or self.current_resource_root() / "assets"
        out = self._git_output(["rev-parse", "HEAD"], cwd=target)
        return out.strip() if out else None

    def _remote_head_hash(self) -> str | None:
        """
        获取远端 HEAD 指向的 commit hash（不需要本地仓库存在）。
        等价于：git ls-remote <repo> HEAD
        输出形如：<hash>\tHEAD
        """
        out = self._git_output(["ls-remote", self.repo_url, "HEAD"], cwd=None)
        if not out:
            return None
        # 取第一列 hash
        first_line = out.splitlines()[0].strip()
        if not first_line:
            return None
        return first_line.split()[0]

    def sync_repo(self) -> bool:
        if not self.repo_url:
            log.warning("未配置 GameDataRepo，跳过 repo 同步")
            return False

        self.assets_dir.parent.mkdir(parents=True, exist_ok=True)

        if self.assets_dir.exists():
            if (self.assets_dir / ".git").exists():
                if self._run_git(["pull"], cwd=self.assets_dir) == 0:
                    return True
                shutil.rmtree(self.assets_dir, ignore_errors=True)
            else:
                shutil.rmtree(self.assets_dir, ignore_errors=True)

        return self._run_git(["clone", "--depth", "1", "--progress", self.repo_url, str(self.assets_dir)]) == 0

    def prepare_release(self, *, force_rebuild: bool = False) -> PreparedResourceRelease:
        """在隔离事务目录中准备完整候选版本，不修改当前在线版本。"""
        if not self.repo_url:
            raise RuntimeError("未配置 GameDataRepo，无法更新资源")

        current = self.current_release()
        current_assets = current.root / "assets"
        current_head = self._local_head_hash(current_assets) if self._is_git_repo(current_assets) else None
        remote_head = self._remote_head_hash()
        if (
            current.managed
            and current.self_contained
            and not force_rebuild
            and remote_head is not None
            and current_head == remote_head
        ):
            return PreparedResourceRelease(
                release_id=current.release_id,
                root=current.root,
                transaction_dir=None,
                version=current.version or remote_head[:7],
                version_date=current.version_date,
                result="up_to_date",
                message="资源已是最新版本",
            )

        transaction_dir = resource_update_transactions_dir(self._config()) / uuid4().hex
        candidate_root = transaction_dir / "release"
        candidate_assets = candidate_root / "assets"
        transaction_dir.mkdir(parents=True, exist_ok=False)

        cloned = False
        if remote_head is not None:
            cloned = self._run_git(
                ["clone", "--depth", "1", "--progress", self.repo_url, str(candidate_assets)]
            ) == 0

        fallback_assets: Path | None = None
        if not cloned:
            if candidate_assets.exists():
                shutil.rmtree(candidate_assets, ignore_errors=True)
            if not force_rebuild:
                self.discard_prepared_release(transaction_dir)
                raise RuntimeError("拉取资源仓库更新失败")
            fallback_assets = next(
                (
                    assets
                    for assets in self._fallback_assets_candidates(current_assets)
                    if self._is_readable_file(assets / "gamedata.zip")
                ),
                None,
            )
            if fallback_assets is None:
                self.discard_prepared_release(transaction_dir)
                raise RuntimeError("拉取资源仓库失败，当前 gamedata.zip 也不可读")
            zip_path = fallback_assets / "gamedata.zip"
            candidate_root.mkdir(parents=True, exist_ok=True)
        else:
            zip_path = candidate_assets / "gamedata.zip"

        candidate_gamedata = candidate_root / "gamedata"
        try:
            self._extract_zip_to(zip_path, candidate_gamedata)
            self._normalize_permissions(candidate_root)
            version = self._git_value(candidate_assets, ["rev-parse", "--short", "HEAD"])
            version_date = self._git_value(candidate_assets, ["show", "-s", "--format=%cs", "HEAD"])
            if version is None:
                version = current.version or (current_head[:7] if current_head else "local-recovery")
            if version_date is None:
                version_date = current.version_date
            release_id = self._new_release_id(version)
            return PreparedResourceRelease(
                release_id=release_id,
                root=candidate_root,
                transaction_dir=transaction_dir,
                version=version,
                version_date=version_date,
                result="recovered" if fallback_assets is not None else "updated",
                message=(
                    "已使用当前资源包重建候选版本"
                    if fallback_assets is not None
                    else "资源候选版本准备完成"
                ),
                fallback_assets=fallback_assets,
            )
        except Exception:
            self.discard_prepared_release(transaction_dir)
            raise

    def publish_prepared_release(
        self,
        prepared: PreparedResourceRelease,
    ) -> ResourceRelease:
        """候选 Bundle 通过校验后，先固定版本目录，再原子切换活动清单。"""
        if not prepared.needs_publish:
            return self.current_release()

        target_parent = releases_dir(self._config())
        target_parent.mkdir(parents=True, exist_ok=True)
        target = target_parent / prepared.release_id
        if target.exists():
            raise FileExistsError(f"资源版本目录已存在: {target}")
        os.replace(prepared.root, target)

        if prepared.fallback_assets is not None:
            relative_target = os.path.relpath(prepared.fallback_assets, start=target)
            os.symlink(relative_target, target / "assets", target_is_directory=True)

        release = ResourceRelease(
            release_id=prepared.release_id,
            root=target,
            version=prepared.version,
            version_date=prepared.version_date,
            created_at=self._now_iso(),
            self_contained=prepared.fallback_assets is None,
        )
        self._write_release_metadata(release)
        publish_active_release(self._config(), release)
        self.discard_prepared_release(prepared.transaction_dir)
        prune_inactive_releases(self._config())
        return release

    @staticmethod
    def discard_prepared_release(transaction_dir: Path | None) -> None:
        if transaction_dir is not None and transaction_dir.exists():
            shutil.rmtree(transaction_dir, ignore_errors=True)

    def _extract_zip_to(self, zip_path: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=False)
        with zipfile.ZipFile(zip_path, "r") as archive:
            for member in archive.infolist():
                relative = Path(member.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise RuntimeError(f"资源包包含越界路径: {member.filename}")
            archive.extractall(destination)

        marker = destination / "excel" / "character_table.json"
        if not marker.is_file():
            raise RuntimeError(f"解压结果校验失败，缺少 {marker}")

    @staticmethod
    def _normalize_permissions(root: Path) -> None:
        for directory, names, files in os.walk(root):
            directory_path = Path(directory)
            os.chmod(directory_path, 0o755)
            for name in names:
                path = directory_path / name
                if not path.is_symlink():
                    os.chmod(path, 0o755)
            for name in files:
                path = directory_path / name
                if not path.is_symlink():
                    os.chmod(path, 0o644)

        mode = stat.S_IMODE((root / "gamedata" / "excel" / "character_table.json").stat().st_mode)
        if mode & 0o444 == 0:
            raise PermissionError("候选资源权限修复失败: character_table.json 仍不可读")

    @staticmethod
    def _is_readable_file(path: Path) -> bool:
        try:
            with path.open("rb") as file:
                return bool(file.read(1))
        except OSError:
            return False

    def _write_release_metadata(self, release: ResourceRelease) -> None:
        payload = {
            "release_id": release.release_id,
            "version": release.version,
            "version_date": release.version_date,
            "created_at": release.created_at,
            "self_contained": release.self_contained,
        }
        path = release.root / "release.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(path, 0o644)

    def _git_value(self, assets_dir: Path, args: list[str]) -> str | None:
        if not self._is_git_repo(assets_dir):
            return None
        output = self._git_output(args, cwd=assets_dir)
        if not output:
            return None
        return output.strip().splitlines()[-1].strip() or None

    def _fallback_assets_candidates(self, current_assets: Path) -> list[Path]:
        current, previous = read_published_releases(self._config())
        candidates = [
            current_assets,
            *(item.root / "assets" for item in (current, previous) if item is not None),
            self.assets_dir,
        ]
        result: list[Path] = []
        for candidate in candidates:
            if candidate not in result:
                result.append(candidate)
        return result

    def _new_release_id(self, version: str | None) -> str:
        safe_version = "".join(
            character for character in str(version or "unknown") if character.isalnum() or character in "-_"
        )[:24] or "unknown"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{safe_version}-{timestamp}-{uuid4().hex[:8]}"

    def _config(self) -> Config:
        return Config(
            ProjectRoot=self.base_dir.parent,
            ResourcePath=self.base_dir,
            GameDataRepo=self.repo_url,
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def extract_zip(self) -> bool:
        zip_path = self.assets_dir / "gamedata.zip"
        if not zip_path.exists():
            log.warning("%s 不存在，无法解压", zip_path)
            return False

        self.base_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(
            tempfile.mkdtemp(prefix=".gamedata-staging-", dir=self.base_dir)
        )
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(staging_dir)

            marker = staging_dir / "excel" / "character_table.json"
            if not marker.is_file():
                log.error("解压结果校验失败，缺少 %s", marker)
                return False

            self._publish_extracted_directory(staging_dir)
            return True
        except Exception:
            log.exception("解压失败")
            return False
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def _publish_extracted_directory(self, staging_dir: Path) -> None:
        """完整解包并校验后再切换在线目录。"""
        if not self.gamedata_dir.exists():
            os.replace(staging_dir, self.gamedata_dir)
            return

        if _exchange_directories(self.gamedata_dir, staging_dir):
            # 交换后 staging_dir 指向旧数据，由 extract_zip() 的 finally 回收。
            return

        # 非 Linux 或文件系统不支持 RENAME_EXCHANGE 时的兼容路径。
        backup_dir = staging_dir.with_name(f"{staging_dir.name}-previous")
        os.replace(self.gamedata_dir, backup_dir)
        try:
            os.replace(staging_dir, self.gamedata_dir)
        except Exception:
            os.replace(backup_dir, self.gamedata_dir)
            raise
        shutil.rmtree(backup_dir, ignore_errors=True)

    def update(self) -> GameDataUpdateResult:
        """
        先比较远端 hash，确定是否需要 pull：
        - 本地没初始化：clone + 解压
        - 本地是 git repo：比较 local HEAD vs remote HEAD，一致则不做事
        - 不一致才 pull + 解压
        """
        if not self.repo_url:
            log.warning("未配置 GameDataRepo，跳过更新")
            return GameDataUpdateResult(ok=False, result="failed", message="未配置 GameDataRepo，无法更新资源")

        # 1) 如果还没 clone（或目录不是 git repo），走原逻辑：clone/pull + 解压
        if not self._is_git_repo(self.assets_dir):
            ok = self.sync_repo()
            if not ok:
                return GameDataUpdateResult(ok=False, result="failed", message="首次拉取资源仓库失败")
            if not self.extract_zip():
                return GameDataUpdateResult(ok=False, result="failed", message="首次解压资源包失败")
            return GameDataUpdateResult(ok=True, result="updated", message="首次资源初始化完成")

        # 2) 已有仓库：先对比 hash
        remote_hash = self._remote_head_hash()
        local_hash = self._local_head_hash(self.assets_dir)

        if not remote_hash or not local_hash:
            # 无法获取 hash（网络/权限/仓库损坏等），保守起见走 sync_repo
            log.warning("无法获取 hash（remote=%s local=%s），无法同步", remote_hash, local_hash)
            return GameDataUpdateResult(ok=False, result="failed", message="无法获取资源仓库版本信息")

        if remote_hash == local_hash:
            log.info("GameDataRepo 无更新（HEAD=%s），跳过 pull/extract", local_hash)
            return GameDataUpdateResult(ok=True, result="up_to_date", message="资源已是最新版本")

        # 3) 有更新才 pull + 解压
        log.info("检测到远端更新：local=%s remote=%s，开始 pull", local_hash, remote_hash)
        ok = self._run_git(["pull"], cwd=self.assets_dir) == 0
        if not ok:
            return GameDataUpdateResult(ok=False, result="failed", message="拉取资源仓库更新失败")
        if not self.extract_zip():
            return GameDataUpdateResult(ok=False, result="failed", message="解压最新资源包失败")
        return GameDataUpdateResult(ok=True, result="updated", message="资源更新完成")
