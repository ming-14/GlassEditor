"""! @brief 系统托盘图标模块

封装 QSystemTrayIcon，提供右键上下文菜单（显示窗口/新建/打开/退出）
和左键单击激活窗口功能，以及气泡通知能力。
"""

from PyQt5.QtCore import pyqtSignal, QSize
from PyQt5.QtWidgets import QSystemTrayIcon, QWidget, QApplication

from qfluentwidgets import RoundMenu, Action, FluentIcon

from src.infrastructure.app_constants import AppConstant
from src.infrastructure.logger import get_logger


class TrayContextMenu(RoundMenu):
    """! @brief 托盘右键菜单

    QSystemTrayIcon 的右键菜单由 QMenu::popup() 弹出，其定位存在两个问题：
    1. popup() 用 sizeHint() 判断是否需要向上翻转，而 RoundMenu 继承自
       QMenu 的 sizeHint() 只按动作文本估算（4 项约 88px），远小于真实
       菜单高度（约 154px），导致 Qt 误判"放得下"而不翻转；
    2. 翻转时使用的是整屏 geometry（含任务栏），而非 availableGeometry，
       菜单底部会被任务栏/屏幕边缘截断。

    因此这里同时给出真实尺寸，并在 showEvent 后把菜单夹回当前屏幕的
    可用区域内，保证所有菜单项都可见。
    """

    def __init__(self, title: str = "", parent: QWidget = None):
        """! @brief 构造托盘右键菜单

        @param title  菜单标题
        @param parent 父组件，通常为主窗口
        """
        super().__init__(title, parent)
        self._logger = get_logger("TrayContextMenu")

    def sizeHint(self) -> QSize:
        """! @brief 返回菜单真实尺寸

        @return 布局尺寸提示（含内外边距），供 QMenu::popup 定位使用
        """
        layout = self.layout()
        if layout is None:
            return super().sizeHint()
        return layout.sizeHint()

    def showEvent(self, e) -> None:
        """! @brief 菜单显示后夹取到屏幕可用区域内

        @param e QShowEvent 对象
        """
        super().showEvent(e)
        self._clamp_to_available_geometry()

    def _clamp_to_available_geometry(self) -> None:
        """! @brief 将菜单整体移动到所在屏幕的可用区域内（避开任务栏）"""
        screen = QApplication.screenAt(self.pos())
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        rect = self.geometry()
        x = min(max(rect.x(), available.left()),
                max(available.left(), available.right() - rect.width() + 1))
        y = min(max(rect.y(), available.top()),
                max(available.top(), available.bottom() - rect.height() + 1))

        if (x, y) != (rect.x(), rect.y()):
            self.move(x, y)
            self._logger.debug(
                f"托盘菜单已移入可用区域: {rect} -> ({x}, {y})"
            )


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

    def _build_context_menu(self) -> TrayContextMenu:
        """! @brief 构建右键上下文菜单

        @return 托盘专用圆角菜单实例（自带屏幕边界修正）
        """
        menu = TrayContextMenu("琉璃编辑器", self._parent)

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
