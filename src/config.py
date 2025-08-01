import json

from dataclasses import dataclass


@dataclass
class Config:
    GameDataPath: str
    GameDataRepo: str


with open('config.json', 'r') as f:
    config = Config(**json.load(f))
