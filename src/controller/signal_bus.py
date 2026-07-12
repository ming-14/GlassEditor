"""
全局信号总线 —— 单例模式，解耦模块间通信

设计依据: doc/架构设计.md 2.2节 EventRouter, 3.3节信号总线

所有模块都可以连接和发射 SignalBus 的信号。
UI 层作为用户事件源发射信号（如主题切换）属于向下广播模式，
Controller/Service 层发射信号属于业务事件广播。
具体发射方见各信号的文档说明。
"""

from PyQt5.QtCore import QObject, pyqtSignal

from src.infrastructure.logger import get_logger
from src.infrastructure.singleton import QSingleton


class SignalBus(QObject, metaclass=QSingleton):
    """
    全局信号总线（单例）

    提供跨模块的事件通信机制，减少直接耦合。
    使用 pyqtSignal 实现，兼容 Qt 事件循环。

    信号列表:
        file_opened(str):          文件打开，参数为文件路径
                                   由 FileService 发射
        file_saved(str):           文件保存，参数为文件路径
                                   由 FileService 发射
        file_closed(str):          文件关闭，参数为文件路径
                                   由 FileService 发射
        file_encoding_changed(str, str): 文件编码转换，参数为(文件路径, 新编码)
                                         由 TabManager 发射
        theme_changed(str):        主题切换，参数为主题名称
                                   由 MainWindow 发射
        config_updated():          配置更新（无参数）
                                   由 ConfigService 发射
        status_message(str, int):  状态栏消息(文本, 持续毫秒)
                                   由各模块按需发射
        search_requested(str):     查找请求，参数为查找文本
                                   由搜索相关模块发射
        app_minimize_to_tray():    应用即将最小化到系统托盘
                                   由 MainWindow.closeEvent 发射
        tray_icon_activated():     托盘图标被点击，请求显示窗口
                                   由 SystemTrayIcon 发射
    """

    # —— 信号定义 ——
    file_opened = pyqtSignal(str)
    file_saved = pyqtSignal(str)
    file_closed = pyqtSignal(str)
    file_encoding_changed = pyqtSignal(str, str)
    theme_changed = pyqtSignal(str)
    config_updated = pyqtSignal()
    status_message = pyqtSignal(str, int)
    search_requested = pyqtSignal(str)
    app_minimize_to_tray = pyqtSignal()
    tray_icon_activated = pyqtSignal()

    def __init__(self):
        """构造函数 —— 仅首次实例化时执行"""
        super().__init__()
        self._logger = get_logger("SignalBus")
        self._logger.debug("SignalBus 单例已创建")