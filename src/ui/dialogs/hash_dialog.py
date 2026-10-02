"""哈希计算器对话框模块

使用 PyQt-Fluent-Widgets 的 MessageBoxBase 组件构建的哈希计算对话框，
支持 MD5、SHA1、SHA256 算法，计算结果可一键复制到剪贴板。
没有文本输入框，自动根据编辑器上下文计算哈希，支持选中文本/整个文件/整个文本切换。
文件保存由对话框的"计算"按钮触发，若文件有待保存修改则按钮显示"保存文件并计算"。
"""
import os
from typing import Callable, Optional

from PyQt5.QtWidgets import (
    QHBoxLayout, QWidget, QApplication,
)
from PyQt5.QtCore import Qt, QObject, QRunnable, QThreadPool, pyqtSignal

from qfluentwidgets import (
    MessageBoxBase, LineEdit, ComboBox,
    PrimaryPushButton, PushButton, BodyLabel,
)
from src.infrastructure.logger import get_logger
from src.service.tool_service import ToolService

_logger = get_logger("HashDialog")

# 哈希范围选项
_SCOPE_SELECTED = "选中文本"
_SCOPE_FILE = "整个文件"
_SCOPE_TEXT = "整个文本"


class _HashWorkerSignals(QObject):
    """! 哈希工作线程的结果回传信号

    在主线程创建、由工作线程发射，接收方（HashDialog）位于主线程，
    跨线程连接显式使用 Qt.QueuedConnection（规范 §6）。
    不设置 parent，生命周期由 HashDialog 与 _HashWorker 共同持有，
    即使对话框提前销毁也不会出现悬垂发射。
    """
    finished = pyqtSignal(str, str)  # (算法显示名, 哈希值)
    failed = pyqtSignal(str)         # (错误信息)


class _HashWorker(QRunnable):
    """! 文件哈希计算任务

    通过 QThreadPool 在工作线程中分块读取文件并计算哈希，
    避免大文件计算阻塞 UI 线程（规范 §6 并发模型）。
    """

    def __init__(self, signals: _HashWorkerSignals, algo_name: str,
                 file_path: str, algorithm: str):
        """! 构造函数

        @param signals  结果回传信号对象（由对话框持有引用）
        @param algo_name 算法显示名，如 "MD5"
        @param file_path 目标文件路径
        @param algorithm 算法标识，如 "md5"
        """
        super().__init__()
        self._signals = signals
        self._algo_name = algo_name
        self._file_path = file_path
        self._algorithm = algorithm

    def run(self) -> None:
        """! 工作线程入口：执行计算并回传结果"""
        try:
            result = ToolService.compute_file_hash(self._file_path, self._algorithm)
            self._signals.finished.emit(self._algo_name, result)
        except Exception as e:
            self._signals.failed.emit(str(e))


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
        "MD5": "md5",
        "SHA1": "sha1",
        "SHA256": "sha256",
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
        self._running = False
        # 工作线程回传信号：不设 parent，由对话框与任务共同持有
        self._worker_signals = _HashWorkerSignals()
        self._worker_signals.finished.connect(
            self._on_hash_finished, Qt.QueuedConnection
        )
        self._worker_signals.failed.connect(
            self._on_hash_failed, Qt.QueuedConnection
        )
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
        if self._running:
            # 上一次文件哈希尚未完成，忽略重复请求
            self._result_input.setPlaceholderText("计算中...")
            return
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
        """计算文件哈希：提交到线程池异步执行，避免阻塞 UI 线程"""
        algo_name = self._algo_combo.currentText()
        algorithm = self._ALGORITHMS.get(algo_name)
        if algorithm is None:
            return

        self._running = True
        self._compute_btn.setEnabled(False)
        self._result_input.setPlaceholderText("计算中...")
        worker = _HashWorker(
            self._worker_signals, algo_name, self._file_path, algorithm
        )
        QThreadPool.globalInstance().start(worker)

    def _compute_text_hash(self, text: str) -> None:
        """计算文本的哈希值（内存操作，同步执行）"""
        if not text:
            return
        algo_name = self._algo_combo.currentText()
        algorithm = self._ALGORITHMS.get(algo_name)
        if algorithm is None:
            return

        result = ToolService.compute_hash(text, algorithm)
        if not result:
            self._result_input.setText(f"不支持的算法: {algo_name}")
            return
        self._result_input.setText(result)
        self.hash_computed.emit(algo_name, result)

    def _on_hash_finished(self, algo_name: str, result: str) -> None:
        """! 工作线程计算完成槽（QueuedConnection 回到主线程）"""
        self._running = False
        self._compute_btn.setEnabled(True)
        self._result_input.setText(result)
        self.hash_computed.emit(algo_name, result)

    def _on_hash_failed(self, error: str) -> None:
        """! 工作线程计算失败槽（QueuedConnection 回到主线程）"""
        self._running = False
        self._compute_btn.setEnabled(True)
        self._logger.error(f"文件哈希计算失败: {error}")
        self._result_input.setText(f"计算失败: {error}")

    def _on_copy(self) -> None:
        """将计算结果复制到剪贴板"""
        result = self._result_input.text()
        if result:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(result)
