"""哈希计算器对话框模块

使用 PyQt-Fluent-Widgets 的 MessageBoxBase 组件构建的哈希计算对话框，
支持 MD5、SHA1、SHA256 算法，计算结果可一键复制到剪贴板。
没有文本输入框，自动根据编辑器上下文计算哈希，支持选中文本/整个文件/整个文本切换。
文件保存由对话框的"计算"按钮触发，若文件有待保存修改则按钮显示"保存文件并计算"。
"""
import hashlib
import os
from typing import Callable, Optional

from PyQt5.QtWidgets import (
    QHBoxLayout, QWidget, QApplication,
)
from PyQt5.QtCore import pyqtSignal

from qfluentwidgets import (
    MessageBoxBase, LineEdit, ComboBox,
    PrimaryPushButton, PushButton, BodyLabel,
)
from src.infrastructure.logger import get_logger

_logger = get_logger("HashDialog")

# 读块大小：64 KB
_CHUNK_SIZE = 64 * 1024

# 哈希范围选项
_SCOPE_SELECTED = "选中文本"
_SCOPE_FILE = "整个文件"
_SCOPE_TEXT = "整个文本"


class HashDialog(MessageBoxBase):
    """哈希计算器对话框

    基于 MessageBoxBase 构建。无文本输入框，根据调用方传入的数据自动计算哈希。
    当编辑器有选中文本时，提供"选中文本 / 整个文件（或整个文本）"切换。
    若文件有待保存修改且范围为"整个文件"，按钮显示"保存文件并计算"，
    点击时先保存文件再计算哈希。

    Signals:
        hash_computed(str, str): 哈希计算完成时发射，参数为算法名称和哈希值
    """
    hash_computed = pyqtSignal(str, str)

    _ALGORITHMS = {
        "MD5": hashlib.md5,
        "SHA1": hashlib.sha1,
        "SHA256": hashlib.sha256,
    }

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        file_path: str = "",
        selected_text: str = "",
        full_text: str = "",
        needs_file_save: bool = False,
        save_callback: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self._logger = get_logger("HashDialog")
        self._file_path = file_path
        self._selected_text = selected_text
        self._full_text = full_text
        self._needs_file_save = needs_file_save
        self._save_callback = save_callback
        self.setWindowTitle("哈希计算器")
        self.setAccessibleName("哈希计算器")

        self._init_ui()

        # 打开对话框时自动计算（不涉及保存）
        self._compute()

    def _init_ui(self) -> None:
        """初始化界面布局"""
        self.viewLayout.setSpacing(12)

        # 增大对话框横向宽度
        self.widget.setMinimumWidth(520)

        # ---- 哈希范围行（仅在有选中文本时显示） ----
        has_selection = bool(self._selected_text)
        if has_selection:
            self._scope_layout = QHBoxLayout()
            self._scope_label = BodyLabel("哈希范围：")
            self._scope_layout.addWidget(self._scope_label)

            self._scope_combo = ComboBox()
            scope_options = [_SCOPE_SELECTED]
            if self._file_path:
                scope_options.append(_SCOPE_FILE)
            else:
                scope_options.append(_SCOPE_TEXT)
            self._scope_combo.addItems(scope_options)
            self._scope_combo.setCurrentIndex(0)
            self._scope_combo.setAccessibleName("哈希范围")
            self._scope_layout.addWidget(self._scope_combo)

            self._scope_layout.addStretch()
            self.viewLayout.addLayout(self._scope_layout)

        # ---- 文件/来源信息行 ----
        self._source_layout = QHBoxLayout()
        self._source_label = BodyLabel("来源：")
        self._source_layout.addWidget(self._source_label)

        source_text = self._file_path if self._file_path else "未命名（编辑器文本）"
        self._source_info = BodyLabel(source_text)
        self._source_info.setAccessibleName("哈希来源")
        self._source_layout.addWidget(self._source_info)

        self._source_layout.addStretch()
        self.viewLayout.addLayout(self._source_layout)

        # ---- 算法选择与计算按钮行 ----
        self._algo_layout = QHBoxLayout()
        self._algo_label = BodyLabel("算法：")
        self._algo_layout.addWidget(self._algo_label)

        self._algo_combo = ComboBox()
        self._algo_combo.addItems(list(self._ALGORITHMS.keys()))
        self._algo_combo.setAccessibleName("算法选择")
        self._algo_layout.addWidget(self._algo_combo)

        self._compute_btn = PrimaryPushButton(self._get_button_text())
        self._compute_btn.setMinimumWidth(120)
        self._compute_btn.setAccessibleName("计算哈希")
        self._algo_layout.addWidget(self._compute_btn)

        self._algo_layout.addStretch()
        self.viewLayout.addLayout(self._algo_layout)

        # ---- 计算结果行 ----
        self._result_layout = QHBoxLayout()
        self._result_label = BodyLabel("结果：")
        self._result_layout.addWidget(self._result_label)

        self._result_input = LineEdit()
        self._result_input.setReadOnly(True)
        self._result_input.setPlaceholderText("自动计算结果...")
        self._result_input.setAccessibleName("哈希结果")
        self._result_layout.addWidget(self._result_input)

        self._copy_btn = PushButton("复制")
        self._copy_btn.setMinimumWidth(60)
        self._copy_btn.setAccessibleName("复制哈希结果")
        self._result_layout.addWidget(self._copy_btn)

        self.viewLayout.addLayout(self._result_layout)
        self.viewLayout.addStretch()

        # 底部按钮
        self.yesButton.setText("关闭")
        self.cancelButton.hide()

        # 连接信号
        self._compute_btn.clicked.connect(self._on_compute_clicked)
        self._copy_btn.clicked.connect(self._on_copy)
        if has_selection:
            self._scope_combo.currentIndexChanged.connect(self._on_scope_changed)

    # ------------------------------------------------------------------
    # 按钮文字与行为
    # ------------------------------------------------------------------

    def _is_file_scope(self) -> bool:
        """判断当前是否处于"整个文件"哈希的范围"""
        scope = self._get_current_scope()
        if scope == _SCOPE_FILE:
            return True
        # 无选中文本时没有范围选择器，但有文件路径则默认为文件范围
        if not scope and self._file_path and os.path.isfile(self._file_path):
            return True
        return False

    def _get_button_text(self) -> str:
        """根据当前范围决定按钮文字"""
        if self._is_file_scope() and self._needs_file_save:
            return "保存文件并计算"
        return "计算"

    def _update_button_text(self) -> None:
        """更新按钮文字"""
        self._compute_btn.setText(self._get_button_text())

    def _on_scope_changed(self) -> None:
        """范围切换时：更新按钮文字并重新计算"""
        self._update_button_text()
        self._compute()

    def _on_compute_clicked(self) -> None:
        """点击计算按钮：若需要先保存文件则保存，然后计算"""
        if self._is_file_scope() and self._needs_file_save and self._save_callback:
            self._save_callback()
            self._needs_file_save = False
            self._update_button_text()
            # 保存后验证文件是否存在
            if not os.path.isfile(self._file_path):
                self._result_input.setText("保存失败，无法计算文件哈希")
                return
        self._compute()

    # ------------------------------------------------------------------
    # 哈希计算
    # ------------------------------------------------------------------

    def _get_current_scope(self) -> str:
        """获取当前选中的哈希范围"""
        if hasattr(self, '_scope_combo') and self._scope_combo.isVisible():
            return self._scope_combo.currentText()
        return ""

    def _compute(self) -> None:
        """根据当前哈希范围执行计算，计算前先清空旧结果"""
        self._result_input.clear()
        scope = self._get_current_scope()
        if scope == _SCOPE_SELECTED:
            self._compute_text_hash(self._selected_text)
        elif scope == _SCOPE_FILE:
            self._compute_file_hash()
        elif scope == _SCOPE_TEXT:
            self._compute_text_hash(self._full_text)
        elif self._file_path and os.path.isfile(self._file_path):
            # 无选中文本 + 有文件 → 计算文件哈希
            self._compute_file_hash()
        elif self._full_text:
            # 无选中文本 + 无文件 → 计算全文本哈希
            self._compute_text_hash(self._full_text)
        else:
            self._result_input.setText("无可用数据")

    def _compute_file_hash(self) -> None:
        """计算文件的哈希值（分块读取）"""
        algo_name = self._algo_combo.currentText()
        algo_func = self._ALGORITHMS.get(algo_name)
        if algo_func is None:
            return

        try:
            hash_obj = algo_func()
            with open(self._file_path, "rb") as f:
                while True:
                    chunk = f.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    hash_obj.update(chunk)
            result = hash_obj.hexdigest()
            self._result_input.setText(result)
            self.hash_computed.emit(algo_name, result)
        except Exception as e:
            self._logger.error(f"文件哈希计算失败: {e}")
            self._result_input.setText(f"计算失败: {e}")

    def _compute_text_hash(self, text: str) -> None:
        """计算文本的哈希值"""
        if not text:
            return
        algo_name = self._algo_combo.currentText()
        algo_func = self._ALGORITHMS.get(algo_name)
        if algo_func is None:
            return

        hash_obj = algo_func(text.encode("utf-8"))
        result = hash_obj.hexdigest()
        self._result_input.setText(result)
        self.hash_computed.emit(algo_name, result)

    def _on_copy(self) -> None:
        """将计算结果复制到剪贴板"""
        result = self._result_input.text()
        if result:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(result)
