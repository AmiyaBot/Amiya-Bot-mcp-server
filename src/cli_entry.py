import asyncio
from dataclasses import dataclass
import sys

APP_COMMAND_NAME = "amiyabot-cli"
WEB_MODE_COMMAND = "web"


@dataclass(slots=True)
class ParsedArgs:
    mode: str
    command_parts: list[str]
    command_service_url: str | None = None
    verbose: bool = False
    output_format: str = "markdown"
    error: str | None = None


def print_usage() -> None:
    print("用法:")
    print(f"  {APP_COMMAND_NAME} {WEB_MODE_COMMAND}                           # 启动 Web 服务")
    print(f"  {APP_COMMAND_NAME}                              # 进入交互式 CLI")
    print(f"  {APP_COMMAND_NAME} [--verbose] [--json] [--url URL] <command> [args] # 执行单次 CLI 指令")


def parse_args(argv: list[str]) -> ParsedArgs:
    command_service_url = None
    verbose = False
    output_format = "markdown"
    remaining = list(argv)

    while remaining:
        option = remaining[0]
        if option in {"-v", "--verbose"}:
            verbose = True
            remaining.pop(0)
            continue

        if option == "--json":
            output_format = "json"
            remaining.pop(0)
            continue

        if not option.startswith("--url"):
            break

        option = remaining.pop(0)
        if option == "--url":
            if not remaining:
                return ParsedArgs(
                    mode="error",
                    command_parts=[],
                    verbose=verbose,
                    output_format=output_format,
                    error="--url 缺少参数",
                )
            command_service_url = remaining.pop(0)
            continue

        if option.startswith("--url="):
            command_service_url = option.split("=", 1)[1].strip()
            if not command_service_url:
                return ParsedArgs(
                    mode="error",
                    command_parts=[],
                    verbose=verbose,
                    output_format=output_format,
                    error="--url 缺少参数",
                )
            continue

        break

    if not remaining:
        if output_format == "json":
            return ParsedArgs(
                mode="error",
                command_parts=[],
                command_service_url=command_service_url,
                verbose=verbose,
                output_format=output_format,
                error="--json 仅支持单次命令模式",
            )
        return ParsedArgs(
            mode="interactive",
            command_parts=[],
            command_service_url=command_service_url,
            verbose=verbose,
            output_format=output_format,
        )

    if remaining[0] in {"-h", "--help"}:
        return ParsedArgs(
            mode="help",
            command_parts=[],
            command_service_url=command_service_url,
            verbose=verbose,
            output_format=output_format,
        )

    if remaining[0] == WEB_MODE_COMMAND:
        return ParsedArgs(
            mode="web",
            command_parts=remaining[1:],
            command_service_url=command_service_url,
            verbose=verbose,
            output_format=output_format,
        )

    return ParsedArgs(
        mode="command",
        command_parts=remaining,
        command_service_url=command_service_url,
        verbose=verbose,
        output_format=output_format,
    )


def run(argv: list[str] | None = None) -> int:
    parsed_args = parse_args(sys.argv[1:] if argv is None else argv)

    if parsed_args.mode == "error":
        print(f"❌ {parsed_args.error}")
        print_usage()
        return 2

    if parsed_args.mode == "help":
        print_usage()
        return 0

    if parsed_args.mode == "web":
        if parsed_args.output_format != "markdown":
            print(f"❌ {WEB_MODE_COMMAND} 模式不支持 --json")
            print_usage()
            return 2
        if parsed_args.command_service_url:
            print(f"❌ {WEB_MODE_COMMAND} 模式不支持 --url")
            print_usage()
            return 2
        if parsed_args.command_parts:
            print(f"❌ {WEB_MODE_COMMAND} 模式不接受额外参数: {' '.join(parsed_args.command_parts)}")
            print_usage()
            return 2

        from src.entrypoints.uvicorn_host import uvicorn_main

        uvicorn_main()
        return 0

    from src.entrypoints.command_line import cmd_main

    if parsed_args.mode == "interactive":
        return asyncio.run(cmd_main(verbose=parsed_args.verbose, output_format=parsed_args.output_format))

    return asyncio.run(
        cmd_main(
            command_parts=parsed_args.command_parts,
            command_service_url=parsed_args.command_service_url,
            verbose=parsed_args.verbose,
            output_format=parsed_args.output_format,
        )
    )


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())