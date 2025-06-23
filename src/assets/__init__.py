import os
import json

from src.config import config


class JsonData:
    cache = {}

    @classmethod
    def get_json_data(cls, name: str, folder: str = 'excel'):
        if name not in cls.cache:
            path = f'{config.GameDataPath}/gamedata/{folder}/{name}.json'
            if os.path.exists(path):
                with open(path, mode='r', encoding='utf-8') as src:
                    cls.cache[name] = json.load(src)
            else:
                return {}

        return cls.cache[name]

    @classmethod
    def clear_cache(cls, name: str = None):
        if name:
            del cls.cache[name]
        else:
            cls.cache = {}
