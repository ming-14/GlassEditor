"""GlassEditor - 应用程序入口

使用 Click 库解析命令行参数，支持通过终端控制编辑器行为，
包括打开文件、跳转到指定行列、指定编码等。
"""
import sys
import os
import codecs
from typing import Optional, Tuple

import click

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _SCRIPT_DIR)

from src.infrastructure.cli_args import ParsedArgs


def _validate_encoding(ctx, param, value):
    """! @brief Click 编码参数校验回调

    通过 codecs.lookup() 验证编码名称是否合法，
    非法编码不中断启动，而是返回 None 由主流程回退到自动检测。

    @param ctx   Click 上下文
    @param param Click 参数对象
    @param value 用户传入的编码名称
    @return 合法的编码名称字符串，或 None
    """
    if value is None:
        return None
    try:
        codecs.lookup(value)
        return value
    except LookupError:
        click.echo(f"警告: 未知编码 '{value}'，将使用自动检测", err=True)
        return None


def _parse_goto(ctx, param, value) -> Optional[Tuple[int, Optional[int]]]:
    """! @brief Click --goto 参数解析回调

    将 "行号" 或 "行号:列号" 格式拆分为 (line, column) 元组。
    格式非法时抛出 Click 异常。

    @param ctx   Click 上下文
    @param param Click 参数对象
    @param value 用户传入的 goto 字符串
    @return (行号, 列号) 元组，列号可能为 None；或 None
    """
    if value is None:
        return None
    try:
        parts = value.split(":", 1)
        line = int(parts[0])
        col = int(parts[1]) if len(parts) > 1 else None
        if line < 1:
            click.echo("警告: 行号不能小于1，已调整为1", err=True)
            line = 1
        if col is not None and col < 1:
            click.echo("警告: 列号不能小于1，已调整为1", err=True)
            col = 1
        return (line, col)
    except (ValueError, IndexError):
        raise click.BadParameter(
            f"无效的位置格式 '{value}'，应为 '行号' 或 '行号:列号'"
        )


@click.command(
    context_settings=dict(
        help_option_names=["-h", "--help"],
        ignore_unknown_options=True,
        allow_extra_args=True,
    )
)
@click.version_option(version="1.0.0", prog_name="琉璃编辑器", message="%(prog)s %(version)s")
@click.option("-l", "--line", type=int, default=None, help="打开文件后跳转到第 N 行")
@click.option("-c", "--column", type=int, default=None, help="跳转到第 C 列（需与 --line 配合使用）")
@click.option("-g", "--goto", default=None, callback=_parse_goto,
              help="跳转到指定位置，格式为 行号 或 行号:列号")
@click.option("-e", "--encoding", default=None, callback=_validate_encoding,
              help="指定打开文件时的编码（如 utf-8, gbk）")
@click.option("--no-tray", is_flag=True, default=False,
              help="禁止系统托盘图标")
@click.option("--minimized", is_flag=True, default=False,
              help="启动时最小化到系统托盘")
@click.argument("files", nargs=-1, type=click.Path())
def cli(line, column, goto, encoding, no_tray, minimized, files):
    """! @brief 琉璃编辑器命令行入口

    Click 装饰的命令行解析函数，负责解析所有命令行参数
    并构建 ParsedArgs 对象传递给主窗口。

    多个文件依次打开，跳转参数仅作用于第一个文件。
    """
    # --goto 优先于 --line / --column
    if goto is not None:
        line = goto[0]
        column = goto[1]
    elif line is not None and line < 1:
        line = 1

    # 规范化文件路径：展开 ~ 并转为绝对路径
    normalized_files = []
    for f in files:
        path = os.path.abspath(os.path.expanduser(f))
        normalized_files.append(path)

    args = ParsedArgs(
        files=normalized_files,
        line=line,
        column=column,
        encoding=encoding,
        no_tray=no_tray,
        minimized=minimized,
    )

    # 启动 GUI 主窗口，传入解析结果
    _launch_main_window(args)


def _launch_main_window(args: ParsedArgs):
    """! @brief 启动主窗口

    初始化 QApplication 并创建 MainWindow，将命令行解析结果
    传递给主窗口以执行文件打开和光标跳转。
    集成单实例守护：已有实例时通过 IPC 委托操作后退出。

    @param args 解析后的命令行参数
    """
    from PyQt5.QtCore import qInstallMessageHandler, QtMsgType, QTimer
    from PyQt5.QtWidgets import QApplication
    from qfluentwidgets import setTheme, Theme
    from src.infrastructure.logger import start_logger, stop_logger, get_logger

    app = QApplication(sys.argv)
    app.setApplicationName("GlassEditor")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("GlassEditor")

    def _qt_message_handler(msg_type: QtMsgType, context, msg: str) -> None:
        """! @brief 自定义 Qt 消息处理，静默过滤不支持的 CSS 属性警告"""
        if "Unknown property" in msg:
            return

    qInstallMessageHandler(_qt_message_handler)

    setTheme(Theme.DARK)

    start_logger()
    logger = get_logger("Main")
    logger.info("GlassEditor starting...")
    logger.info(f"CLI args: files={args.files}, line={args.line}, "
                f"column={args.column}, encoding={args.encoding}, "
                f"no_tray={args.no_tray}, minimized={args.minimized}")

    from src.infrastructure.single_instance import SingleInstanceGuard
    from src.infrastructure.app_constants import AppConstant

    guard = SingleInstanceGuard(AppConstant.IPC_SERVER_NAME)

    if not guard.try_lock():
        logger.info("检测到已有实例运行, 通过 IPC 委托操作")

        message = {
            "action": "open_files",
            "files": args.files,
            "line": args.line,
            "column": args.column,
        }
        success = guard.send_message(message)

        if not success:
            from PyQt5.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                None, "通信失败",
                "无法连接到已运行的编辑器实例。\n"
                "是否仍然启动新实例？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                guard.release()
                stop_logger()
                sys.exit(1)
            logger.warning("IPC 通信失败, 以降级模式启动新实例")
        else:
            guard.release()
            stop_logger()
            sys.exit(0)

    logger.info("单实例锁定成功, 本进程为主实例")

    from src.ui.main_window import MainWindow
    window = MainWindow(
        cli_args=args,
        single_instance_guard=guard,
    )

    start_minimized = window.is_start_minimized_to_tray()

    if not start_minimized:
        window.show()
    else:
        window.show()
        QTimer.singleShot(0, window.hide)

    logger.info("GlassEditor started")

    exit_code = app.exec_()

    if window._tray_icon is not None:
        window._tray_icon.hide()
    guard.release()
    stop_logger()
    sys.exit(exit_code)


def main():
    """! @brief 应用程序入口

    Click 的 cli() 函数替代了原先的 main() 作为入口点，
    负责解析命令行参数并启动 GUI。
    """
    cli()


if __name__ == "__main__":
    main()
