"""
pytest 全局配置 — 确保项目 src 在 sys.path 中。
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
