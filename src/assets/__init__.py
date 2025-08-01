import os
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from src.config import config


class JsonData:
    cache = {}
    base_dir = Path(__file__).resolve().parents[2] / "resources"
    assets_dir = base_dir / "assets"      # repo clone 到这里
    gamedata_dir = base_dir / "gamedata"  # zip 解压到这里

    @classmethod
    def run_git_command(cls, args, cwd=None):
        process = subprocess.Popen(
            ["git"] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        output = []
        for line in process.stdout:
            print(line, end="")
            output.append(line)
        process.wait()
        return type("Result", (), {
            "returncode": process.returncode,
            "stdout": "".join(output),
            "stderr": "".join(output)
        })()

    # === 任务 1：同步 assets repo ===
    @classmethod
    def sync_assets_repo(cls):
        repo_url = getattr(config, "GameDataRepo", None)
        if not repo_url:
            print("[INFO] 未配置 GameDataRepo，跳过 repo 同步")
            return False

        cls.assets_dir.parent.mkdir(parents=True, exist_ok=True)

        # 如果 assets_dir 已存在
        if cls.assets_dir.exists():
            print(f"[INFO] {cls.assets_dir} 已存在，尝试 git pull")
            if (cls.assets_dir / ".git").exists():
                pull_result = cls.run_git_command(["pull"], cwd=cls.assets_dir)
                if pull_result.returncode == 0:
                    print("[INFO] Git pull 成功 ✅")
                    return True
                else:
                    print(f"[WARN] Pull 失败，删除后重新 clone")
                    shutil.rmtree(cls.assets_dir, ignore_errors=True)
            else:
                print("[WARN] {cls.assets_dir} 不是 git 仓库，删除重新 clone")
                shutil.rmtree(cls.assets_dir, ignore_errors=True)

        # clone
        print(f"[INFO] 正在 clone {repo_url} 到 {cls.assets_dir}")
        clone_result = cls.run_git_command(["clone", "--depth", "1", "--progress", repo_url, str(cls.assets_dir)])
        if clone_result.returncode == 0:
            print("[INFO] Clone 成功 ✅")
            return True
        else:
            print(f"[ERROR] Clone 失败: {clone_result.stderr}")
            return False

    # === 任务 2：解压 gamedata.zip 到 gamedata_dir ===
    @classmethod
    def extract_gamedata(cls):
        zip_path = cls.assets_dir / "gamedata.zip"
        if not zip_path.exists():
            print(f"[WARN] {zip_path} 不存在，无法解压")
            return False

        cls.gamedata_dir.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] 解压 {zip_path} 到 {cls.gamedata_dir}")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(cls.gamedata_dir)
            print("[INFO] 解压完成 ✅")
            return True
        except Exception as e:
            print(f"[ERROR] 解压失败: {e}")
            return False

    @classmethod
    def init(cls):
        cls.cache = {}
        repo_ok = cls.sync_assets_repo()
        if repo_ok:
            cls.extract_gamedata()

    @classmethod
    def get_json_data(cls, name: str, folder: str = 'excel'):
        json_path = cls.gamedata_dir / folder / f"{name}.json"
        print(f"[INFO] 获取 JSON 数据: {json_path}")
        if name not in cls.cache:
            if json_path.exists():
                with open(json_path, mode='r', encoding='utf-8') as src:
                    cls.cache[name] = json.load(src)
            else:
                return {}
        return cls.cache[name]

    @classmethod
    def clear_cache(cls, name: str = None):
        if name:
            cls.cache.pop(name, None)
        else:
            cls.cache = {}
