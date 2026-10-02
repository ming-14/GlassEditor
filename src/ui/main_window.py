"""! @brief 琉璃编辑器主窗口模块

主窗口作为编排器(Orchestrator)，组合已提取的子组件：
WelcomePage、MenuBarManager、SearchResultPanel、SplitViewManager、
syntax_helper，负责创建子组件实例、连接信号与槽、
处理核心事件逻辑（文件操作、编辑操作、会话管理等）。
"""

import os
from typing import Dict, Optional

from PyQt5.QtCore import Qt, pyqtSlot, QEvent, QTimer
from PyQt5.QtGui import QFontMetrics, QTextCursor, QTextCharFormat
from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout,
    QApplication, QSplitter,
    QFileDialog,
)

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, PushButton, RoundMenu,
    CommandBar, Action, FluentIcon, MessageBox,
)

from src.infrastructure.logger import get_logger
from src.infrastructure.config_keys import ConfigKey
from src.infrastructure.encoding_utils import get_display_name, get_status_bar_encoding

from src.ui.editor_tab_widget import EditorTabWidget
from src.ui.code_editor import CodeEditor, set_colors_provider
from src.ui.syntax_highlighter import create_highlighter, set_syntax_colors_provider
from src.ui.search_bar import SearchBar
from src.ui.status_bar import StatusBar
from src.ui.welcome_page import WelcomePage
from src.ui.menu_manager import MenuBarManager
from src.ui.search_result_panel import SearchResultPanel
from src.ui.split_view_manager import SplitViewManager
from src.ui.system_tray_icon import SystemTrayIcon
from src.ui.settings_page import SettingsPage

from src.controller.action_manager import ActionManager
from src.controller.tab_manager import TabManager
from src.controller.signal_bus import SignalBus
from src.controller.focus_manager import FocusManager

from src.service.file_service import FileService
from src.service.theme_service import ThemeService
from src.service.config_service import ConfigService
from src.service.tool_service import ToolService
from src.service.search_service import SearchService
from src.service.syntax_highlighter_manager import SyntaxHighlighterManager

from src.infrastructure.cli_args import ParsedArgs
from src.infrastructure.app_constants import AppConstant


