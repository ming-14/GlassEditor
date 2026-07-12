"""统计信息对话框模块

使用 PyQt-Fluent-Widgets 的 MessageBoxBase 组件构建的文档统计信息对话框，
展示字符数、词数、行数等统计结果。
"""
from typing import Dict, Optional

from PyQt5.QtWidgets import (
    QHBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, MessageBoxBase, SettingCardGroup,
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

        # 统计信息分组
        stats_group = SettingCardGroup("文档统计", self)
        stats_group.setAccessibleName("文档统计")

        # 字符数（含空格）
        chars_with_widget = QWidget()
        chars_with_layout = QHBoxLayout(chars_with_widget)
        chars_with_layout.setContentsMargins(20, 8, 20, 8)
        chars_with_label = BodyLabel("字符数（含空格）：")
        self._chars_with_value = BodyLabel(str(stats["chars_with_spaces"]))
        self._chars_with_value.setStyleSheet("font-weight: bold;")
        chars_with_layout.addWidget(chars_with_label)
        chars_with_layout.addStretch()
        chars_with_layout.addWidget(self._chars_with_value)
        stats_group.addSettingCard(chars_with_widget)

        # 字符数（不含空格）
        chars_without_widget = QWidget()
        chars_without_layout = QHBoxLayout(chars_without_widget)
        chars_without_layout.setContentsMargins(20, 8, 20, 8)
        chars_without_label = BodyLabel("字符数（不含空格）：")
        self._chars_without_value = BodyLabel(str(stats["chars_without_spaces"]))
        self._chars_without_value.setStyleSheet("font-weight: bold;")
        chars_without_layout.addWidget(chars_without_label)
        chars_without_layout.addStretch()
        chars_without_layout.addWidget(self._chars_without_value)
        stats_group.addSettingCard(chars_without_widget)

        # 词数
        words_widget = QWidget()
        words_layout = QHBoxLayout(words_widget)
        words_layout.setContentsMargins(20, 8, 20, 8)
        words_label = BodyLabel("词数：")
        self._words_value = BodyLabel(str(stats["words"]))
        self._words_value.setStyleSheet("font-weight: bold;")
        words_layout.addWidget(words_label)
        words_layout.addStretch()
        words_layout.addWidget(self._words_value)
        stats_group.addSettingCard(words_widget)

        # 行数
        lines_widget = QWidget()
        lines_layout = QHBoxLayout(lines_widget)
        lines_layout.setContentsMargins(20, 8, 20, 8)
        lines_label = BodyLabel("行数：")
        self._lines_value = BodyLabel(str(stats["lines"]))
        self._lines_value.setStyleSheet("font-weight: bold;")
        lines_layout.addWidget(lines_label)
        lines_layout.addStretch()
        lines_layout.addWidget(self._lines_value)
        stats_group.addSettingCard(lines_widget)

        # 将统计分组添加到 MessageBoxBase 的内容区域
        self.viewLayout.addWidget(stats_group)

        # 配置底部按钮
        self.yesButton.setText("关闭")
        self.cancelButton.hide()
