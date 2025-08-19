import json
from pathlib import Path

GLOSSARY = {}

with open('data/glossary.json', 'r') as f:
    GLOSSARY = json.load(f)

__all__ = ["GLOSSARY"]

