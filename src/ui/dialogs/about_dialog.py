"""关于对话框模块

使用 PyQt-Fluent-Widgets 的 MessageBoxBase 组件构建的关于对话框，
展示应用程序名称、版本、描述等信息。
"""
from typing import Optional

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt

from qfluentwidgets import (
    MessageBoxBase, TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel,
)
from src.infrastructure.logger import get_logger

_logger = get_logger("AboutDialog")


class AboutDialog(MessageBoxBase):
    """! @brief 关于对话框

    展示琉璃编辑器的名称、版本号、功能描述和技术信息。
    基于 MessageBoxBase 实现，自动处理模态与布局。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._logger = get_logger("AboutDialog")
        self.setWindowTitle("关于琉璃编辑器")
        self.setAccessibleName("关于琉璃编辑器")

        self._init_ui()

    def _init_ui(self) -> None:
        """! @brief 初始化界面布局

        使用 MessageBoxBase 提供的 viewLayout 作为内容区域布局，
        并配置内置按钮。
        """
        self.viewLayout.setSpacing(12)

        # 应用名称
        self._name_label = TitleLabel("琉璃编辑器")
        self._name_label.setAlignment(Qt.AlignCenter)
        self._name_label.setAccessibleName("应用名称")
        self.viewLayout.addWidget(self._name_label)

        # 版本号
        self._version_label = SubtitleLabel("版本 1.0.0")
        self._version_label.setAlignment(Qt.AlignCenter)
        self.viewLayout.addWidget(self._version_label)

        self.viewLayout.addSpacing(8)

        # 功能描述
        self._desc_label = BodyLabel("轻量级桌面文本/代码编辑器")
        self._desc_label.setAlignment(Qt.AlignCenter)
        self._desc_label.setWordWrap(True)
        self.viewLayout.addWidget(self._desc_label)

        # 技术信息
        self._tech_label = CaptionLabel("基于 PyQt5 与 PyQt-Fluent-Widgets 构建")
        self._tech_label.setAlignment(Qt.AlignCenter)
        self.viewLayout.addWidget(self._tech_label)

        self.viewLayout.addStretch()

        # 配置内置按钮
        self.yesButton.setText("关闭")
        self.cancelButton.hide()
