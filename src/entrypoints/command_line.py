# 该代码执行命令行交互，从disk构造ctx后，用户输入一个命令后跟参数，程序执行并输出结果，命令在cmd adapter下注册

import logging
import sys

from src.app.bootstrap_disk import build_context_from_disk
from src.app.config import load_from_disk

from src.adapters.cmd.app import CommandLineInterface

logger = logging.getLogger(__name__)

async def cmd_main():
    """主函数：初始化上下文并启动CLI"""
    try:
        logger.info("正在初始化应用上下文...")
        cfg = load_from_disk()
        ctx = await build_context_from_disk(cfg)
        logger.info("✅ 上下文初始化完成")
        
        # 启动命令行界面
        cli = CommandLineInterface(ctx)
        await cli.run()
        
    except Exception as e:
        logger.exception("初始化失败")
        print(f"❌ 初始化失败: {e}")
        sys.exit(1)

