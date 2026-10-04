"""统计信息对话框模块

使用 PyQt-Fluent-Widgets 的 MessageBoxBase 组件构建的文档统计信息对话框，
展示字符数、词数、行数等统计结果。
"""
from typing import Dict, Optional

from PyQt5.QtWidgets import (
    QHBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, MessageBoxBase, TitleLabel,
)
from src.infrastructure.logger import get_logger

_logger = get_logger("StatisticsDialog")


class StatisticsDialog(MessageBoxBase):
    """! 统计信息对话框

    基于 MessageBoxBase 构建，展示文档的字符数（含/不含空格）、词数、行数等统计结果。

    Args:
        parent: 父窗口
        stats: 统计数据字典，包含 chars_with_spaces、chars_without_spaces、words、lines
    """
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        stats: Optional[Dict[str, int]] = None,
    ):
        super().__init__(parent)
        self._logger = get_logger("StatisticsDialog")
        self.setWindowTitle("统计信息")
        self.setAccessibleName("统计信息")

        if stats is None:
            stats = {
                "chars_with_spaces": 0,
                "chars_without_spaces": 0,
                "words": 0,
                "lines": 0,
            }

        self._init_ui(stats)

    def _init_ui(self, stats: Dict[str, int]) -> None:
        """! 初始化界面布局

        Args:
            stats: 统计数据字典
        """

        # 固定对话框最小宽度，避免统计行被压缩（MaskDialogBase 按内容 hint 布局）
        self.widget.setMinimumWidth(360)

        # 标题
        title_label = TitleLabel("文档统计")
        title_label.setAccessibleName("文档统计")
        self.viewLayout.addWidget(title_label)
        self.viewLayout.addSpacing(4)

        # 统计行：标签左对齐、数值右对齐加粗
        self._chars_with_value = self._add_stat_row(
            "字符数（含空格）：", stats["chars_with_spaces"]
        )
        self._chars_without_value = self._add_stat_row(
            "字符数（不含空格）：", stats["chars_without_spaces"]
        )
        self._words_value = self._add_stat_row("词数：", stats["words"])
        self._lines_value = self._add_stat_row("行数：", stats["lines"])

        self.viewLayout.addStretch()

        # 配置底部按钮
        self.yesButton.setText("关闭")
        self.cancelButton.hide()

    def _add_stat_row(self, label_text: str, value: int) -> BodyLabel:
        """! 添加一行统计信息（标签左对齐、数值右对齐）

        Args:
            label_text: 统计项名称
            value: 统计数值

        Returns:
            数值标签，供调用方保留引用
        """
        row = QHBoxLayout()
        row.addWidget(BodyLabel(label_text))
        row.addStretch()

        value_label = BodyLabel(str(value))
        value_label.setStyleSheet("font-weight: bold;")
        row.addWidget(value_label)

        self.viewLayout.addLayout(row)
        return value_label
