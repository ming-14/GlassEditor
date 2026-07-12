"""! @brief 系统托盘图标模块

封装 QSystemTrayIcon，提供右键上下文菜单（显示窗口/新建/打开/退出）
和左键单击激活窗口功能，以及气泡通知能力。
"""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QWidget

from qfluentwidgets import RoundMenu, Action, FluentIcon

from src.infrastructure.app_constants import AppConstant
from src.infrastructure.logger import get_logger


class SystemTrayIcon(QSystemTrayIcon):
    """! @brief 系统托盘图标组件

    提供右键上下文菜单和左键单击激活窗口功能。

    @var show_window_requested: 用户请求显示/恢复主窗口
    @var new_file_requested:    用户请求新建文件
    @var open_file_requested:   用户请求打开文件
    @var quit_requested:        用户请求退出应用
    """

    show_window_requested = pyqtSignal()
    new_file_requested = pyqtSignal()
    open_file_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: QWidget = None):
        """! @brief 构造系统托盘图标

        @param parent 父组件，通常为主窗口
        """
        super().__init__(parent)
        self._logger = get_logger("SystemTrayIcon")
        self._parent = parent

        icon = FluentIcon.EDIT.icon()
        self.setIcon(icon)
        self.setToolTip(AppConstant.TRAY_TOOLTIP)

        self._menu = self._build_context_menu()
        self.setContextMenu(self._menu)

        self.activated.connect(self._on_activated)

    def _build_context_menu(self) -> RoundMenu:
        """! @brief 构建右键上下文菜单

        @return 圆角菜单实例
        """
        menu = RoundMenu("琉璃编辑器", self._parent)

        menu.addAction(
            Action(
                FluentIcon.VIEW, "显示主窗口",
                triggered=self.show_window_requested.emit,
            )
        )
        menu.addSeparator()
        menu.addAction(
            Action(
                FluentIcon.ADD, "新建文件",
                triggered=self.new_file_requested.emit,
            )
        )
        menu.addAction(
            Action(
                FluentIcon.FOLDER, "打开文件...",
                triggered=self.open_file_requested.emit,
            )
        )
        menu.addSeparator()
        menu.addAction(
            Action(
                FluentIcon.CLOSE, "退出",
                triggered=self.quit_requested.emit,
            )
        )

        self._logger.debug("托盘上下文菜单已构建")
        return menu

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """! @brief 托盘图标激活事件处理

        左键单击或双击时发射显示窗口请求信号。

        @param reason 激活原因
        """
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._logger.debug("托盘图标被激活，请求显示窗口")
            self.show_window_requested.emit()

    def show_notification(
        self, title: str, message: str,
        duration_ms: int = AppConstant.STATUS_MESSAGE_DURATION_MS,
    ):
        """! @brief 显示气泡通知

        @param title   通知标题
        @param message 通知内容
        @param duration_ms 通知持续时间（毫秒）
        """
        self.showMessage(title, message, QSystemTrayIcon.Information, duration_ms)
        self._logger.debug(f"托盘气泡通知: [{title}] {message}")

    @staticmethod
    def is_tray_available() -> bool:
        """! @brief 检测系统托盘是否可用

        @return True 表示系统支持托盘图标
        """
        return QSystemTrayIcon.isSystemTrayAvailable()
