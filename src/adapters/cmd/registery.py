
import logging
from typing import Callable, Dict


logger = logging.getLogger(__name__)

# 命令注册表
command_registry: Dict[str, Callable] = {}


def register_command(name: str):
    """装饰器：注册命令处理函数"""
    def decorator(func: Callable):
        command_registry[name] = func
        return func
    return decorator