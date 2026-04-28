"""允许通过 `python -m corebot` 直接运行 CLI。"""

from corebot.cli import app


if __name__ == "__main__":
    # 直接调用 Typer 应用对象，进入命令行分发逻辑。
    app()
