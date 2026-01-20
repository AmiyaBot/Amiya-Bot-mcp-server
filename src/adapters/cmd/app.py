
import logging

from src.app.context import AppContext

from src.adapters.cmd.registery import register_command, command_registry

from src.adapters.cmd.cmd_tools.operator import *

logger = logging.getLogger(__name__)

class CommandLineInterface:
    """命令行交互界面"""
    
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.running = True
    
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
                
                # 解析命令和参数
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
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
    
    async def _execute_command(self, command: str, args: str):
        """执行注册的命令"""
        if command not in command_registry:
            print(f"❌ 未知命令: {command}")
            print("输入 'help' 查看可用命令")
            return
        
        handler = command_registry[command]
        try:
            result = await handler(self.ctx, args)
            if result:
                print(result)
        except Exception as e:
            logger.exception(f"命令执行失败: {command}")
            print(f"❌ 命令执行失败: {e}")


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
