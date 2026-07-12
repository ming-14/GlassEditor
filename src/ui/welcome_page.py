"""! @brief 欢迎页组件模块

从 MainWindow 中提取的欢迎页独立组件，包含标题、快捷键速查表、
主题切换按钮组、新建文件和打开文件按钮。
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidgetItem, QTableWidgetItem,
)

from qfluentwidgets import (
    PushButton, StrongBodyLabel, SubtitleLabel,
    SimpleCardWidget, TableWidget, FluentIcon,
)

from src.infrastructure.app_constants import AppConstant


class WelcomePage(QWidget):
    """! @brief 欢迎页组件

    包含标题、快捷键速查表、主题切换按钮组、新建文件和打开文件按钮。
    通过信号与 MainWindow 通信，不直接依赖业务逻辑。

    @signal theme_changed_requested(str) 主题切换请求，参数为主题ID
    @signal new_file_requested() 新建文件请求
    @signal open_file_requested() 打开文件请求
    """

    theme_changed_requested = pyqtSignal(str)
    new_file_requested = pyqtSignal()
    open_file_requested = pyqtSignal()

    def __init__(self, parent: QWidget = None):
        """! @brief 欢迎页构造函数

        @param parent 父组件，默认为 None
        """
        super().__init__(parent)
        self.setObjectName("welcomePage")
        self.setAccessibleName("欢迎页")

        self._dark_btn: PushButton = None
        self._light_btn: PushButton = None

        self._build_ui()

    def _build_ui(self) -> None:
        """! @brief 构建欢迎页UI布局

        创建标题、快捷键速查表、主题切换按钮组和操作按钮，
        使用居中卡片布局呈现。
        """
        outer_layout = QVBoxLayout(self)
        outer_layout.setAlignment(Qt.AlignCenter)

        card = SimpleCardWidget(self)
        card.setObjectName("welcomeCard")
        card.setMaximumWidth(AppConstant.WELCOME_CARD_MAX_WIDTH)
        card.setMaximumHeight(AppConstant.WELCOME_CARD_MAX_HEIGHT)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 24, 32, 24)
        card_layout.setSpacing(16)

        self._build_title(card_layout)
        self._build_shortcut_table(card_layout)
        self._build_theme_buttons(card_layout)
        self._build_action_buttons(card_layout)

        outer_layout.addWidget(card)

    def _build_title(self, layout: QVBoxLayout) -> None:
        """! @brief 构建标题区域

        @param layout 目标布局
        """
        title_label = StrongBodyLabel("欢迎使用琉璃编辑器")
        title_label.setObjectName("welcomeTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        subtitle = SubtitleLabel("轻量级桌面文本/代码编辑器")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setObjectName("welcomeSubtitle")
        layout.addWidget(subtitle)

        layout.addSpacing(8)

    def _build_shortcut_table(self, layout: QVBoxLayout) -> None:
        """! @brief 构建快捷键速查表

        @param layout 目标布局
        """
        shortcut_label = StrongBodyLabel("快捷键速查")
        shortcut_label.setObjectName("shortcutSectionTitle")
        layout.addWidget(shortcut_label)

        table = TableWidget()
        table.setColumnCount(2)
        table.setObjectName("shortcutTable")
        table.setHorizontalHeaderLabels(["操作", "快捷键"])
        table.horizontalHeader().setSectionResizeMode(0, table.horizontalHeader().Stretch)
        table.horizontalHeader().setSectionResizeMode(1, table.horizontalHeader().ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(table.NoEditTriggers)
        table.setSelectionMode(table.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setAlternatingRowColors(True)
        table.setMaximumHeight(220)
        table.setAccessibleName("快捷键速查表")

        shortcuts = [
            ("--- 文件操作 ---", [
                ("新建文件", "Ctrl+N"),
                ("打开文件", "Ctrl+O"),
                ("保存", "Ctrl+S"),
                ("关闭标签", "Ctrl+W"),
                ("退出", "Ctrl+Q"),
            ]),
            ("--- 编辑操作 ---", [
                ("撤销", "Ctrl+Z"),
                ("重做", "Ctrl+Y"),
                ("剪切", "Ctrl+X"),
                ("复制", "Ctrl+C"),
                ("粘贴", "Ctrl+V"),
                ("全选", "Ctrl+A"),
            ]),
            ("--- 查找 ---", [
                ("查找", "Ctrl+F"),
                ("替换", "Ctrl+H"),
                ("转到行", "Ctrl+G"),
            ]),
            ("--- 视图 ---", [
                ("放大/缩小", "Ctrl+滚轮"),
                ("全屏", "F11"),
                ("垂直分屏", "Ctrl+Alt+V"),
                ("水平分屏", "Ctrl+Alt+H"),
            ]),
        ]

        for group_title, items in shortcuts:
            group_row = table.rowCount()
            table.insertRow(group_row)
            group_name_item = QTableWidgetItem(group_title)
            group_name_font = group_name_item.font()
            group_name_font.setBold(True)
            group_name_item.setFont(group_name_font)
            group_name_item.setFlags(Qt.NoItemFlags)
            table.setItem(group_row, 0, group_name_item)
            table.setSpan(group_row, 0, 1, 2)

            for desc, key in items:
                row = table.rowCount()
                table.insertRow(row)
                desc_item = QTableWidgetItem(f"  {desc}")
                desc_item.setFlags(Qt.NoItemFlags)
                table.setItem(row, 0, desc_item)
                key_item = QTableWidgetItem(key)
                key_item.setFlags(Qt.NoItemFlags)
                table.setItem(row, 1, key_item)

        layout.addWidget(table)
        layout.addSpacing(8)

    def _build_theme_buttons(self, layout: QVBoxLayout) -> None:
        """! @brief 构建主题切换按钮组

        @param layout 目标布局
        """
        theme_label = StrongBodyLabel("主题切换")
        theme_label.setObjectName("themeSectionTitle")
        layout.addWidget(theme_label)

        theme_btn_layout = QHBoxLayout()
        theme_btn_layout.setSpacing(12)

        self._dark_btn = PushButton("深色主题")
        self._dark_btn.setMinimumWidth(120)
        self._dark_btn.setAccessibleName("深色主题按钮")
        self._dark_btn.clicked.connect(lambda: self.theme_changed_requested.emit("dark"))
        theme_btn_layout.addWidget(self._dark_btn)

        self._light_btn = PushButton("浅色主题")
        self._light_btn.setMinimumWidth(120)
        self._light_btn.setAccessibleName("浅色主题按钮")
        self._light_btn.clicked.connect(lambda: self.theme_changed_requested.emit("light"))
        theme_btn_layout.addWidget(self._light_btn)

        theme_btn_layout.addStretch()
        layout.addLayout(theme_btn_layout)
        layout.addSpacing(8)

    def _build_action_buttons(self, layout: QVBoxLayout) -> None:
        """! @brief 构建新建/打开文件按钮

        @param layout 目标布局
        """
        action_btn_layout = QHBoxLayout()
        action_btn_layout.setSpacing(12)

        new_file_btn = PushButton("新建文件")
        new_file_btn.setMinimumWidth(140)
        new_file_btn.setIcon(FluentIcon.ADD)
        new_file_btn.setAccessibleName("新建文件按钮")
        new_file_btn.clicked.connect(self.new_file_requested.emit)
        action_btn_layout.addWidget(new_file_btn)

        open_file_btn = PushButton("打开文件")
        open_file_btn.setMinimumWidth(140)
        open_file_btn.setIcon(FluentIcon.FOLDER)
        open_file_btn.setAccessibleName("打开文件按钮")
        open_file_btn.clicked.connect(self.open_file_requested.emit)
        action_btn_layout.addWidget(open_file_btn)

        action_btn_layout.addStretch()
        layout.addLayout(action_btn_layout)

    def update_theme_buttons(self, theme: str) -> None:
        """! @brief 更新主题按钮样式

        根据当前主题高亮对应按钮。

        @param theme 当前主题名称（"dark" 或 "light"）
        """
        dark_active = (theme == "dark")
        self._dark_btn.setProperty("active", dark_active)
        self._light_btn.setProperty("active", not dark_active)
        self._dark_btn.style().unpolish(self._dark_btn)
        self._dark_btn.style().polish(self._dark_btn)
        self._light_btn.style().unpolish(self._light_btn)
        self._light_btn.style().polish(self._light_btn)
