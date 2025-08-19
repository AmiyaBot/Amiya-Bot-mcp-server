import os
import json
import shutil
import subprocess
import zipfile
import logging
from pathlib import Path
from src.accessories.config import config

logger = logging.getLogger("asset")
logger.setLevel(logging.INFO)  # 默认日志等级

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
            logger.info(line.strip())
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
            logger.warning("未配置 GameDataRepo，跳过 repo 同步")
            return False

        cls.assets_dir.parent.mkdir(parents=True, exist_ok=True)

        # 如果 assets_dir 已存在
        if cls.assets_dir.exists():
            logger.info(f"{cls.assets_dir} 已存在，尝试更新")
            if (cls.assets_dir / ".git").exists():
                pull_result = cls.run_git_command(["pull"], cwd=cls.assets_dir)
                if pull_result.returncode == 0:
                    logger.info("Git pull 成功")
                    return True
                else:
                    logger.warning(f"Git pull 失败: {pull_result.stderr}")
                    shutil.rmtree(cls.assets_dir, ignore_errors=True)
            else:
                logger.warning(f"{cls.assets_dir} 不是一个有效的 git 仓库，删除重新 clone")
                shutil.rmtree(cls.assets_dir, ignore_errors=True)

        # clone
        logger.info(f"开始 clone {repo_url} 到 {cls.assets_dir}")
        clone_result = cls.run_git_command(["clone", "--depth", "1", "--progress", repo_url, str(cls.assets_dir)])
        if clone_result.returncode == 0:
            logger.info("Git clone 成功")
            return True
        else:
            logger.error(f"Git clone 失败: {clone_result.stderr}")
            return False

    # === 任务 2：解压 gamedata.zip 到 gamedata_dir ===
    @classmethod
    def extract_gamedata(cls):
        zip_path = cls.assets_dir / "gamedata.zip"
        if not zip_path.exists():
            logger.warning(f"{zip_path} 不存在，无法解压")
            return False

        cls.gamedata_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"开始解压 {zip_path} 到 {cls.gamedata_dir}")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(cls.gamedata_dir)
            logger.info(f"解压完成，文件已存储在 {cls.gamedata_dir}")
            return True
        except Exception as e:
            logger.error(f"解压失败: {e}")
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
        logger.debug(f"获取 JSON 数据: {json_path}")
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