class MainWindow(FluentWindow):
    """! @brief 琉璃编辑器主窗口类（编排器）

    基于PyQt5和PyQt-Fluent-Widgets的FluentWindow构建的主窗口，
    作为编排器组合子组件（WelcomePage、MenuBarManager、
    SearchResultPanel、SplitViewManager），负责信号连接与核心事件处理。
    """

    MIN_WIDTH = AppConstant.MIN_WINDOW_WIDTH
    MIN_HEIGHT = AppConstant.MIN_WINDOW_HEIGHT

    def __init__(self, cli_args: 'ParsedArgs' = None,
                 single_instance_guard=None):
        """! @brief 主窗口构造函数

        初始化所有服务、控制器、子组件，并恢复上次会话状态。
        若传入命令行参数，则在会话恢复后处理文件打开和光标跳转。

        @param cli_args 命令行解析结果，默认为 None（无参数启动）
        @param single_instance_guard 单实例守护，默认为 None
        """
        super().__init__()
        self.setAcceptDrops(True)

        self._split_view_manager = None
        self._menu_manager = None
        self._search_result_panel = None

        self._logger = get_logger("MainWindow")
        self._logger.info("MainWindow init")

        self._cli_args = cli_args or ParsedArgs()

        self._signal_bus = SignalBus()

        self._config_service = ConfigService(signal_bus=self._signal_bus, parent=self)
        self._theme_service = ThemeService(signal_bus=self._signal_bus, parent=self)

        set_colors_provider(self._get_editor_colors_from_theme_service)
        set_syntax_colors_provider(self._get_syntax_colors_from_theme_service)

        self._file_service = FileService(signal_bus=self._signal_bus, parent=self)
        self._search_service = SearchService()
        self._highlighter_manager = SyntaxHighlighterManager(
            config_service=self._config_service,
            highlighter_factory=create_highlighter,
        )

        self.init_ui()

        self._tab_manager = TabManager(
            tab_widget=self._tab_widget,
            file_service=self._file_service,
            editor_factory=CodeEditor,
            highlighter_manager=self._highlighter_manager,
            signal_bus=self._signal_bus,
            parent=self,
        )
        self._tab_manager.set_config_service(self._config_service)

        self._focus_manager = FocusManager(
            tab_manager=self._tab_manager, parent=self
        )

        self._action_manager = ActionManager(
            main_window=self,
            file_service=self._file_service,
            theme_service=self._theme_service,
            config_service=self._config_service,
            tab_manager=self._tab_manager,
            focus_manager=self._focus_manager,
            search_service=self._search_service,
            parent=self,
        )
        self._action_manager.register_actions()

        self._settings_interface = SettingsPage(
            config_service=self._config_service,
            shortcut_registry=self._action_manager._shortcut_registry,
        )
        self.addSubInterface(
            self._settings_interface,
            FluentIcon.SETTING,
            "设置",
            NavigationItemPosition.BOTTOM,
            isTransparent=True,
        )

        self._split_view_manager = SplitViewManager(
            tab_manager=self._tab_manager,
            signal_bus=self._signal_bus,
            focus_manager=self._focus_manager,
            tab_widget=self._tab_widget,
            main_splitter=self._main_splitter,
            splitter=self._splitter,
            on_editor_ready=self._on_split_editor_ready,
        )

        self._search_result_panel = SearchResultPanel(
            tab_manager=self._tab_manager,
            signal_bus=self._signal_bus,
        )
        self._search_result_panel.set_tab_widget_ref(self._tab_widget)
        self._splitter.addWidget(self._search_result_panel)
        self._search_result_panel.hide()

        self._menu_manager = MenuBarManager(
            action_manager=self._action_manager,
            tab_manager=self._tab_manager,
            file_service=self._file_service,
            theme_service=self._theme_service,
            config_service=self._config_service,
            signal_bus=self._signal_bus,
            status_bar_widget=self._status_bar_widget,
            parent=self,
        )
        self._menu_manager.set_tab_widget_ref(self._tab_widget)
        self._menu_bar_widget = self._menu_manager.create_menu_bar(self._editor_interface)
        editor_layout = self._editor_interface.layout()
        editor_layout.insertWidget(0, self._menu_bar_widget)

        self._populate_menus_and_toolbar()
        self.connect_signals()
        self._load_config_and_theme()
        self._restore_session()
        self._process_cli_args()

        if self._config_service.get(ConfigKey.FIRST_RUN, True):
            self._config_service.set(ConfigKey.FIRST_RUN, False)

        self._single_instance_guard = single_instance_guard
        self._tray_icon = None
        self._setup_tray()

        if self._single_instance_guard is not None:
            self._single_instance_guard.message_received.connect(
                self._on_instance_message
            )

        self._logger.info("MainWindow init complete")

    # ========================================================================
    # 窗口关闭
    # ========================================================================

    def closeEvent(self, event) -> None:
        """! @brief 窗口关闭事件处理

        根据 CLOSE_TO_TRAY 配置决定行为：
        - 若开启关闭到托盘且托盘可用：隐藏窗口到系统托盘
        - 否则：走正常退出流程（含未保存检查和确认对话框）

        @param event QCloseEvent 对象
        """
        close_to_tray = self._config_service.get(ConfigKey.CLOSE_TO_TRAY, False)

        if close_to_tray and self._tray_icon is not None:
            self._logger.info("关闭到系统托盘模式触发")
            unsaved = self._tab_manager.get_unsaved_tabs()
            unsaved = [u for u in unsaved
                       if not self._is_empty_new_file(u["index"])]

            if unsaved:
                choice = self._confirm_close_unsaved_all_tabs(unsaved)
                if choice == "cancel":
                    event.ignore()
                    return
                elif choice == "save":
                    for tab in unsaved:
                        idx = tab["index"]
                        self._tab_manager.switch_to_tab(idx)
                        self._action_manager.save_current_file()
                        if self._tab_manager.is_tab_modified(idx):
                            self._logger.warning(
                                f"保存失败, 中止隐藏: [{idx}]"
                            )
                            event.ignore()
                            return

            self._save_full_session()
            self._signal_bus.app_minimize_to_tray.emit()
            self.hide()
            event.ignore()

            self._logger.info("已最小化到系统托盘")
        else:
            self._logger.info("MainWindow 关闭事件触发")
            unsaved = self._tab_manager.get_unsaved_tabs()
            unsaved = [u for u in unsaved if not self._is_empty_new_file(u["index"])]

            if unsaved:
                names: list[str] = []
                for tab in unsaved[:10]:
                    fp = tab.get("file_path")
                    names.append(os.path.basename(fp) if fp else "未命名")
                more = f"\n... 等共 {len(unsaved)} 个文件" if len(unsaved) > 10 else ""

                msg = MessageBox(
                    "未保存的更改",
                    f"以下 {len(unsaved)} 个文件有未保存的更改：\n\n"
                    + "\n".join(f"  - {n}" for n in names)
                    + f"{more}\n\n是否保存后再退出？",
                    self,
                )
                msg.yesButton.setText("保存")
                msg.cancelButton.setText("不保存")

                cancelBtn = PushButton("取消")
                cancelBtn.setMinimumWidth(80)
                msg.yesButton.setMinimumWidth(80)
                msg.cancelButton.setMinimumWidth(80)
                msg.buttonLayout.addWidget(cancelBtn)
                cancelBtn.clicked.connect(msg.reject)

                choice = self._exec_tristate_dialog(msg, 'save', 'discard')

                if choice == 'save':
                    for tab in unsaved:
                        idx = tab["index"]
                        self._tab_manager.switch_to_tab(idx)
                        self._action_manager.save_current_file()
                        if self._tab_manager.is_tab_modified(idx):
                            self._logger.warning(f"保存失败或取消，中止关闭: [{idx}]")
                            event.ignore()
                            return
                    self._save_full_session()
                    event.accept()
                    self._logger.info("MainWindow 关闭（已保存）")
                elif choice == 'discard':
                    self._save_full_session()
                    event.accept()
                    self._logger.info("MainWindow 关闭（放弃修改）")
                else:
                    event.ignore()
                    self._logger.info("MainWindow 关闭已取消")
            else:
                confirm = MessageBox(
                    "确认退出",
                    "确定要退出编辑器吗？",
                    self,
                )
                confirm.yesButton.setText("退出")
                confirm.cancelButton.setText("取消")
                choice = self._exec_tristate_dialog(confirm, 'quit', None)

                if choice == 'quit':
                    self._save_full_session()
                    event.accept()
                    self._logger.info("MainWindow 关闭")
                else:
                    event.ignore()
                    self._logger.info("MainWindow 关闭已取消")

    def _save_full_session(self) -> None:
        """! @brief 保存完整会话快照

        委托给 TabManager.save_full_session() 执行，
        避免与 TabManager._do_auto_save_session() 的逻辑重复。
        """
        self._tab_manager.save_full_session()

    @staticmethod
    def _exec_tristate_dialog(dialog, yes_choice: str, cancel_choice: str) -> str:
        """! @brief 执行三选一对话框并返回用户选择

        替代 setattr+lambda 的 hack 模式，用正规的实例变量记录选择。

        @param dialog       MessageBox 对话框实例
        @param yes_choice   点击"是"按钮时返回的标识
        @param cancel_choice 点击"取消"按钮时返回的标识（可为 None）
        @return 用户选择的标识字符串，或 None 表示对话框被拒绝
        """
        result = [None]
        dialog.yesSignal.connect(lambda: result.__setitem__(0, yes_choice))
        if cancel_choice is not None:
            dialog.cancelSignal.connect(lambda: result.__setitem__(0, cancel_choice))
        dialog.exec()
        return result[0]

    # ========================================================================
    # 系统托盘
    # ========================================================================

    def _setup_tray(self):
        """! @brief 创建系统托盘图标

        若系统支持托盘且未通过 CLI 禁用则创建并显示，否则跳过。
        """
        if self._cli_args and self._cli_args.no_tray:
            self._logger.info("CLI --no-tray 已指定，跳过托盘图标创建")
            return

        if not SystemTrayIcon.is_tray_available():
            self._logger.warning("系统托盘不可用，跳过托盘图标创建")
            return

        try:
            self._tray_icon = SystemTrayIcon(self)
            self._tray_icon.show_window_requested.connect(self._bring_to_front)
            self._tray_icon.new_file_requested.connect(
                self._action_manager.new_file
            )
            self._tray_icon.open_file_requested.connect(
                self._action_manager.open_file
            )
            self._tray_icon.quit_requested.connect(self._on_tray_quit)
            self._signal_bus.tray_icon_activated.connect(self._bring_to_front)
            self._tray_icon.show()
            self._logger.info("系统托盘图标已创建")
        except Exception as e:
            self._logger.error(f"系统托盘初始化失败: {e}")
            self._tray_icon = None

    def _bring_to_front(self):
        """! @brief 将窗口恢复并聚焦到前台

        若窗口处于隐藏或最小化状态则恢复显示，
        然后置顶并激活窗口。
        """
        try:
            if self.isHidden():
                self.show()
            if self.isMinimized():
                self.showNormal()
            self.raise_()
            self.activateWindow()
            self._logger.debug("窗口已恢复到前台")
        except Exception as e:
            self._logger.error(f"窗口恢复前台失败: {e}")

    def _handle_ipc_activation(self):
        """! @brief 处理来自第二实例的窗口激活请求

        根据主实例当前窗口状态决定行为：
        - 最小化状态 → 闪烁任务栏提醒用户
        - 隐藏（托盘后台）或前台状态 → 恢复/置顶窗口并获取焦点
        """
        try:
            if self.isMinimized():
                QApplication.alert(self, 0)
                self._logger.debug("IPC 激活: 窗口已最小化, 闪烁任务栏")
            else:
                if self.isHidden():
                    self.show()
                self.raise_()
                self.activateWindow()
                self._logger.debug("IPC 激活: 窗口已恢复到前台")
        except Exception as e:
            self._logger.error(f"IPC 激活窗口异常: {e}")

    def _on_tray_quit(self):
        """! @brief 从托盘菜单退出

        走完整退出流程，包括未保存检查。
        """
        self._logger.info("从系统托盘触发退出")
        self._save_full_session()
        self.close()

    def _confirm_close_unsaved_all_tabs(self, unsaved: list) -> str:
        """! @brief 对一批未保存标签弹出三选一对话框

        @param unsaved 未保存标签元数据列表
        @return 'save' / 'discard' / 'cancel' / None
        """
        if not unsaved:
            return "discard"

        names = []
        for tab in unsaved:
            fp = tab.get("file_path")
            names.append(os.path.basename(fp) if fp else "未命名")

        more = (f"\n... 等共 {len(unsaved)} 个文件"
                if len(unsaved) > 10 else "")

        msg = MessageBox(
            "未保存的更改",
            f"以下 {len(unsaved)} 个文件有未保存的更改：\n\n"
            + "\n".join(f"  - {n}" for n in names[:10])
            + f"{more}\n\n关闭窗口后将最小化到系统托盘，是否保存？",
            self,
        )
        msg.yesButton.setText("全部保存")
        msg.cancelButton.setText("不保存")

        cancel_btn = PushButton("取消")
        cancel_btn.setMinimumWidth(80)
        msg.yesButton.setMinimumWidth(80)
        msg.cancelButton.setMinimumWidth(80)
        msg.buttonLayout.addWidget(cancel_btn)
        cancel_btn.clicked.connect(msg.reject)

        return self._exec_tristate_dialog(msg, "save", "discard")

    # ========================================================================
    # IPC 消息处理
    # ========================================================================

    @pyqtSlot(dict)
    def _on_instance_message(self, message: dict):
        """! @brief 处理来自第二实例的 IPC 消息

        @param message 消息字典，包含 action 字段
        """
        try:
            action = message.get("action", "")
            self._logger.info(f"接收到 IPC 消息: {action}")

            if action == "open_files":
                files = message.get("files", [])
                line = message.get("line")
                column = message.get("column")

                ipc_args = ParsedArgs(
                    files=files, line=line, column=column,
                )
                self._handle_external_files(ipc_args)
                self._handle_ipc_activation()

            elif action == "bring_to_front":
                self._handle_ipc_activation()

            else:
                self._logger.warning(f"未知 IPC 动作: {action}")
        except Exception as e:
            self._logger.error(f"IPC 消息处理异常: {e}")

    def _handle_external_files(self, args: "ParsedArgs"):
        """! @brief 处理外部传入的文件打开请求（CLI 或 IPC）

        @param args 命令行参数（或 IPC 参数）
        """
        if not args.files:
            return

        self._logger.info(
            f"处理外部文件: {len(args.files)} 个, "
            f"line={args.line}, column={args.column}"
        )

        if self._tab_manager.tab_count() == 1:
            editor = self._tab_manager.get_editor(0)
            file_path = self._tab_manager.get_file_path(0)
            if editor and file_path is None and not editor.document().isModified():
                self._tab_manager.close_tab(0)

        first_tab_index = -1
        for i, file_path in enumerate(args.files):
            if os.path.exists(file_path):
                content, encoding, _, err = self._file_service.open_file(
                    file_path, encoding=args.encoding,
                )
                if err:
                    self._logger.warning(
                        f"外部文件打开失败: {file_path}, error={err}"
                    )
                    self._signal_bus.status_message.emit(
                        f"打开失败: {os.path.basename(file_path)}",
                        AppConstant.STATUS_MESSAGE_DURATION_MS,
                    )
                    continue
                use_encoding = args.encoding if args.encoding else encoding
                index = self._tab_manager.create_tab(
                    file_path=file_path, content=content,
                    encoding=use_encoding,
                )
            else:
                self._logger.info(
                    f"外部文件不存在, 创建未保存标签: {file_path}"
                )
                index = self._tab_manager.create_tab(
                    file_path=None, content="",
                    encoding=args.encoding or "utf-8",
                )

            if i == 0:
                first_tab_index = index

        if first_tab_index >= 0 and (
            args.line is not None or args.column is not None
        ):
            self._apply_cursor_position(
                first_tab_index,
                args.line if args.line is not None else 1,
                args.column if args.column is not None else 1,
            )

        if first_tab_index >= 0:
            self._tab_manager.switch_to_tab(first_tab_index)

    def is_start_minimized_to_tray(self) -> bool:
        """! @brief 判断启动时是否需要隐藏主窗口

        供 main.py 调用，结合 CLI 参数和配置决定。

        @return True 表示启动时应最小化到托盘
        """
        if self._cli_args and self._cli_args.minimized:
            return True
        return self._config_service.get(
            ConfigKey.START_MINIMIZED_TO_TRAY, False
        )

    # ========================================================================
    # UI初始化
    # ========================================================================

    def _get_editor_colors_from_theme_service(self) -> Dict:
        """! @brief 编辑器配色提供者回调

        供 CodeEditor 模块通过 set_colors_provider 注入后调用，
        避免 UI 层直接 import ThemeService。

        @return 当前主题的编辑器配色字典
        """
        theme_name = self._theme_service.get_current_theme()
        return self._theme_service.get_editor_colors(theme_name)

    def _get_syntax_colors_from_theme_service(self) -> Dict:
        """! @brief 语法配色提供者回调

        供 syntax_highlighter 模块通过 set_syntax_colors_provider 注入后调用，
        避免 UI 层直接 import ThemeService。

        @return 当前主题的语法高亮配色字典
        """
        theme_name = self._theme_service.get_current_theme()
        theme = self._theme_service.get_theme(theme_name)
        syntax_colors = {}
        for k, v in theme.items():
            if k.startswith("syntax_"):
                syntax_colors[k[7:]] = v
        return syntax_colors

    def init_ui(self) -> None:
        """! @brief 初始化所有UI组件

        按顺序创建命令栏、编辑器子界面、搜索栏。
        菜单栏、欢迎页、搜索结果面板等子组件在 __init__ 中延迟创建。
        FluentWindow自带标题栏和导航面板，无需手动创建。
        """
        self.setWindowTitle("琉璃编辑器")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(AppConstant.DEFAULT_WINDOW_WIDTH, AppConstant.DEFAULT_WINDOW_HEIGHT)

        self.init_command_bar()
        self.init_editor_interface()
        self.init_search_bar()

    def init_editor_interface(self) -> None:
        """! @brief 初始化编辑器子界面

        创建编辑器子界面容器，包含命令栏、
        标签栏（贯穿全宽）、内容区域（splitter）、搜索栏和状态栏，
        并将其注册为FluentWindow的子界面。
        菜单栏在 __init__ 中由 MenuBarManager 创建后插入布局顶部。
        """
        self._editor_interface = QWidget(self)
        self._editor_interface.setObjectName("editorInterface")
        layout = QVBoxLayout(self._editor_interface)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._command_bar)

        self._tab_widget = EditorTabWidget(self._editor_interface)
        self._tab_widget.setAccessibleName("标签栏")

        self._welcome_page = WelcomePage(self._tab_widget)
        self._welcome_page.hide()

        self._tab_widget.vBoxLayout.removeWidget(self._tab_widget.tabBar)
        self._tab_widget.tabBar.setParent(self._editor_interface)
        layout.addWidget(self._tab_widget.tabBar)
        self._tab_widget.vBoxLayout.setContentsMargins(0, 0, 0, 0)

        self._tab_widget.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._tab_widget.hide()

        self._main_splitter = QSplitter(Qt.Vertical, self._editor_interface)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.setHandleWidth(1)

        self._splitter = QSplitter(Qt.Horizontal, self._main_splitter)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(1)

        self._splitter.addWidget(self._tab_widget.stackedWidget)
        self._main_splitter.addWidget(self._splitter)

        layout.addWidget(self._main_splitter, 1)

        self._search_bar = SearchBar(self._editor_interface)
        self._search_bar.setAccessibleName("查找栏")
        self._search_bar.setVisible(False)
        layout.addWidget(self._search_bar)

        self._status_bar_widget = StatusBar(self._editor_interface)
        self._status_bar_widget.setAccessibleName("状态栏")
        layout.addWidget(self._status_bar_widget)

        self.addSubInterface(
            self._editor_interface,
            FluentIcon.DOCUMENT,
            "编辑器",
            NavigationItemPosition.TOP,
            isTransparent=True,
        )

    # ========================================================================
    # 欢迎页委托方法
    # ========================================================================

    def _show_welcome_page(self) -> None:
        """! @brief 切换到欢迎页标签

        若欢迎页标签不存在则重新创建并插入到索引 0；
        若已存在则直接切换。
        更新主题按钮样式以匹配当前主题。
        """
        theme = self._theme_service.get_current_theme()
        self._welcome_page.update_theme_buttons(theme)
        if self._welcome_tab_exists():
            self._tab_widget.switch_to_welcome()
        else:
            self._tab_widget.add_welcome_tab(self._welcome_page)
            self._tab_widget.setCurrentIndex(0)

    def _welcome_tab_exists(self) -> bool:
        """! @brief 检查当前是否存在欢迎页标签

        @return True 表示欢迎页标签存在
        """
        for i in range(self._tab_widget.count()):
            if self._tab_widget.is_welcome_tab(i):
                return True
        return False

    def _hide_welcome_page(self) -> None:
        """! @brief 切换到第一个文件标签页

        若欢迎页标签不存在，文件标签从索引 0 开始；
        若存在，文件标签从索引 1 开始。
        """
        count = self._tab_manager.tab_count()
        if count > 0:
            target = 1 if self._welcome_tab_exists() else 0
            self._tab_widget.setCurrentIndex(target)

    def _update_welcome_visibility(self) -> None:
        """! @brief 根据文件标签数量更新欢迎页切换

        无文件标签时切换到欢迎页，有文件标签时切换到第一个文件标签。
        """
        if self._tab_manager.tab_count() == 0:
            self._show_welcome_page()
        else:
            self._hide_welcome_page()

    # ========================================================================
    # 菜单与命令栏
    # ========================================================================

    def _populate_menus_and_toolbar(self) -> None:
        """! @brief 填充菜单项和命令栏

        委托 MenuBarManager 连接菜单信号，
        并向命令栏添加动作。
        """
        self._menu_manager.connect_menu_signals()
        self._add_command_bar_actions()

    def init_command_bar(self) -> None:
        """! @brief 初始化Fluent风格命令栏

        使用qfluentwidgets.CommandBar替代QToolBar，提供Fluent Design风格的工具栏。
        """
        self._command_bar = CommandBar(self)
        self._command_bar.setAccessibleName("工具栏")

    def _add_command_bar_actions(self) -> None:
        """! @brief 向命令栏添加动作

        使用FluentIcon为各动作配置图标，按功能分组并添加分隔符。
        为每个按钮设置包含快捷键的悬停提示，提升操作效率。
        """
        am = self._action_manager

        icon_map = {
            "new_file": FluentIcon.ADD,
            "open_file": FluentIcon.FOLDER,
            "save_file": FluentIcon.SAVE,
            "save_as": FluentIcon.SAVE_AS,
            "undo": FluentIcon.RETURN,
            "redo": FluentIcon.CANCEL,
            "cut": FluentIcon.CUT,
            "copy": FluentIcon.COPY,
            "paste": FluentIcon.PASTE,
            "find": FluentIcon.SEARCH,
            "replace": FluentIcon.SEARCH_MIRROR,
            "zoom_in": FluentIcon.ZOOM_IN,
            "zoom_out": FluentIcon.ZOOM_OUT,
            "show_settings": FluentIcon.SETTING,
            "fullscreen": FluentIcon.FULL_SCREEN,
        }

        tooltip_map = {
            "new_file": "新建文件 (Ctrl+N)",
            "open_file": "打开文件 (Ctrl+O)",
            "save_file": "保存 (Ctrl+S)",
            "save_as": "另存为 (Ctrl+Shift+S)",
            "undo": "撤销 (Ctrl+Z)",
            "redo": "重做 (Ctrl+Y)",
            "cut": "剪切 (Ctrl+X)",
            "copy": "复制 (Ctrl+C)",
            "paste": "粘贴 (Ctrl+V)",
            "find": "查找 (Ctrl+F)",
            "replace": "查找替换 (Ctrl+H)",
            "zoom_in": "放大 (Ctrl+=)",
            "zoom_out": "缩小 (Ctrl+-)",
            "fullscreen": "全屏 (F11)",
            "show_settings": "偏好设置 (Ctrl+,)",
        }

        command_actions = [
            "new_file", "open_file", "save_file", "save_as",
            None, "undo", "redo", None,
            "cut", "copy", "paste", None,
            "find", "replace", None,
            "zoom_in", "zoom_out", None,
            "fullscreen", None, "show_settings",
            None, "show_theme_menu",
        ]

        for action_id in command_actions:
            if action_id is None:
                self._command_bar.addSeparator()
            elif action_id == "show_theme_menu":
                self._theme_action = Action(FluentIcon.CONSTRACT, "主题", self)
                self._theme_action.setToolTip("切换主题")  # type: ignore[attr-defined]
                self._theme_action.triggered.connect(self._on_theme_toolbar_clicked)
                self._command_bar.addAction(self._theme_action)
            else:
                action = am.get_action(action_id)
                if action:
                    if action_id in icon_map:
                        action.setIcon(icon_map[action_id])
                    if action_id in tooltip_map:
                        action.setToolTip(tooltip_map[action_id])  # type: ignore[attr-defined]
                    self._command_bar.addAction(action)

    # ========================================================================
    # 搜索栏
    # ========================================================================

    def init_search_bar(self) -> None:
        """! @brief 初始化搜索栏

        搜索栏已在init_editor_interface中创建并添加到布局，
        此处保留方法签名以维持初始化流程一致性。
        """
        pass

    # ========================================================================
    # 信号连接
    # ========================================================================

    def connect_signals(self) -> None:
        """! @brief 连接所有信号与槽

        包括标签页管理、文件操作、主题切换、搜索等信号，
        以及子组件（WelcomePage、MenuBarManager、SearchResultPanel）的信号。
        """
        self._tab_manager.tab_switched.connect(self._on_tab_changed)
        self._tab_manager.tab_closed.connect(self._on_tab_closed_update)
        self._tab_manager.tab_created.connect(self._on_tab_created_bind_signals)
        self._tab_widget.tab_changed.connect(self._on_tab_changed)
        self._tab_widget.tab_close_requested.connect(self._on_tab_close_requested)
        self._tab_widget.new_tab_requested.connect(self._on_new_tab_requested)

        self._signal_bus.file_opened.connect(self._on_file_opened)
        self._signal_bus.file_saved.connect(self._on_file_saved)
        self._signal_bus.file_closed.connect(self._on_file_closed)
        self._signal_bus.file_encoding_changed.connect(self._on_file_encoding_changed)
        self._signal_bus.theme_changed.connect(self._on_theme_changed_apply)
        self._signal_bus.status_message.connect(self._on_status_message)
        self._signal_bus.search_requested.connect(self._on_search_requested)
        self._signal_bus.config_updated.connect(self._on_config_updated)

        self._status_bar_widget.encoding_changed.connect(self._on_encoding_changed)
        self._status_bar_widget.line_ending_changed.connect(self._on_line_ending_changed)
        self._status_bar_widget.language_changed.connect(self._on_language_changed)

        self._tab_manager.file_externally_modified.connect(self._on_file_externally_modified)

        self._search_bar.search_requested.connect(self._on_search_execute)
        self._search_bar.search_next.connect(self._on_search_next)
        self._search_bar.search_prev.connect(self._on_search_prev)
        self._search_bar.search_closed.connect(self._on_search_closed)

        split_v_action = self._action_manager.get_action("split_vertical")
        if split_v_action:
            split_v_action.triggered.connect(self._on_split_vertical)
        split_h_action = self._action_manager.get_action("split_horizontal")
        if split_h_action:
            split_h_action.triggered.connect(self._on_split_horizontal)

        self._welcome_page.theme_changed_requested.connect(self._on_theme_change)
        self._welcome_page.new_file_requested.connect(self._on_new_tab_requested)
        self._welcome_page.open_file_requested.connect(
            lambda: self._action_manager.open_file()
        )

        self._menu_manager.open_recent_file_requested.connect(self._on_open_recent_file)
        self._menu_manager.remove_recent_file_requested.connect(self._on_remove_recent_file)
        self._menu_manager.clear_recent_files_requested.connect(self._on_clear_recent_files)
        self._menu_manager.encoding_changed_requested.connect(self._on_encoding_changed)
        self._menu_manager.theme_change_requested.connect(self._on_theme_change)
        self._menu_manager.print_requested.connect(self._on_print)
        self._menu_manager.sort_dedup_requested.connect(self._on_sort_dedup)
        self._menu_manager.delete_requested.connect(self._on_delete)
        self._menu_manager.delete_line_requested.connect(self._on_delete_line)
        self._menu_manager.duplicate_line_requested.connect(self._on_duplicate_line)
        self._menu_manager.move_line_up_requested.connect(self._on_move_line_up)
        self._menu_manager.move_line_down_requested.connect(self._on_move_line_down)
        self._menu_manager.case_convert_requested.connect(self._on_case_convert)
        self._menu_manager.syntax_auto_detect_changed.connect(
            self._on_syntax_auto_detect_changed
        )
        self._menu_manager.language_selected.connect(self._on_language_selected)

        self._search_result_panel.navigate_to_match.connect(self._on_search_result_navigate)

        self._settings_interface.theme_change_requested.connect(
            lambda theme: self._theme_service.apply_theme(QApplication.instance(), theme)
        )
        self._settings_interface.settings_changed.connect(
            self._on_settings_page_changed
        )

    def _on_split_editor_ready(self, editor: CodeEditor) -> None:
        """! @brief 分屏编辑器初始化完成回调

        由 SplitViewManager 在创建分屏编辑器后调用，
        负责绑定信号、设置主题配色、应用配置，
        使分屏编辑器获得与主编辑器一致的能力。

        @param editor 分屏编辑器实例
        """
        index = self._tab_manager.get_current_index()
        self._bind_editor_signals(editor, index)

        if self._tab_manager.get_current_editor_colors():
            editor.set_editor_colors(self._tab_manager.get_current_editor_colors())

        self._logger.debug(f"分屏编辑器初始化完成 | index={index}")

    def _bind_editor_signals(self, editor: CodeEditor, index: int) -> None:
        """! @brief 绑定编辑器信号

        将编辑器的文本修改、光标位置变化和缩放变化信号连接到对应的槽。
        信号连接使用编辑器实例引用而非索引闭包，避免标签关闭重索引后
        闭包中的索引值变为陈旧导致修改状态被设置到错误标签。

        @param editor 代码编辑器实例
        @param index  标签页索引（仅用于日志，不用于信号连接）
        """
        if editor is None:
            return
        editor.text_modified.connect(
            lambda modified, ed=editor: self._on_editor_modified_by_editor(ed, modified)
        )
        editor.cursor_position_changed.connect(
            lambda line, col, ed=editor: self._on_cursor_changed_by_editor(ed, line, col)
        )
        editor.zoom_changed.connect(
            lambda percent: self._status_bar_widget.set_zoom(percent)
        )
        editor.zoom_changed.connect(
            lambda percent, ed=editor: self._on_zoom_save_config(ed)
        )
        editor.viewport().installEventFilter(self)
        show_ln = self._config_service.get(ConfigKey.SHOW_LINE_NUMBERS, True)
        word_wrap = self._config_service.get(ConfigKey.WORD_WRAP, False)
        editor.set_line_numbers_visible(show_ln)
        editor.set_word_wrap(word_wrap)

    # ========================================================================
    # 信号槽处理
    # ========================================================================

    @pyqtSlot(str)
    def _on_file_opened(self, file_path: str) -> None:
        """! @brief 文件打开后的处理槽

        @param file_path 已打开的文件路径
        """
        self._logger.info(f"File opened: {file_path}")
        self._hide_welcome_page()
        self._status_bar_widget.show_message(f"已打开：{os.path.basename(file_path)}", AppConstant.STATUS_MESSAGE_DURATION_MS)

    @pyqtSlot(str)
    def _on_file_saved(self, file_path: str) -> None:
        """! @brief 文件保存后的处理槽

        @param file_path 已保存的文件路径
        """
        self._logger.info(f"File saved: {file_path}")
        self._status_bar_widget.show_message(f"已保存：{os.path.basename(file_path)}", AppConstant.STATUS_MESSAGE_DURATION_MS)
        index = self._tab_manager.get_current_index()
        if index >= 0:
            self._update_status_bar_from_tab(index)

    @pyqtSlot(str)
    def _on_file_closed(self, file_path: str) -> None:
        """! @brief 文件关闭后的处理槽

        @param file_path 已关闭的文件路径
        """
        self._logger.info(f"File closed: {file_path}")

    @pyqtSlot(int)
    def _on_tab_changed(self, index: int) -> None:
        """! @brief 标签页切换后的处理槽

        分屏模式下，标签栏控制焦点屏：
        - 焦点在左屏(0)：标签切换改变左屏（stackedWidget自动处理）
        - 焦点在右屏(1)：标签切换改变右屏编辑器内容，左屏不变

        @param index 新的标签页索引（含欢迎页标签）
        """
        svm = getattr(self, '_split_view_manager', None)
        fm = getattr(self, '_focus_manager', None)
        if svm and svm.syncing_tab:
            return

        if fm and svm and svm.split_active and fm.focus_side == 1:
            fm.set_panel_tab_index(1, index)
            editor = self._tab_manager.get_editor(index)
            if editor and svm.split_editor:
                svm.split_editor.setPlainText(editor.toPlainText())
            saved = fm.panel_tab_index[0]
            if saved >= 0:
                self._tab_widget.blockSignals(True)
                self._tab_widget.stackedWidget.setCurrentIndex(saved)
                self._tab_widget.blockSignals(False)
            if svm.split_editor:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, svm.split_editor.setFocus)
            return

        if fm:
            fm.set_panel_tab_index(0, index)

        if self._tab_widget.is_welcome_tab(index):
            self.setWindowTitle("琉璃编辑器")
            self._status_bar_widget.set_cursor_position(0, 0)
            self._status_bar_widget.set_modified(False)
            self._status_bar_widget.set_encoding("")
            self._status_bar_widget.set_line_ending("")
            self._status_bar_widget.set_language("")
            self._status_bar_widget.set_zoom(100)
            return

        self._update_status_bar_from_tab(index)

        file_path = self._tab_manager.get_file_path(index)
        if file_path:
            title = os.path.basename(file_path)
            self.setWindowTitle(f"琉璃编辑器 - {title}")
        else:
            self.setWindowTitle("琉璃编辑器")

    @pyqtSlot(int)
    def _on_tab_closed_update(self, index: int) -> None:
        """! @brief 标签页关闭后的状态更新槽

        当所有标签页关闭时，重置窗口标题、状态栏并显示欢迎页。

        @param index 关闭的标签页索引
        """
        count = self._tab_manager.tab_count()
        if count == 0:
            self.setWindowTitle("琉璃编辑器")
            self._status_bar_widget.set_cursor_position(1, 1)
            self._status_bar_widget.set_modified(False)
            if not getattr(self, '_closing_welcome', False):
                self._show_welcome_page()
            self._closing_welcome = False

    @pyqtSlot(int)
    def _on_tab_created_bind_signals(self, index: int) -> None:
        """! @brief 标签页创建后的信号绑定槽

        @param index 新创建的标签页索引
        """
        editor = self._tab_manager.get_editor(index)
        if editor is not None:
            self._bind_editor_signals(editor, index)
            self._logger.debug(f"标签信号已绑定: [{index}]")

    def _update_status_bar_from_tab(self, index: int) -> None:
        """! @brief 从标签元数据统一更新状态栏

        从 TabManager 获取标签的完整信息，一次性更新状态栏所有字段。
        当标签元数据尚未就绪（如标签创建过程中 add_editor_tab 提前
        触发了 tab_changed 信号）时，仅更新光标位置和修改状态，
        跳过需要元数据的字段（编码、语言），后续由 editor_modified
        信号或 tag_switched 信号再次触发更新。

        @param index 标签页索引
        """
        if index < 0:
            return

        editor = self._tab_manager.get_editor(index)
        if editor is None:
            return

        # 光标位置（不需要元数据）
        line, col = editor.get_current_line_col()
        self._status_bar_widget.set_cursor_position(line, col)

        # 修改状态 —— 以 TabManager.is_tab_modified 为唯一数据源，
        # 不依赖 file_path 本地判断，避免元数据未就绪时的误判。
        self._status_bar_widget.set_modified(
            self._tab_manager.is_tab_modified(index)
        )

        # 编码和语言需要元数据，元数据未就绪时跳过
        meta = self._tab_manager.get_tab_meta(index)
        if meta is None:
            return

        file_path = meta.get("file_path")
        if file_path:
            enc_internal = meta.get("encoding", "utf-8")
            self._status_bar_widget.set_encoding(
                get_status_bar_encoding(enc_internal)
            )
        else:
            self._status_bar_widget.set_encoding("")

        line_ending = meta.get("line_ending", "LF")
        self._status_bar_widget.set_line_ending(line_ending)

        language = meta.get("language", "")
        self._status_bar_widget.set_language(
            language if language else "纯文本"
        )

    @pyqtSlot(int)
    def _on_tab_close_requested(self, index: int) -> None:
        """! @brief 标签页关闭请求处理槽

        如果文件有未保存的更改，弹出确认对话框。
        欢迎页标签直接关闭，无需确认。

        @param index 请求关闭的标签页索引
        """
        if self._tab_widget.is_welcome_tab(index):
            self._closing_welcome = True
            self._tab_widget.removeTab(index)
            return
        choice = self._confirm_close_unsaved_tab(index)
        if choice == 'save':
            self._save_and_close_tab(index)
        elif choice == 'discard':
            self._tab_manager.close_tab(index)

    def _is_empty_new_file(self, index: int) -> bool:
        """! @brief 判断指定标签是否为"空的未命名新文件"

        @param index 标签页索引
        @return True 表示是空的新建文件
        """
        file_path = self._tab_manager.get_file_path(index)
        if file_path:
            return False
        editor = self._tab_manager.get_editor(index)
        if editor is None:
            return False
        return not editor.toPlainText()

    def _confirm_close_unsaved_tab(self, index: int) -> Optional[str]:
        """! @brief 对未保存标签弹出关闭确认对话框

        @param index 标签页索引
        @return 'save' / 'discard' / None（取消）
        """
        if not self._tab_manager.is_tab_modified(index):
            return 'discard'

        if self._is_empty_new_file(index):
            return 'discard'

        file_path = self._tab_manager.get_file_path(index)
        title = os.path.basename(file_path) if file_path else "未命名"

        msg = MessageBox(
            "未保存的更改",
            f'文件"{title}"有未保存的更改。\n\n是否保存？',
            self,
        )
        msg.yesButton.setText("保存")
        msg.cancelButton.setText("不保存")

        cancelBtn = PushButton("取消")
        cancelBtn.setMinimumWidth(80)
        msg.yesButton.setMinimumWidth(80)
        msg.cancelButton.setMinimumWidth(80)
        msg.buttonLayout.addWidget(cancelBtn)
        cancelBtn.clicked.connect(msg.reject)

        return self._exec_tristate_dialog(msg, 'save', 'discard')

    def _save_and_close_tab(self, index: int) -> None:
        """! @brief 保存并关闭标签页

        委托给 ActionManager.save_and_close_tab 执行。

        @param index 标签页索引
        """
        self._action_manager.save_and_close_tab(index)

    @pyqtSlot()
    def _on_new_tab_requested(self) -> None:
        """! @brief 新标签页请求处理槽"""
        self._hide_welcome_page()
        self._action_manager.new_file()

    def _on_editor_modified(self, index: int, modified: bool) -> None:
        """! @brief 编辑器内容修改状态变化处理

        @param index   标签页索引
        @param modified 是否已修改
        """
        self._tab_manager.set_tab_modified(index, modified)
        if index == self._tab_manager.get_current_index():
            self._update_status_bar_from_tab(index)

    def _on_editor_modified_by_editor(self, editor: CodeEditor, modified: bool) -> None:
        """! @brief 编辑器内容修改状态变化处理（基于编辑器引用）

        @param editor  触发信号的编辑器实例
        @param modified 是否已修改
        """
        index = self._tab_manager.find_index_by_editor(editor)
        if index < 0:
            self._logger.warning("编辑器修改状态变化: 未找到对应标签索引")
            return
        self._on_editor_modified(index, modified)

    def _on_cursor_changed_by_editor(self, editor: CodeEditor, line: int, col: int) -> None:
        """! @brief 光标位置变化处理（基于编辑器引用）

        @param editor 触发信号的编辑器实例
        @param line   行号
        @param col    列号
        """
        index = self._tab_manager.find_index_by_editor(editor)
        if index < 0:
            return
        if index == self._tab_manager.get_current_index():
            self._status_bar_widget.set_cursor_position(line, col)

    def _on_zoom_save_config(self, editor: CodeEditor) -> None:
        font_size = editor.get_font_size()
        if not hasattr(self, '_zoom_save_timer'):
            self._zoom_save_timer = QTimer(self)
            self._zoom_save_timer.setSingleShot(True)
            self._zoom_save_timer.timeout.connect(self._do_zoom_save)
        self._pending_zoom_size = font_size
        self._zoom_save_timer.start(300)

    def _do_zoom_save(self) -> None:
        if hasattr(self, '_pending_zoom_size'):
            self._config_service.set(ConfigKey.FONT_SIZE, self._pending_zoom_size)

    # ========================================================================
    # 主题与配置
    # ========================================================================

    @pyqtSlot(str)
    def _on_theme_changed_apply(self, theme_name: str) -> None:
        """! @brief 主题切换应用槽

        更新主题菜单选中状态，应用主题到应用程序和各组件，
        包含分屏编辑器的主题更新。
        当切换到高对比度主题时，额外注入增强 QSS。

        @param theme_name 主题名称
        """
        if self._menu_manager:
            for tid, action in getattr(self._menu_manager, "_theme_actions", {}).items():
                action.setChecked(tid == theme_name)

        colors = self._theme_service.get_theme(theme_name)
        editor_colors = self._theme_service.get_editor_colors(theme_name)
        self._logger.debug(f"[高亮] 主题变更应用 | theme={theme_name!r}")
        self._tab_manager.set_editor_colors(editor_colors)

        fm = getattr(self, '_focus_manager', None)
        if fm and fm.split_active and fm.split_editor is not None:
            fm.split_editor.set_editor_colors(editor_colors)
            self._logger.debug("[高亮] 分屏编辑器主题已更新")

        self._status_bar_widget.update_theme(colors)
        self._search_bar.update_theme(colors)
        if self._welcome_page:
            self._welcome_page.update_theme_buttons(theme_name)
        self._apply_high_contrast_qss(theme_name)

    def _apply_high_contrast_qss(self, theme_name: str) -> None:
        """! @brief 高对比度主题时注入/移除增强 QSS

        @param theme_name 当前主题名称
        """
        if theme_name == ThemeService.THEME_HIGH_CONTRAST:
            if not getattr(self, '_high_contrast_qss_applied', False):
                current = self.styleSheet()
                self.setStyleSheet(current + ThemeService.HIGH_CONTRAST_QSS)
                self._high_contrast_qss_applied = True
        else:
            if getattr(self, '_high_contrast_qss_applied', False):
                current = self.styleSheet()
                stripped = current.replace(ThemeService.HIGH_CONTRAST_QSS, "")
                self.setStyleSheet(stripped)
                self._high_contrast_qss_applied = False

    def _on_theme_change(self, theme_id: str) -> None:
        """! @brief 主题切换处理

        由用户主动触发（点击主题按钮/菜单），委托 ThemeService 应用主题。

        @param theme_id 主题标识符
        """
        self._theme_service.apply_theme(QApplication.instance(), theme_id)
        self._config_service.set(ConfigKey.THEME, theme_id)

    def _on_theme_toolbar_clicked(self) -> None:
        """! @brief 命令栏主题按钮点击处理

        在按钮位置弹出主题选择菜单，委托 MenuBarManager 填充主题子菜单。
        """
        menu = RoundMenu(parent=self)
        self._menu_manager.populate_theme_menu(menu)
        button = None
        for btn in self._command_bar.commandButtons:
            if btn.action() is self._theme_action:
                button = btn
                break
        if button is not None:
            pos = button.mapToGlobal(button.rect().bottomLeft())
        else:
            pos = self._command_bar.mapToGlobal(
                self._command_bar.rect().bottomLeft()
            )
        menu.exec(pos)

    # ========================================================================
    # 语法高亮（MenuBarManager信号槽）
    # ========================================================================

    @pyqtSlot(int, str)
    def _on_syntax_auto_detect_changed(self, index: int, language: str) -> None:
        """! @brief 自动识别开关切换槽

        由 MenuBarManager.syntax_auto_detect_changed 信号触发。

        @param index   标签页索引
        @param language 检测到的语言名称
        """
        editor = self._tab_manager.get_editor(index)
        if editor is None:
            return
        meta = self._tab_manager.get_tab_meta(index)
        old_highlighter = meta.get("highlighter") if meta else None
        new_highlighter = self._highlighter_manager.apply_language_to_editor(
            language, editor,
            meta.get("file_size", 0) if meta else 0,
            self._tab_manager.get_current_editor_colors(),
            old_highlighter,
        )
        if new_highlighter and meta:
            meta["highlighter"] = new_highlighter
            meta["language"] = language
            self._tab_manager.set_tab_meta(index, meta)
        self._status_bar_widget.set_language(language if language else "纯文本")
        self._logger.info(
            f"标签 [{index}] 语法高亮切换为自动识别: {language or '纯文本'}"
        )

    @pyqtSlot(int, str)
    def _on_language_selected(self, index: int, language: str) -> None:
        """! @brief 手动选择语言槽

        由 MenuBarManager.language_selected 信号触发。
        手动选择语言后自动关闭"自动识别"开关，避免下次菜单仍显示打勾。

        @param index   标签页索引
        @param language 选择的语言名称
        """
        editor = self._tab_manager.get_editor(index)
        if editor is None:
            return
        meta = self._tab_manager.get_tab_meta(index)
        old_highlighter = meta.get("highlighter") if meta else None
        new_highlighter = self._highlighter_manager.apply_language_to_editor(
            language, editor,
            meta.get("file_size", 0) if meta else 0,
            self._tab_manager.get_current_editor_colors(),
            old_highlighter,
        )
        if new_highlighter and meta:
            meta["highlighter"] = new_highlighter
            meta["language"] = language
            meta["syntax_auto_detect"] = False
            self._tab_manager.set_tab_meta(index, meta)
        self._status_bar_widget.set_language(language)
        self._logger.info(f"标签 [{index}] 手动选择语法高亮: {language}")

    # ========================================================================
    # 分屏视图（委托 SplitViewManager）
    # ========================================================================

    @pyqtSlot()
    def _on_split_vertical(self) -> None:
        """! @brief 垂直分屏处理槽

        委托 SplitViewManager 切换分屏，并同步事件过滤器。
        """
        self._split_view_manager.remove_event_filter(self)
        self._split_view_manager.toggle_split(Qt.Horizontal)
        if self._split_view_manager.split_active:
            self._split_view_manager.install_event_filter(self)

    @pyqtSlot()
    def _on_split_horizontal(self) -> None:
        """! @brief 水平分屏处理槽

        委托 SplitViewManager 切换分屏，并同步事件过滤器。
        """
        self._split_view_manager.remove_event_filter(self)
        self._split_view_manager.toggle_split(Qt.Vertical)
        if self._split_view_manager.split_active:
            self._split_view_manager.install_event_filter(self)

    # ========================================================================
    # 配置与主题加载
    # ========================================================================

    def _load_config_and_theme(self) -> None:
        """! @brief 加载配置和主题

        从配置服务读取主题设置并应用。
        """
        config = self._config_service.load_settings()
        theme = config.get(ConfigKey.THEME, "dark")
        self._theme_service.apply_theme(QApplication.instance(), theme)

    def _restore_session(self) -> None:
        """! @brief 恢复上次会话

        从配置服务加载会话信息，恢复之前打开的文件和光标位置。
        支持恢复未保存/未命名文件的内容。
        首次启动时不创建空白标签页，而是显示欢迎页。
        """
        try:
            first_run = self._config_service.get(ConfigKey.FIRST_RUN, True)
            session = self._config_service.load_session()
            if not session:
                if first_run:
                    self._show_welcome_page()
                else:
                    self._tab_manager.create_tab(file_path=None, content="")
                return

            for file_info in session:
                file_path = file_info.get("path", "")
                cursor_pos = file_info.get("cursor_pos", 0)
                encoding = file_info.get("encoding", "utf-8")
                saved_content = file_info.get("content", "")
                saved_language = file_info.get("language", "")
                saved_auto_detect = file_info.get("syntax_auto_detect", True)

                # 构建 create_tab 通用参数（语言偏好优先使用保存值）
                tab_kwargs = {
                    "encoding": encoding,
                    "language": saved_language or None,
                    "syntax_auto_detect": saved_auto_detect,
                }

                if saved_content:
                    if file_path and os.path.exists(file_path):
                        index = self._tab_manager.create_tab(
                            file_path=file_path,
                            content=saved_content,
                            **tab_kwargs,
                        )
                        disk_content, _, _, _ = self._file_service.open_file(file_path)
                        if disk_content != saved_content:
                            self._tab_manager.set_tab_modified(index, True)
                    else:
                        index = self._tab_manager.create_tab(
                            file_path=None,
                            content=saved_content,
                            **tab_kwargs,
                        )
                        self._tab_manager.set_tab_modified(index, True)
                elif file_path and os.path.exists(file_path):
                    content, enc, _, err = self._file_service.open_file(file_path)
                    if err:
                        self._logger.warning(f"会话恢复: 打开文件失败 {file_path}: {err}")
                        continue
                    index = self._tab_manager.create_tab(
                        file_path=file_path,
                        content=content,
                        encoding=enc,
                        language=saved_language or None,
                        syntax_auto_detect=saved_auto_detect,
                    )
                elif not file_path:
                    index = self._tab_manager.create_tab(
                        file_path=None,
                        content="",
                        **tab_kwargs,
                    )
                else:
                    continue

                editor = self._tab_manager.get_editor(index)
                if editor and cursor_pos > 0:
                    text_len = len(editor.toPlainText())
                    if text_len > 0:
                        cursor = editor.textCursor()
                        cursor.setPosition(min(cursor_pos, text_len))
                        editor.setTextCursor(cursor)

            if self._tab_manager.tab_count() == 0:
                if first_run:
                    self._show_welcome_page()
                else:
                    self._tab_manager.create_tab(file_path=None, content="")
        except Exception as e:
            self._logger.error(f"Session restore failed: {e}")
            self._tab_manager.create_tab(file_path=None, content="")

    # ========================================================================
    # 命令行参数处理
    # ========================================================================

    def _process_cli_args(self) -> None:
        """! @brief 处理命令行参数

        委托给 _handle_external_files，统一 CLI 和 IPC 的文件打开逻辑。
        """
        self._handle_external_files(self._cli_args)

    def _apply_cursor_position(self, index: int, line: int, column: int) -> None:
        """! @brief 对指定标签页应用光标位置跳转

        @param index  标签页索引
        @param line   目标行号（None 表示不跳转行）
        @param column 目标列号（None 表示不跳转列）
        """
        editor = self._tab_manager.get_editor(index)
        if editor is None:
            return

        if line is not None:
            doc = editor.document()
            total_lines = doc.blockCount()
            if line > total_lines:
                self._logger.info(f"CLI: line {line} exceeds document length {total_lines}, "
                                  f"jumping to last line")
                self._signal_bus.status_message.emit("行号超出范围", AppConstant.STATUS_MESSAGE_DURATION_MS)
                line = total_lines
            editor.goto_line(line)

        if column is not None:
            editor.goto_column(column)

    # ========================================================================
    # 最近文件
    # ========================================================================

    def _on_open_recent_file(self, file_path: str) -> None:
        """! @brief 打开最近文件

        @param file_path 文件路径
        """
        if not os.path.exists(file_path):
            msg = MessageBox("文件未找到", f"文件未找到：\n{file_path}", self)
            msg.exec()
            return
        existing = self._tab_manager.find_tab_by_path(file_path)
        if existing >= 0:
            self._tab_manager.switch_to_tab(existing)
            return
        content, encoding, line_ending, err = self._file_service.open_file(file_path)
        if err:
            MessageBox("打开失败", err, self).exec()
            return
        index = self._tab_manager.create_tab(
            file_path=file_path,
            content=content,
            encoding=encoding,
        )
        self._tab_manager.switch_to_tab(index)

    def _on_remove_recent_file(self, file_path: str) -> None:
        """! @brief 从最近文件列表中移除指定文件

        @param file_path 文件路径
        """
        self._file_service.remove_recent_file(file_path)
        self._status_bar_widget.show_message(
            f"已从最近文件列表移除: {os.path.basename(file_path)}",
            AppConstant.STATUS_MESSAGE_DURATION_MS,
        )

    def _on_clear_recent_files(self) -> None:
        """! @brief 清空最近文件列表"""
        self._file_service.clear_recent_files()
        self._status_bar_widget.show_message("最近文件列表已清空", AppConstant.STATUS_MESSAGE_DURATION_MS)

    # ========================================================================
    # 状态栏与搜索
    # ========================================================================

    @pyqtSlot(str, int)
    def _on_status_message(self, message: str, duration: int) -> None:
        """! @brief 状态栏消息显示槽

        @param message  消息内容
        @param duration 显示时长（毫秒）
        """
        self._status_bar_widget.show_message(message, duration)

    @pyqtSlot(str)
    def _on_search_requested(self, search_text: str) -> None:
        """! @brief 搜索请求处理槽

        @param search_text 待搜索的文本
        """
        self._search_bar.show_bar()
        if search_text:
            self._search_bar.set_search_text(search_text)
        else:
            self._search_bar.focus_input()

    @pyqtSlot(dict)
    def _on_settings_page_changed(self, settings: dict) -> None:
        """! @brief 设置页配置变更槽

        由 SettingsPage.settings_changed(dict) 信号触发。
        设置内容已由 SettingsPage 自行持久化到配置文件，
        此处只刷新依赖配置的运行时状态（如快捷键注册表）。

        注意: 装饰器签名必须与信号签名一致（pyqtSignal(dict) -> @pyqtSlot(dict)），
        否则 PyQt5 会按装饰器声明的零参签名调用，抛出
        "missing 1 required positional argument" 并触发 qFatal -> abort。

        @param settings 变更后的完整设置字典
        """
        self._action_manager._apply_shortcuts_from_registry()

    def _on_config_updated(self) -> None:
        """! @brief 配置更新处理槽

        根据最新配置更新所有编辑器的设置。
        """
        show_ln = self._config_service.get(ConfigKey.SHOW_LINE_NUMBERS, True)
        word_wrap = self._config_service.get(ConfigKey.WORD_WRAP, False)
        font_family = self._config_service.get(ConfigKey.FONT_FAMILY, "")
        font_size = self._config_service.get(ConfigKey.FONT_SIZE, 13)
        tab_width = self._config_service.get(ConfigKey.TAB_WIDTH, 4)
        bracket_completion = self._config_service.get(ConfigKey.BRACKET_COMPLETION, True)
        auto_indent = self._config_service.get(ConfigKey.AUTO_INDENT, True)

        if font_family:
            from PyQt5.QtGui import QFontDatabase
            available_families = QFontDatabase().families()
            if font_family not in available_families:
                self._logger.warning(f"配置字体不可用，自动回退: {font_family}")
                MessageBox(
                    "字体不可用",
                    f'字体 "{font_family}" 在当前系统中不可用。\n已自动切换为默认等宽字体。',
                    self,
                ).exec()
                self._config_service.set(ConfigKey.FONT_FAMILY, "")
                font_family = ""

        for i in range(self._tab_widget.count()):
            if self._tab_widget.is_welcome_tab(i):
                continue
            editor = self._tab_widget.get_editor(i)
            if editor:
                editor.set_line_numbers_visible(show_ln)
                editor.set_word_wrap(word_wrap)
                if font_family:
                    font = editor.font
                    font.setFamily(font_family)
                    font.setPointSize(font_size)
                    editor.font = font
                    editor.setTabStopDistance(
                        QFontMetrics(font).horizontalAdvance(" ") * tab_width
                    )
                    editor.set_line_numbers_visible(show_ln)
                else:
                    editor.set_font_size(font_size)
                    editor.setTabStopDistance(
                        QFontMetrics(editor.font).horizontalAdvance(" ") * tab_width
                    )
                editor.set_bracket_completion(bracket_completion)
                editor.set_auto_indent(auto_indent)

        fm = getattr(self, '_focus_manager', None)
        if fm and fm.split_active and fm.split_editor is not None:
            split_ed = fm.split_editor
            split_ed.set_line_numbers_visible(show_ln)
            split_ed.set_word_wrap(word_wrap)
            if font_family:
                font = split_ed.font
                font.setFamily(font_family)
                font.setPointSize(font_size)
                split_ed.font = font
                split_ed.setTabStopDistance(
                    QFontMetrics(font).horizontalAdvance(" ") * tab_width
                )
            else:
                split_ed.set_font_size(font_size)
                split_ed.setTabStopDistance(
                    QFontMetrics(split_ed.font).horizontalAdvance(" ") * tab_width
                )
            split_ed.set_bracket_completion(bracket_completion)
            split_ed.set_auto_indent(auto_indent)

        reduce_anim = self._config_service.get(ConfigKey.REDUCE_ANIMATION, False)
        app = QApplication.instance()
        if app:
            animation_rule = (
                "* { animation-duration: 0ms !important; "
                "transition-duration: 0ms !important; }"
            )
            if reduce_anim:
                current = app.styleSheet()
                if animation_rule not in current:
                    app.setStyleSheet(current + "\n" + animation_rule)
            else:
                current = app.styleSheet()
                stripped = current.replace(animation_rule, "")
                if stripped != current:
                    app.setStyleSheet(stripped)

    def _on_search_execute(self, text: str, options: dict) -> None:
        """! @brief 执行搜索

        @param text    搜索文本
        @param options 搜索选项
        """
        editor = self._tab_widget.current_editor()
        if editor is None:
            return

        if not text:
            editor.clear_highlights()
            self._status_bar_widget.show_message("", 0)
            return

        search_service = self._action_manager.get_search_service()
        content = editor.toPlainText()
        matches, err = search_service.find_all(text, content, options)
        if err:
            self._status_bar_widget.show_message("无效的正则表达式", AppConstant.STATUS_MESSAGE_DURATION_MS)
            return

        editor.highlight_matches(matches)

        count = search_service.match_count()
        if count > 0:
            match = search_service.navigate_to(0)
            if match:
                self._navigate_to_match_from_service(editor, match)
            self._search_bar.set_match_count(1, count)
        else:
            self._search_bar.set_match_count(0, 0)
            self._status_bar_widget.show_message("未找到匹配项", AppConstant.STATUS_MESSAGE_DURATION_MS)

    def _navigate_to_match_from_service(self, editor, match_span: tuple) -> None:
        """! @brief 将编辑器光标移动到 SearchService 指定的匹配位置

        @param editor    编辑器实例
        @param match_span 匹配的 (start, end) 元组
        """
        start, end = match_span
        editor.goto_match(start, end)
        search_service = self._action_manager.get_search_service()
        self._search_bar.set_match_count(
            search_service.current_idx + 1, search_service.match_count()
        )

    @pyqtSlot()
    def _on_search_next(self) -> None:
        """! @brief 跳转到下一个搜索匹配项"""
        search_service = self._action_manager.get_search_service()
        editor = self._tab_widget.current_editor()
        if editor is None:
            return
        match = search_service.advance_next()
        if match:
            self._navigate_to_match_from_service(editor, match)

    @pyqtSlot()
    def _on_search_prev(self) -> None:
        """! @brief 跳转到上一个搜索匹配项"""
        search_service = self._action_manager.get_search_service()
        editor = self._tab_widget.current_editor()
        if editor is None:
            return
        match = search_service.advance_prev()
        if match:
            self._navigate_to_match_from_service(editor, match)

    @pyqtSlot()
    def _on_search_closed(self) -> None:
        """! @brief 搜索栏关闭处理

        清除所有编辑器的搜索高亮和匹配结果。
        """
        for i in range(self._tab_widget.count()):
            if self._tab_widget.is_welcome_tab(i):
                continue
            editor = self._tab_widget.get_editor(i)
            if editor:
                editor.clear_highlights()
        self._action_manager.get_search_service().clear()

    # ========================================================================
    # 编码、行尾符、语言变更
    # ========================================================================

    @pyqtSlot(str, str)
    def _on_file_encoding_changed(self, file_path: str, new_encoding: str) -> None:
        """! @brief 文件编码变更信号处理槽

        @param file_path 文件路径
        @param new_encoding 新编码的内部名称
        """
        current_path = self._tab_manager.get_current_file_path()
        if current_path == file_path:
            display = get_status_bar_encoding(new_encoding)
            self._status_bar_widget.set_encoding(display)
        self._logger.info(f"文件编码已变更: {file_path} -> {new_encoding}")

    @pyqtSlot(str)
    def _on_encoding_changed(self, encoding: str) -> None:
        """! @brief 编码变更处理槽

        @param encoding 目标编码的内部名称
        """
        self._logger.info(f"编码转换请求: {encoding}")
        index = self._tab_manager.get_current_index()
        if index < 0:
            return

        success, err = self._tab_manager.change_encoding_for_tab(index, encoding)
        if success:
            display = get_status_bar_encoding(encoding)
            self._status_bar_widget.set_encoding(display)
            self._signal_bus.status_message.emit(
                f"编码已转换为 {get_display_name(encoding)}", 3000
            )
        else:
            self._logger.warning(f"编码转换失败: {err}")
            msg_box = MessageBox(
                "编码转换失败",
                (err or "未知错误") + "\n\n是否强制转换？强制转换将清除无法编码的字符。",
                self,
            )
            msg_box.yesButton.setText("强制转换")
            msg_box.cancelButton.setText("取消")
            if msg_box.exec():
                force_success, force_err = self._tab_manager.change_encoding_for_tab(
                    index, encoding, force=True
                )
                if force_success:
                    display = get_status_bar_encoding(encoding)
                    self._status_bar_widget.set_encoding(display)
                    self._signal_bus.status_message.emit(
                        f"编码已强制转换为 {get_display_name(encoding)}", 3000
                    )
                else:
                    MessageBox(
                        "强制转换失败",
                        force_err or "未知错误",
                        self,
                    ).exec()

    @pyqtSlot(str)
    def _on_line_ending_changed(self, line_ending: str) -> None:
        """! @brief 行尾符变更处理槽

        @param line_ending 新的行尾符类型（LF/CRLF/CR）
        """
        self._logger.info(f"Line ending changed: {line_ending}")
        editor = self._tab_widget.current_editor()
        if editor is None:
            return
        content = editor.toPlainText()
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        if line_ending == "CRLF":
            content = content.replace("\n", "\r\n")
        elif line_ending == "CR":
            content = content.replace("\n", "\r")
        editor.setPlainText(content)
        index = self._tab_manager.get_current_index()
        if index >= 0:
            self._tab_manager.set_tab_modified(index, True)

    @pyqtSlot(str)
    def _on_language_changed(self, language: str) -> None:
        """! @brief 语言变更处理槽

        切换当前编辑器的语法高亮器，更新标签页元数据和状态栏。
        由 StatusBar.language_changed 信号触发（状态栏下拉选择语言）。

        @param language 新的语言标识
        """
        self._logger.info(f"Language changed: {language}")
        index = self._tab_manager.get_current_index()
        if index < 0:
            self._logger.debug("[高亮] 状态栏语言切换跳过: index<0")
            return

        editor = self._tab_manager.get_editor(index)
        if editor is None:
            return
        meta = self._tab_manager.get_tab_meta(index)
        old_highlighter = meta.get("highlighter") if meta else None
        new_highlighter = self._highlighter_manager.apply_language_to_editor(
            language, editor,
            meta.get("file_size", 0) if meta else 0,
            self._tab_manager.get_current_editor_colors(),
            old_highlighter,
        )
        if new_highlighter and meta:
            meta["highlighter"] = new_highlighter
            meta["language"] = language
            meta["syntax_auto_detect"] = False
            self._tab_manager.set_tab_meta(index, meta)
        self._status_bar_widget.set_language(language)

    # ========================================================================
    # 编辑操作
    # ========================================================================

    def _on_delete(self) -> None:
        """! @brief 删除选中文本"""
        editor = self._tab_widget.current_editor()
        if editor:
            cursor = editor.textCursor()
            if cursor.hasSelection():
                cursor.removeSelectedText()

    def _on_delete_line(self) -> None:
        """! @brief 删除当前行"""
        editor = self._tab_widget.current_editor()
        if editor:
            editor.delete_current_line()

    def _on_duplicate_line(self) -> None:
        """! @brief 复制当前行"""
        editor = self._tab_widget.current_editor()
        if editor:
            editor.duplicate_line()

    def _on_move_line_up(self) -> None:
        """! @brief 上移当前行"""
        editor = self._tab_widget.current_editor()
        if editor:
            editor.move_line_up()

    def _on_move_line_down(self) -> None:
        """! @brief 下移当前行"""
        editor = self._tab_widget.current_editor()
        if editor:
            editor.move_line_down()

    def _on_case_convert(self, mode: str) -> None:
        """! @brief 大小写转换

        @param mode 转换模式（upper/lower/title/swap）
        """
        editor = self._tab_widget.current_editor()
        if editor:
            cursor = editor.textCursor()
            if cursor.hasSelection():
                text = cursor.selectedText()
                converted = ToolService.convert_case(text, mode)
                cursor.insertText(converted)

    def _on_sort_dedup(self) -> None:
        """! @brief 排序去重

        对选中文本进行排序并去重，未选中文本时提示用户。
        """
        editor = self._tab_widget.current_editor()
        if editor:
            cursor = editor.textCursor()
            if cursor.hasSelection():
                text = cursor.selectedText()
                result = ToolService.sort_lines(text, unique=True)
                cursor.insertText(result)
            else:
                msg = MessageBox("排序去重", "请先选择文本。", self)
                msg.exec()

    # ========================================================================
    # 搜索结果导航（SearchResultPanel信号槽）
    # ========================================================================

    def _on_search_result_navigate(self, tab_index: int, line_num: int, search_text: str) -> None:
        """! @brief 搜索结果导航槽

        由 SearchResultPanel.navigate_to_match 信号触发，
        切换到目标标签页，定位到目标行，高亮匹配词。

        @param tab_index  目标标签页索引
        @param line_num   目标行号
        @param search_text 搜索文本
        """
        self._tab_manager.switch_to_tab(tab_index)

        editor = self._tab_manager.get_editor(tab_index)
        if editor is None:
            return

        editor.goto_line(line_num)

        import re
        try:
            pattern = re.compile(re.escape(search_text), re.IGNORECASE)
            content = editor.toPlainText()
            matches = [(m.start(), m.end()) for m in pattern.finditer(content)]
            editor.clear_highlights()
            editor.highlight_matches(matches)

            lines = content.split('\n')
            if line_num <= len(lines):
                line_start = sum(len(l) + 1 for l in lines[:line_num - 1])
                for start, end in matches:
                    if start >= line_start:
                        editor.goto_match(start, end)
                        break
        except re.error:
            pass

        editor.setFocus()

    # ========================================================================
    # 打印与导出PDF
    # ========================================================================

    def _on_print(self) -> None:
        """! @brief 打印当前编辑器内容

        弹出系统打印对话框，将编辑器内容发送至用户选择的打印机。
        """
        editor = self._tab_widget.current_editor()
        if editor is None:
            return

        try:
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec_() == QPrintDialog.Accepted:
                editor.print_(printer)
                self._status_bar_widget.show_message("打印任务已发送", AppConstant.STATUS_MESSAGE_DURATION_MS)
        except Exception as e:
            self._logger.error(f"打印失败: {e}")
            MessageBox("打印失败", f"打印时发生错误：\n{str(e)}", self).exec_()

    def _export_pdf(self) -> None:
        """! @brief 导出当前编辑器内容为PDF"""
        editor = self._tab_widget.current_editor()
        if editor is None:
            MessageBox("请先打开文件", "没有打开的文件可供导出。", self).exec_()
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出PDF", "", "PDF文件 (*.pdf)"
        )
        if not file_path:
            return

        try:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            printer.setPageMargins(
                AppConstant.PDF_MARGIN_MM, AppConstant.PDF_MARGIN_MM,
                AppConstant.PDF_MARGIN_MM, AppConstant.PDF_MARGIN_MM,
                QPrinter.Millimeter,
            )

            doc = editor.document().clone()
            doc.setTextWidth(printer.pageRect(QPrinter.DevicePixel).width())

            cursor = QTextCursor(doc)
            cursor.select(QTextCursor.Document)
            fmt = QTextCharFormat()
            fmt.setFontFamily(editor.font().family())
            fmt.setFontPointSize(10)
            cursor.mergeCharFormat(fmt)

            doc.print_(printer)

            doc.deleteLater()
            self._status_bar_widget.show_message("PDF 导出成功", AppConstant.STATUS_MESSAGE_DURATION_MS)
        except Exception as e:
            self._logger.error(f"PDF export failed: {e}")
            MessageBox("导出失败", f"导出PDF时发生错误：\n{str(e)}", self).exec_()

    # ========================================================================
    # 全屏
    # ========================================================================

    def toggle_fullscreen(self) -> None:
        """! @brief 切换全屏模式

        仅负责切换全屏状态；控件的显示/隐藏由 changeEvent 统一处理。
        """
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def changeEvent(self, event) -> None:
        """! @brief 窗口状态变更事件处理

        @param event QEvent 对象
        """
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            if self.isFullScreen():
                self._menu_bar_widget.hide()
                self._status_bar_widget.hide()
            else:
                self._menu_bar_widget.show()
                self._status_bar_widget.show()

    # ========================================================================
    # 拖拽打开文件
    # ========================================================================

    def dragEnterEvent(self, event) -> None:
        """! @brief 拖拽进入事件处理

        仅接受包含文件URL的拖拽事件。
        """
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        """! @brief 拖拽释放事件处理

        将拖拽的文件在编辑器中打开。
        """
        urls = event.mimeData().urls()
        for url in urls:
            file_path = url.toLocalFile()
            if file_path and os.path.isfile(file_path):
                self._open_dropped_file(file_path)
        event.acceptProposedAction()

    def _open_dropped_file(self, file_path: str) -> None:
        """! @brief 打开拖拽的文件

        @param file_path 文件路径
        """
        existing = self._tab_manager.find_tab_by_path(file_path)
        if existing >= 0:
            self._tab_manager.switch_to_tab(existing)
            return
        content, encoding, line_ending, err = self._file_service.open_file(file_path)
        if err:
            MessageBox("打开失败", err, self).exec()
            return
        index = self._tab_manager.create_tab(
            file_path=file_path, content=content, encoding=encoding,
        )
        self._tab_manager.switch_to_tab(index)

    # ========================================================================
    # 编辑器右键上下文菜单
    # ========================================================================

    def eventFilter(self, obj, event) -> bool:
        """! @brief 事件过滤器

        处理编辑器视口的右键点击事件，显示上下文菜单。
        处理分屏模式下鼠标按下事件，根据点击位置追踪焦点侧。
        使用 FocusManager.is_split_viewport() 替代脆弱的引用比较。
        """
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QMouseEvent
        fm = getattr(self, '_focus_manager', None)
        svm = getattr(self, '_split_view_manager', None)
        if event.type() == QEvent.MouseButtonPress and isinstance(event, QMouseEvent):
            if fm and svm and svm.split_active:
                if fm.is_split_viewport(obj):
                    svm.set_focus_side(1)
                else:
                    editor = self._tab_manager.get_current_editor()
                    if editor and obj is editor.viewport():
                        svm.set_focus_side(0)
            if event.button() == Qt.RightButton:
                for i in range(self._tab_manager.tab_count()):
                    editor = self._tab_manager.get_editor(i)
                    if editor and obj == editor.viewport():
                        self._show_editor_context_menu(editor, event.pos())
                        return True
        return super().eventFilter(obj, event)

    def _show_editor_context_menu(self, editor, pos) -> None:
        """! @brief 显示编辑器右键上下文菜单

        使用Fluent风格RoundMenu提供常用编辑命令。

        @param editor 代码编辑器实例
        @param pos    鼠标位置
        """
        menu = RoundMenu(parent=self)
        am = self._action_manager

        menu.addAction(am.get_action("cut"))
        menu.addAction(am.get_action("copy"))
        menu.addAction(am.get_action("paste"))
        menu.addSeparator()
        menu.addAction(am.get_action("select_all"))
        menu.addSeparator()

        line_menu = RoundMenu("行操作", self)
        line_menu.addAction(Action("删除行", triggered=self._on_delete_line))
        line_menu.addAction(Action("复制行", triggered=self._on_duplicate_line))
        line_menu.addAction(Action("上移行", triggered=self._on_move_line_up))
        line_menu.addAction(Action("下移行", triggered=self._on_move_line_down))
        menu.addMenu(line_menu)
        menu.addSeparator()

        menu.addAction(am.get_action("find"))
        menu.addAction(am.get_action("replace"))

        global_pos = editor.viewport().mapToGlobal(pos)
        menu.exec_(global_pos)

    # ========================================================================
    # 文件外部修改处理
    # ========================================================================

    @pyqtSlot(str)
    def _on_file_externally_modified(self, file_path: str) -> None:
        """! @brief 文件被外部修改时的处理

        弹出提示询问用户是否重新加载。

        @param file_path 被修改的文件路径
        """
        title = os.path.basename(file_path)
        msg = MessageBox(
            "文件已更改",
            f'文件"{title}"已被外部程序修改。\n\n是否重新加载？',
            self,
        )
        msg.yesSignal.connect(lambda: self._reload_file(file_path))
        msg.cancelSignal.connect(lambda checked=False: None)
        msg.exec()

    def _reload_file(self, file_path: str) -> None:
        """! @brief 重新加载指定文件

        @param file_path 文件路径
        """
        index = self._tab_manager.find_tab_by_path(file_path)
        if index < 0:
            return
        editor = self._tab_manager.get_editor(index)
        if editor is None:
            return
        encoding = self._tab_manager.get_current_encoding()
        content, err = self._file_service.reload_file(file_path, encoding=encoding)
        if err:
            MessageBox("重新加载失败", err, self).exec()
            return
        editor.setPlainText(content)
        self._tab_manager.set_tab_modified(index, False)

    # ========================================================================
    # 公共接口方法（供 ActionManager 等外部模块调用）
    # ========================================================================

    def export_pdf(self) -> None:
        """! @brief 导出当前编辑器内容为PDF（公共接口）"""
        self._export_pdf()

    def confirm_close_unsaved_tab(self, index: int) -> Optional[str]:
        """! @brief 对未保存标签弹出关闭确认对话框（公共接口）

        @param index 标签页索引
        @return 'save' / 'discard' / None（取消）
        """
        return self._confirm_close_unsaved_tab(index)

    def show_welcome_page(self) -> None:
        """! @brief 切换到欢迎页标签（公共接口）"""
        self._show_welcome_page()

    def find_in_files(self) -> None:
        """! @brief 多文件查找入口（公共接口）

        委托给 SearchResultPanel.find_in_files() 执行。
        """
        self._search_result_panel.find_in_files()

    # ========================================================================
    # 公共查询方法
    # ========================================================================

    def get_search_text(self) -> str:
        """! @brief 获取当前搜索栏文本

        @return 搜索文本，搜索栏不可见时返回空字符串
        """
        return self._search_bar.get_search_text() if self._search_bar.isVisible() else ""
