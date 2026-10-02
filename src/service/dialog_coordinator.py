"""
对话框协调器模块 —— 统一管理所有 UI 对话框的创建

负责实例化并展示各种对话框（MessageBox、设置、查找替换等），
使得 Controller 层（ActionManager）不必直接操作 UI 组件，
实现分层解耦。

设计依据: docs/架构设计.md 2.3节 分层设计

注意: 对话框类通过依赖注入传入，避免 Service 层直接导入 UI 层组件。
"""

from typing import Dict, Optional

from PyQt5.QtWidgets import QWidget, QFileDialog

from qfluentwidgets import MessageBox

from src.infrastructure.logger import get_logger


class DialogCoordinator:
    """! 对话框协调器

    统一管理编辑器中所有对话框的创建与展示。
    所有方法接收 parent 作为 UI 上下文参数，仅负责创建和展示对话框，
    不包含业务逻辑。

    对话框类通过依赖注入传入，避免 Service 层直接导入 UI 层组件，
    遵循 UI -> Controller -> Service -> Infrastructure 分层架构。
    """

    def __init__(self, config_service=None, dialog_classes: Dict = None):
        """
        @param config_service   配置服务实例（可选）
        @param dialog_classes   对话框类字典（可选），用于依赖注入。
                                键为对话框标识符，值为对话框类引用。
                                若未提供，则使用延迟导入获取默认对话框类。
        """
        self._logger = get_logger("DialogCoordinator")
        self._config_service = config_service
        self._dialog_classes = dialog_classes or {}

    def _get_dialog_class(self, name: str):
        """! 延迟获取对话框类

        优先使用依赖注入的类引用，若未提供则延迟导入。
        延迟导入仅在运行时执行，避免模块级别的跨层引用。

        @param name    对话框标识符
        @return        对话框类引用
        """
        if name in self._dialog_classes:
            return self._dialog_classes[name]

        # 延迟导入映射表：仅在运行时按需加载，避免模块级别的 Service -> UI 跨层引用
        lazy_map = {
            "find_replace": "src.ui.dialogs.find_replace_dialog:FindReplaceDialog",
            "goto_line": "src.ui.dialogs.goto_line_dialog:GotoLineDialog",
            "statistics": "src.ui.dialogs.statistics_dialog:StatisticsDialog",
            "hash": "src.ui.dialogs.hash_dialog:HashDialog",
        }
        if name in lazy_map:
            module_path, class_name = lazy_map[name].rsplit(":", 1)
            import importlib
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            # 缓存到 _dialog_classes 避免重复导入
            self._dialog_classes[name] = cls
            self._logger.debug(f"延迟导入对话框类: {name} -> {module_path}.{class_name}")
            return cls

        raise ValueError(f"未知的对话框类型: {name}")

    # ------------------------------------------------------------------
    #  通用消息提示
    # ------------------------------------------------------------------

    def show_info(self, parent: QWidget, title: str, content: str) -> None:
        """! 显示信息提示框

        @param parent  父窗口
        @param title   标题
        @param content 内容
        """
        MessageBox(title, content, parent).exec_()

    def show_warning(self, parent: QWidget, title: str, content: str) -> None:
        """! 显示警告提示框

        @param parent  父窗口
        @param title   标题
        @param content 内容
        """
        MessageBox(title, content, parent).exec_()

    def show_error(self, parent: QWidget, title: str, content: str) -> None:
        """! 显示错误提示框

        @param parent  父窗口
        @param title   标题
        @param content 内容
        """
        MessageBox(title, content, parent).exec_()

    def confirm(self, parent: QWidget, title: str, content: str) -> bool:
        """! 显示确认对话框

        @param parent  父窗口
        @param title   标题
        @param content 内容
        @return        True 用户确认，False 取消
        """
        return MessageBox(title, content, parent).exec_()

    # ------------------------------------------------------------------
    #  文件对话框
    # ------------------------------------------------------------------

    def show_open_file_dialog(
        self, parent: QWidget, default_dir: str = "",
    ) -> Optional[str]:
        """! 弹出打开文件对话框

        @param parent       父窗口
        @param default_dir  默认目录
        @return             选择的文件路径，None 表示取消
        """
        file_path, _ = QFileDialog.getOpenFileName(
            parent, "打开文件", default_dir,
            "所有文件 (*);;文本文件 (*.txt *.py *.js *.ts *.html *.css *.json *.xml *.md);;",
        )
        return file_path if file_path else None

    def show_save_file_dialog(
        self, parent: QWidget, default_name: str = "untitled.txt",
    ) -> Optional[str]:
        """! 弹出另存为对话框

        @param parent        父窗口
        @param default_name  默认文件名
        @return              选择的文件路径，None 表示取消
        """
        file_path, _ = QFileDialog.getSaveFileName(
            parent, "另存为", default_name,
            "所有文件 (*);;文本文件 (*.txt);;",
        )
        return file_path if file_path else None

    # ------------------------------------------------------------------
    #  编辑对话框
    # ------------------------------------------------------------------

    def show_find_replace_dialog(
        self, parent: QWidget, selected_text: str = "",
        find_next_callback=None,
        replace_callback=None,
        replace_all_callback=None,
    ) -> None:
        """! 创建查找替换对话框并展示

        @param parent                父窗口
        @param selected_text         初始搜索文本
        @param find_next_callback    查找下一个回调
        @param replace_callback      替换回调
        @param replace_all_callback  全部替换回调
        """
        FindReplaceDialog = self._get_dialog_class("find_replace")
        dialog = FindReplaceDialog(parent=parent, selected_text=selected_text)
        if find_next_callback:
            dialog.find_next_requested.connect(find_next_callback)
        if replace_callback:
            dialog.replace_requested.connect(replace_callback)
        if replace_all_callback:
            dialog.replace_all_requested.connect(replace_all_callback)
        dialog.exec_()

    def show_goto_line_dialog(
        self, parent: QWidget, max_lines: int,
        goto_callback,
    ) -> None:
        """! 创建转到行对话框并展示

        @param parent         父窗口
        @param max_lines      最大行数
        @param goto_callback  跳转回调
        """
        GotoLineDialog = self._get_dialog_class("goto_line")
        dialog = GotoLineDialog(max_lines=max_lines, parent=parent)
        if goto_callback:
            dialog.goto_line_requested.connect(goto_callback)
        dialog.exec_()

    def show_statistics_dialog(
        self, parent: QWidget, stats: Dict, file_name: str = "untitled",
    ) -> None:
        """! 创建统计信息对话框并展示

        @param parent     父窗口
        @param stats      统计数据字典
        @param file_name  文件名
        """
        StatisticsDialog = self._get_dialog_class("statistics")
        dialog = StatisticsDialog(parent=parent, stats=stats)
        dialog.setWindowTitle(f"统计信息 - {file_name}")
        dialog.exec_()

    def show_hash_dialog(
        self,
        parent: QWidget,
        file_path: str = "",
        selected_text: str = "",
        full_text: str = "",
        needs_file_save: bool = False,
        save_callback=None,
    ) -> None:
        """! 创建哈希计算对话框并展示

        @param parent          父窗口
        @param file_path       文件路径（有磁盘文件时使用）
        @param selected_text   编辑器选中文本（无选中时为""）
        @param full_text       编辑器完整文本
        @param needs_file_save 文件是否需要先保存再计算文件哈希
        @param save_callback   保存文件的回调函数
        """
        HashDialog = self._get_dialog_class("hash")
        dialog = HashDialog(
            parent=parent,
            file_path=file_path,
            selected_text=selected_text,
            full_text=full_text,
            needs_file_save=needs_file_save,
            save_callback=save_callback,
        )
        dialog.exec_()

    # ------------------------------------------------------------------
    #  大文件确认
    # ------------------------------------------------------------------

    def confirm_large_file(self, parent: QWidget, file_size: float) -> bool:
        """! 大文件只读打开确认

        @param parent     父窗口
        @param file_size  文件大小（字节）
        @return           True 以只读方式打开，False 取消
        """
        size_mb = file_size / (1024 * 1024)
        return self.confirm(
            parent,
            "大文件",
            f"文件大小为 {size_mb:.1f} MB。\n是否以只读方式打开？",
        )
