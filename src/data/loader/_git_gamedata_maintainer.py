import logging
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("asset")


@dataclass(frozen=True, slots=True)
class GameDataUpdateResult:
    ok: bool
    result: str
    message: str

class GitGameDataMaintainer:
    def __init__(self, repo_url: str, base_dir: Path):
        self.repo_url = repo_url
        self.base_dir = base_dir
        self.assets_dir = base_dir / "assets"
        self.gamedata_dir = base_dir / "gamedata"

    def is_initialized(self) -> bool:
        return (self.gamedata_dir / "excel" / "character_table.json").exists()

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
        out = self._git_output(["status", "--porcelain"], cwd=self.assets_dir)
        return bool(out and out.strip())

    def get_version(self, short: bool = True, with_dirty: bool = True) -> str | None:
        """
        返回用于 bundle.version 的版本串：
        - 默认：<short_head> 或 <short_head>-dirty
        """
        if not self._is_git_repo():
            return None

        args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
        out = self._git_output(args, cwd=self.assets_dir)
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
        if not self._is_git_repo():
            return None

        out = self._git_output(["show", "-s", "--format=%cs", "HEAD"], cwd=self.assets_dir)
        if not out:
            return None

        commit_date = out.strip().splitlines()[-1].strip()
        return commit_date or None

    def _is_git_repo(self) -> bool:
        return self.assets_dir.exists() and (self.assets_dir / ".git").exists()

    def _local_head_hash(self) -> str | None:
        out = self._git_output(["rev-parse", "HEAD"], cwd=self.assets_dir)
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

    def extract_zip(self) -> bool:
        zip_path = self.assets_dir / "gamedata.zip"
        if not zip_path.exists():
            log.warning("%s 不存在，无法解压", zip_path)
            return False

        self.gamedata_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(self.gamedata_dir)
            return True
        except Exception:
            log.exception("解压失败")
            return False

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
        if not self._is_git_repo():
            ok = self.sync_repo()
            if not ok:
                return GameDataUpdateResult(ok=False, result="failed", message="首次拉取资源仓库失败")
            if not self.extract_zip():
                return GameDataUpdateResult(ok=False, result="failed", message="首次解压资源包失败")
            return GameDataUpdateResult(ok=True, result="updated", message="首次资源初始化完成")

        # 2) 已有仓库：先对比 hash
        remote_hash = self._remote_head_hash()
        local_hash = self._local_head_hash()

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
