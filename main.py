import asyncio
import logging
import sys
import argparse

from pathlib import Path

from src.entrypoints.uvicorn_host import uvicorn_main
from src.entrypoints.command_line import cmd_main

logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-C",
        "--custom-mode",
        action="store_true",
        help="启动时进入命令行模式"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    # 可以用环境变量 / 全局变量 / 配置传递
    if args.custom_mode:
        print("🚀 使用 -C 启动，进入命令行模式")
        asyncio.run(cmd_main())
        sys.exit(0)
    else:
        uvicorn_main()
        sys.exit(0)

