# 该代码执行命令行交互，从disk构造ctx后，用户输入一个命令后跟参数，程序执行并输出结果，命令在cmd adapter下注册

from dataclasses import replace
import logging

from src.app.bootstrap_disk import build_context_from_disk
from src.app.config import load_from_disk

from src.adapters.cmd.app import CommandLineInterface, parse_command_line, run_preflight_command_once
from src.adapters.cmd.web_client import execute_remote_command_once, is_local_service_url, resolve_command_service_url

logger = logging.getLogger(__name__)
LOCAL_CONTEXT_COMMANDS = {"resource-version"}

async def cmd_main(
    command_parts: list[str] | None = None,
    command_service_url: str | None = None,
    verbose: bool = False,
    output_format: str = "markdown",
) -> int:
    """主函数：初始化上下文并启动 CLI。"""
    try:
        cfg = load_from_disk()

        if command_parts:
            builtin_exit_code = await run_preflight_command_once(command_parts)
            if builtin_exit_code is not None:
                return builtin_exit_code

            command, _ = parse_command_line(" ".join(part for part in command_parts if part).strip())
            base_url = resolve_command_service_url(cfg, explicit_url=command_service_url)
            if command in LOCAL_CONTEXT_COMMANDS and is_local_service_url(base_url):
                ctx = await build_context_from_disk(cfg)
                ctx = replace(ctx, output_format=output_format)
                cli = CommandLineInterface(ctx)
                return await cli.run_once(command_parts)

            return await execute_remote_command_once(
                cfg,
                command_parts=command_parts,
                explicit_url=command_service_url,
                verbose=verbose,
                output_format=output_format,
            )

        logger.info("正在初始化应用上下文...")
        ctx = await build_context_from_disk(cfg)
        ctx = replace(ctx, output_format=output_format)
        logger.info("✅ 上下文初始化完成")

        cli = CommandLineInterface(ctx)
        if command_parts:
            return await cli.run_once(command_parts)

        await cli.run()
        return 0

    except Exception as e:
        logger.exception("初始化失败")
        print(f"❌ 初始化失败: {e}")
        return 1

