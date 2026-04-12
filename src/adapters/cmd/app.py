
import logging
from dataclasses import dataclass

from src.app.context import AppContext

from src.adapters.cmd.registery import register_command, command_registry

from src.adapters.cmd.cmd_tools.operator import *

logger = logging.getLogger(__name__)

BUILTIN_COMMANDS = {"help", "exit", "config-path"}


@dataclass(slots=True)
class CommandExecutionResult:
    ok: bool
    output: str = ""

    def to_response(self) -> dict:
        return {
            "ok": self.ok,
            "output": self.output,
        }


def parse_command_line(user_input: str) -> tuple[str, str]:
    parts = user_input.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return command, args


async def run_preflight_command_once(command_parts: list[str]) -> int | None:
    command_line = " ".join(part for part in command_parts if part).strip()
    if not command_line:
        return 0

    command, args = parse_command_line(command_line)
    if command not in command_registry:
        print(f"❌ 未知命令: {command}")
        print("输入 'help' 查看可用命令")
        return 1

    if command not in BUILTIN_COMMANDS:
        return None

    if command == "exit":
        return 0

    handler = command_registry[command]
    result = await handler(None, args)
    if result:
        print(result)
    return 0


async def execute_registered_command(ctx: AppContext | None, command: str, args: str) -> CommandExecutionResult:
    """执行已注册命令，并返回结构化结果。"""
    normalized_command = (command or "").strip().lower()
    if normalized_command not in command_registry:
        return CommandExecutionResult(
            ok=False,
            output=f"❌ 未知命令: {normalized_command}\n输入 'help' 查看可用命令",
        )

    handler = command_registry[normalized_command]
    try:
        result = await handler(ctx, args)
        return CommandExecutionResult(ok=True, output=result or "")
    except Exception as e:
        logger.exception(f"命令执行失败: {normalized_command}")
        return CommandExecutionResult(ok=False, output=f"❌ 命令执行失败: {e}")

class CommandLineInterface:
    """命令行交互界面"""
    
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.running = True

    @staticmethod
    def _parse_user_input(user_input: str) -> tuple[str, str]:
        return parse_command_line(user_input)
    
    async def run(self):
        """主交互循环"""
        print("=" * 60)
        print("🤖 Amiya Bot 命令行模式")
        print("=" * 60)
        print("输入 'help' 查看可用命令，输入 'exit' 退出")
        print()
        
        while self.running:
            try:
                # 读取用户输入
                user_input = input(">> ").strip()
                
                if not user_input:
                    continue

                command, args = self._parse_user_input(user_input)
                
                if command == "exit":
                    print("👋 再见！")
                    self.running = False
                    continue

                # 执行命令
                await self._execute_command(command, args)
                
            except KeyboardInterrupt:
                print("\n\nBye!")
                self.running = False
            except Exception as e:
                logger.exception(f"执行命令时出错: {e}")
                print(f"❌ 错误: {e}")

    async def run_once(self, command_parts: list[str]) -> int:
        """执行单条命令后退出。"""
        command_line = " ".join(part for part in command_parts if part).strip()
        if not command_line:
            return 0

        command, args = self._parse_user_input(command_line)
        if command == "exit":
            return 0

        ok = await self._execute_command(command, args)
        return 0 if ok else 1
    
    async def _execute_command(self, command: str, args: str) -> bool:
        """执行注册的命令"""
        result = await execute_registered_command(self.ctx, command, args)
        if result.output:
            print(result.output)
        return result.ok


# ==================== 内置命令 ====================

@register_command("help")
async def cmd_help(ctx: AppContext, args: str) -> str:
    """显示帮助信息"""
    help_text = "📚 可用命令：\n"
    help_text += "-" * 40 + "\n"
    for cmd_name in sorted(command_registry.keys()):
        help_text += f"  • {cmd_name}\n"
    help_text += "-" * 40
    return help_text


@register_command("exit")
async def cmd_exit(ctx: AppContext, args: str) -> str:
    """退出程序"""
    return ""  # 由CLI处理exit逻辑
