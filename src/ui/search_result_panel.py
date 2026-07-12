"""! @brief 搜索结果面板组件模块

从 MainWindow 中提取的多文件搜索结果面板组件，
包含搜索输入框、查找按钮和结果树。
"""

import os
import re

from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QApplication, QTreeWidgetItem,
)

from qfluentwidgets import (
    PushButton, StrongBodyLabel, BodyLabel,
    SearchLineEdit, LineEdit,
    TreeWidget, Dialog, MessageBox,
)

from src.infrastructure.app_constants import AppConstant
from src.infrastructure.logger import get_logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.controller.tab_manager import TabManager
    from src.controller.signal_bus import SignalBus
    from src.ui.editor_tab_widget import EditorTabWidget


class SearchResultPanel(QWidget):
    """! @brief 多文件搜索结果面板

    包含搜索输入框、查找按钮和结果树，
    支持跨标签页多文件搜索和结果导航。

    @signal navigate_to_match(int, int, str) 导航到匹配项，参数为(标签索引, 行号, 搜索文本)
    """

    navigate_to_match = pyqtSignal(int, int, str)

    def __init__(
        self,
        tab_manager: 'TabManager',
        signal_bus: 'SignalBus',
        parent: QWidget = None,
    ):
        """! @brief 搜索结果面板构造函数

        @param tab_manager 标签页管理器
        @param signal_bus 信号总线
        @param parent 父组件
        """
        super().__init__(parent)
        self._logger = get_logger("SearchResultPanel")
        self._tab_manager = tab_manager
        self._signal_bus = signal_bus
        self._tab_widget_ref = None

        self._search_result_input: SearchLineEdit = None
        self._search_result_btn: PushButton = None
        self._search_result_status: BodyLabel = None
        self._search_result_tree: TreeWidget = None

        self._build_ui()

    def _build_ui(self) -> None:
        """! @brief 构建面板UI布局

        创建搜索输入框、查找按钮、状态标签、关闭按钮和结果树。
        """
        self.setObjectName("searchResultPanel")
        self.setMinimumWidth(180)
        self.setMaximumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        title_label = StrongBodyLabel("查找结果")
        layout.addWidget(title_label)

        search_layout = QHBoxLayout()
        self._search_result_input = SearchLineEdit()
        self._search_result_input.setPlaceholderText("输入搜索文本...")
        self._search_result_input.returnPressed.connect(self._on_search_panel_search)
        search_layout.addWidget(self._search_result_input, 1)

        self._search_result_btn = PushButton("查找")
        self._search_result_btn.clicked.connect(self._on_search_panel_search)
        search_layout.addWidget(self._search_result_btn)
        layout.addLayout(search_layout)

        self._search_result_status = BodyLabel("")
        self._search_result_status.setWordWrap(True)
        layout.addWidget(self._search_result_status)

        close_btn = PushButton("关闭")
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

        self._search_result_tree = TreeWidget()
        self._search_result_tree.setHeaderLabels(["文件名 / 行号", "匹配内容"])
        self._search_result_tree.setRootIsDecorated(True)
        self._search_result_tree.setAlternatingRowColors(True)
        self._search_result_tree.setColumnWidth(0, AppConstant.SEARCH_PANEL_MIN_WIDTH)
        self._search_result_tree.itemDoubleClicked.connect(
            self._on_search_result_double_clicked
        )
        layout.addWidget(self._search_result_tree, 1)

    def set_tab_widget_ref(self, tab_widget: 'EditorTabWidget') -> None:
        """! @brief 设置标签页组件引用

        @param tab_widget EditorTabWidget 实例
        """
        self._tab_widget_ref = tab_widget

    def show_panel(self) -> None:
        """! @brief 显示查找结果面板

        将面板添加到分割器中并设置分割比例。
        """
        splitter = self.parent()
        if splitter and hasattr(splitter, 'indexOf') and splitter.indexOf(self) >= 0:
            self.show()
            sizes = splitter.sizes()
            total = sum(sizes)
            if total > 0:
                splitter.setSizes([int(total * 0.6), int(total * 0.4)])

    def hide_panel(self) -> None:
        """! @brief 隐藏查找结果面板"""
        splitter = self.parent()
        if splitter and hasattr(splitter, 'indexOf') and splitter.indexOf(self) >= 0:
            self.hide()

    def find_in_files(self) -> None:
        """! @brief 多文件查找入口

        弹出输入对话框获取搜索文本，遍历所有已打开的标签页执行搜索，
        将匹配结果显示在侧边栏结果面板中。

        标签页数量超过20时弹出提示，搜索过程中禁用查找按钮。
        """
        self.show_panel()

        dialog = Dialog("在文件中查找", "请输入搜索文本：", self.window())
        dialog.yesButton.setText("查找")
        dialog.cancelButton.setText("取消")

        input_edit = LineEdit()
        input_edit.setText(self._search_result_input.text())
        dialog.textLayout.addWidget(input_edit)

        if dialog.exec():
            text = input_edit.text().strip()
        else:
            return

        if not text:
            return

        search_text = text.strip()
        self._search_result_input.setText(search_text)
        self._perform_multi_file_search(search_text)

    @pyqtSlot()
    def _on_search_panel_search(self) -> None:
        """! @brief 面板中查找按钮点击处理

        使用面板输入框中的文本执行多文件搜索。
        """
        search_text = self._search_result_input.text().strip()
        if not search_text:
            return
        self._perform_multi_file_search(search_text)

    def _perform_multi_file_search(self, search_text: str) -> None:
        """! @brief 执行多文件搜索核心逻辑

        遍历所有打开标签页的编辑器内容，使用正则表达式搜索匹配项，
        收集文件名、行号、匹配行内容并填充到结果树中。

        @param search_text 搜索文本
        """
        tab_count = self._tab_manager.tab_count()
        if tab_count == 0:
            self._search_result_status.setText("没有打开的标签页")
            self._search_result_tree.clear()
            return

        if tab_count > AppConstant.MULTI_FILE_SEARCH_TAB_WARNING:
            msg = MessageBox(
                "搜索提示",
                f"当前打开了 {tab_count} 个标签页，搜索可能较慢。是否继续？",
                self.window(),
            )
            if not msg.exec_():
                return

        self._search_result_btn.setEnabled(False)
        self._search_result_status.setText("搜索中...")
        self._search_result_tree.clear()

        QApplication.processEvents()

        try:
            pattern = re.compile(re.escape(search_text), re.IGNORECASE)
        except re.error:
            self._search_result_status.setText("无效的搜索文本")
            self._search_result_btn.setEnabled(True)
            return

        total_matches = 0
        file_count = 0

        for tab_idx in range(self._tab_widget_ref.count()):
            if self._tab_widget_ref.is_welcome_tab(tab_idx):
                continue
            editor = self._tab_manager.get_editor(tab_idx)
            file_path = self._tab_manager.get_file_path(tab_idx)
            if editor is None:
                continue

            display_name = (
                os.path.basename(file_path) if file_path
                else f"未命名 ({tab_idx + 1})"
            )

            content = editor.toPlainText()
            if not content:
                continue

            lines = content.split('\n')

            file_matches = []
            for line_idx, line_content in enumerate(lines, start=1):
                for m in pattern.finditer(line_content):
                    file_matches.append((line_idx, line_content, m.start(), m.end()))

            if not file_matches:
                continue

            file_count += 1

            file_item = QTreeWidgetItem(self._search_result_tree)
            file_item.setText(0, f"{display_name} ({len(file_matches)} 处匹配)")
            file_item.setText(1, file_path or "")
            file_item.setData(
                0, Qt.UserRole,
                {"type": "file", "file_path": file_path or "", "tab_index": tab_idx},
            )
            file_item.setExpanded(True)

            for line_num, line_content, match_start, match_end in file_matches:
                match_item = QTreeWidgetItem(file_item)
                match_item.setText(0, f"行 {line_num}")

                display_line = line_content.strip()
                if len(display_line) > AppConstant.SEARCH_RESULT_LINE_TRUNCATE:
                    display_line = display_line[:AppConstant.SEARCH_RESULT_LINE_TRUNCATE] + "..."

                match_item.setText(1, display_line)
                match_item.setData(
                    0, Qt.UserRole,
                    {
                        "type": "match",
                        "tab_index": tab_idx,
                        "line_num": line_num,
                        "search_text": search_text,
                    },
                )
                total_matches += 1

        self._search_result_status.setText(
            f"在 {file_count} 个文件中找到 {total_matches} 处匹配"
        )
        self._search_result_btn.setEnabled(True)

    @pyqtSlot("QTreeWidgetItem*", int)
    def _on_search_result_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """! @brief 双击搜索结果节点处理

        对于匹配行节点（二级节点）：发射导航信号，
        由 MainWindow 处理标签切换和光标定位。

        @param item   被双击的树节点
        @param column 被双击的列索引
        """
        data = item.data(0, Qt.UserRole)
        if not data or data.get("type") != "match":
            return

        tab_index = data["tab_index"]
        line_num = data["line_num"]
        search_text = data["search_text"]

        self.navigate_to_match.emit(tab_index, line_num, search_text)
