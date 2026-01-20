# src/config/model.py
import json
import os
from pathlib import Path

from dataclasses import dataclass
from typing import Optional

FILE_PATH = Path(__file__).parent.parent.parent.resolve()

@dataclass
class Config:
    ProjectRoot: Path
    ResourcePath: Path
    GameDataRepo: Optional[str] = None
    BaseUrl: Optional[str] = None

def load_from_disk()-> Config:

    ProjectRoot = FILE_PATH
    ResourcePath = None
    GameDataRepo = None
    BaseUrl = None

    # 按照以下路径顺序寻找config.json文件
    # 1. 当前工作目录
    # 2. resources子目录
    # 3. data子目录
    # 未发现则抛出异常
    possible_paths = [
        FILE_PATH / 'config.json',
        FILE_PATH / 'resources' / 'config.json',
        FILE_PATH / 'data' / 'config.json'
    ]
    for path in possible_paths:
        if path.exists():
            with open(path, 'r') as f:
                config = json.load(f)
                
                cfgResourcePath = config.get('ResourcePath', '')
                if cfgResourcePath == '':
                    # 如果配置文件中没有指定 ResourcePath，则使用默认路径
                    ResourcePath = Path((FILE_PATH / 'resources').resolve())
                else:
                    ResourcePath = Path(cfgResourcePath)

                GameDataRepo = config.get('GameDataRepo', None)
                BaseUrl = config.get('BaseUrl', None)

                break

    if ResourcePath is None:
        raise FileNotFoundError("Could not find config.json in expected locations.")
    

    return Config(
        ProjectRoot=ProjectRoot,
        ResourcePath=ResourcePath,
        GameDataRepo=GameDataRepo,
        BaseUrl=BaseUrl
    )


