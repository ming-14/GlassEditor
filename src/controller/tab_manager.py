"""
标签页管理器 —— 管理编辑器标签生命周期

设计依据: docs/开发规范/设计架构规范.md 3.3节 TabManager, docs/开发规范/信息架构文档.md 3.2节文件打开
"""

import os
from typing import Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from PyQt5.QtCore import QObject, pyqtSignal, QFileSystemWatcher, QTimer

from src.infrastructure.logger import get_logger
from src.service.syntax_service import SyntaxService
from src.service.syntax_highlighter_manager import SyntaxHighlighterManager
from src.controller.signal_bus import SignalBus

if TYPE_CHECKING:
    from PyQt5.QtGui import QSyntaxHighlighter
    from src.ui.editor_tab_widget import EditorTabWidget
    from src.ui.code_editor import CodeEditor
    from src.service.file_service import FileService
    from src.service.config_service import ConfigService


class TabManager(QObject):
    """
    标签页管理器 —— 管理编辑器标签的创建、关闭、切换

    依赖 EditorTabWidget 作为标签容器，FileService 用于文件操作。
    每个标签绑定一个 CodeEditor 编辑器实例。

    修改状态同步机制:
        编辑器的修改状态由 Qt 文档的 isModified() 驱动，
        通过 modificationChanged 信号传播到标签元数据["modified"]。
        mark_saved() 会同时重置文档修改状态与元数据，确保二者始终同步。

    元数据存储:
        使用 QTabWidget.setTabData()/tabData() 存储每个标签的元数据字典，
        与 Qt 标签索引自动同步，无需手动维护并行索引字典。

    信号:
        tab_created(int):      标签创建后发射，参数为标签索引
        tab_closed(int):       标签关闭后发射，参数为标签索引
        tab_switched(int):     标签切换后发射，参数为新标签索引
        file_externally_modified(str): 文件被外部修改，参数为文件路径
    """

    # —— 信号定义 ——
    tab_created = pyqtSignal(int)
    tab_closed = pyqtSignal(int)
    tab_switched = pyqtSignal(int)
    file_externally_modified = pyqtSignal(str)

    def __init__(
        self,
        tab_widget: "EditorTabWidget",
        file_service: "FileService",
        editor_factory: Callable[[], "CodeEditor"],
        highlighter_manager: SyntaxHighlighterManager,
        signal_bus: SignalBus = None,
        parent: Optional[QObject] = None,
    ):
        """
        构造函数

        @param tab_widget: 编辑器标签页控件
        @param file_service: 文件服务
        @param editor_factory: 编辑器工厂，调用返回 CodeEditor 实例
        @param highlighter_manager: 语法高亮器管理器（Service 层），替代原来的 highlighter_factory
        @param signal_bus: SignalBus 实例（可选），用于转发 file_closed 信号
        @param parent: Qt父对象
        """
        super().__init__(parent)
        self._logger = get_logger("TabManager")
        self._tab_widget = tab_widget
        self._file_service = file_service
        self._editor_factory = editor_factory
        self._highlighter_manager = highlighter_manager
        self._signal_bus = signal_bus

        self._current_editor_colors: Optional[Dict[str, str]] = None

        self._highlighter_store: Dict[int, QSyntaxHighlighter] = {}

        self._syntax_service = SyntaxService()

        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_externally_changed)

        self._config_service: "ConfigService | None" = None

        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setInterval(30000)
        self._auto_save_timer.timeout.connect(self._do_auto_save_session)

        self._logger.debug("TabManager 已初始化")

    # ========================================================================
    # 元数据辅助方法
    # ========================================================================

    def _get_meta(self, index: int) -> Optional[Dict]:
        if index < 0 or index >= self._tab_widget.count():
            return None
        data = self._tab_widget.tabData(index)
        if not isinstance(data, dict):
            return None
        highlighter = self._highlighter_store.get(index)
        if highlighter is not None:
            data["highlighter"] = highlighter
        return data

    def _set_meta(self, index: int, meta: Dict) -> None:
        highlighter = meta.pop("highlighter", None)
        if highlighter is not None:
            self._highlighter_store[index] = highlighter
        self._tab_widget.setTabData(index, meta)

    # ========================================================================
    # 标签创建与关闭
    # ========================================================================

    def create_tab(
        self,
        file_path: Optional[str] = None,
        content: str = "",
        encoding: str = "utf-8",
        file_size: int = 0,
        language: Optional[str] = None,
        syntax_auto_detect: bool = True,
    ) -> int:
        """
        创建新标签页

        @param file_path: 文件路径（新建文件时为 None）
        @param content: 初始文本内容
        @param encoding: 文件编码
        @param file_size: 文件大小（字节），用于决定是否启用语法高亮
        @param language: 语言名称，为 None 时根据扩展名自动检测
        @param syntax_auto_detect: 是否启用自动识别
        @return: 新标签的索引
        """
        # 确定标签标题
        title = os.path.basename(file_path) if file_path else "未命名"

        # 创建编辑器实例（通过依赖注入的工厂方法）
        editor = self._editor_factory()
        editor.setPlainText(content)
        # 会话恢复时 setPlainText 会触发 modificationChanged 信号，
        # 导致标签被误标记为"已修改"，此处显式重置文档修改状态
        editor.document().setModified(False)

        # 创建语法高亮器：优先使用传入的 language，否则根据扩展名自动检测
        if language is not None:
            pass  # 使用传入的 language
        elif file_path:
            ext = os.path.splitext(file_path)[1]
            language = self._syntax_service.get_language(ext)
        else:
            language = ""

        self._logger.debug(f"[高亮] create_tab 语法解析 | file_path={file_path!r}, ext={os.path.splitext(file_path)[1] if file_path else 'N/A'}, language={language!r}")

        syntax_colors = None
        if self._current_editor_colors:
            syntax_colors = self._current_editor_colors.get("syntax_colors")

        highlighter = self._highlighter_manager.apply_to_editor(
            language, editor, file_size, syntax_colors
        )

        self._logger.debug(f"[高亮] create_tab 高亮器创建 | language={language!r}, highlighter_type={type(highlighter).__name__ if highlighter else 'None'}")

        # 添加到标签控件
        index = self._tab_widget.add_editor_tab(editor, title)

        # 记录元数据 —— 必须紧跟在 add_editor_tab 之后，
        # 确保后续任何信号处理（如 add_editor_tab 内部触发的
        # currentChanged → tab_changed → _on_tab_changed）
        # 都能正确读取到元数据，避免因元数据未就绪导致状态栏
        # 等组件获取到错误的状态（已打开的文件被误标记为"未保存"）。
        self._set_meta(index, {
            "file_path": file_path,
            "encoding": encoding,
            "modified": False,
            "file_size": file_size,
            "language": language,
            "highlighter": highlighter,
            "syntax_auto_detect": syntax_auto_detect,
        })

        # 应用当前编辑器配色（如果有）
        if self._current_editor_colors:
            editor.set_editor_colors(self._current_editor_colors)

        # 添加文件到系统监视器
        if file_path and os.path.exists(file_path):
            self._watcher.addPath(file_path)

        self._logger.info(f"标签已创建: [{index}] {title}", file_path=str(file_path))
        self.tab_created.emit(index)
        return index

    def close_tab(self, index: int) -> bool:
        """
        关闭指定标签页

        如果标签有未保存的修改，调用方应在此之前询问用户是否保存。

        @param index: 标签索引
        @return: 是否成功关闭（False 表示索引无效）
        """
        if index < 0 or index >= self._tab_widget.count():
            self._logger.warning(f"关闭标签失败: 索引 {index} 超出范围")
            return False

        meta = self._get_meta(index)
        if meta is None:
            self._logger.warning(f"关闭标签失败: 索引 {index} 无元数据")
            return False
        file_path = meta.get("file_path")
        title = os.path.basename(file_path) if file_path else "未命名"

        # 从文件监视器中移除
        if file_path and file_path in self._watcher.files():
            self._watcher.removePath(file_path)

        # 移除标签（Qt 自动移除 tabData，无需手动重索引）
        self._tab_widget.remove_tab(index)

        # 清理高亮器引用并重索引
        self._highlighter_store.pop(index, None)
        new_store = {}
        for k, v in self._highlighter_store.items():
            new_store[k - 1 if k > index else k] = v
        self._highlighter_store = new_store

        self._logger.info(f"标签已关闭: [{index}] {title}")
        self.tab_closed.emit(index)

        if file_path and self._signal_bus:
            self._signal_bus.file_closed.emit(file_path)

        return True

    # ========================================================================
    # 获取编辑器与文件信息
    # ========================================================================

    def get_current_index(self) -> int:
        """
        获取当前激活标签的索引

        @return: 当前标签索引，无标签时返回 -1
        """
        return self._tab_widget.currentIndex()

    def get_current_editor(self) -> Optional["CodeEditor"]:
        """
        获取当前激活标签的编辑器

        @note 此方法仅返回标签页对应的编辑器。
              需要获取含分屏的活跃编辑器时，请使用 FocusManager.get_active_editor()。

        @return: CodeEditor 实例，无编辑器时返回 None
        """
        current = self._tab_widget.currentIndex()
        if current < 0:
            return None
        return self.get_editor(current)

    def get_current_file_path(self) -> Optional[str]:
        """
        获取当前激活标签的文件路径

        @note 此方法仅返回标签页对应的文件路径。
              需要获取含分屏的活跃文件路径时，请使用 FocusManager.get_active_file_path()。

        @return: 文件路径字符串，新建文件或无标签时返回 None
        """
        current = self._tab_widget.currentIndex()
        if current < 0:
            return None
        return self.get_file_path(current)

    def get_editor(self, index: int) -> Optional["CodeEditor"]:
        """
        获取指定索引的编辑器

        @param index: 标签索引
        @return: CodeEditor 实例，索引无效时返回 None
        """
        return self._tab_widget.get_editor(index)

    def get_file_path(self, index: int) -> Optional[str]:
        """
        获取指定索引的文件路径

        @param index: 标签索引
        @return: 文件路径字符串，索引无效时返回 None
        """
        meta = self._get_meta(index)
        if meta is None:
            return None
        return meta.get("file_path")

    def find_index_by_editor(self, editor: "CodeEditor") -> int:
        """
        根据编辑器实例查找当前标签索引

        通过 QTabWidget.indexOf 动态查找，不受标签关闭重索引影响。

        @param editor: CodeEditor 实例
        @return: 标签索引，未找到返回 -1
        """
        if editor is None:
            return -1
        return self._tab_widget.index_of(editor)

    # ========================================================================
    # 标签状态管理
    # ========================================================================

    def set_tab_modified(self, index: int, modified: bool) -> None:
        """
        设置标签的修改标记（在标题显示 * 号）

        同时同步编辑器文档的修改状态，确保 Qt 文档的 isModified()
        与标签元数据["modified"] 始终一致。

        @param index: 标签索引
        @param modified: True 表示已修改，False 表示未修改
        """
        if index < 0 or index >= self._tab_widget.count():
            return
        meta = self._get_meta(index)
        if meta is None:
            return
        meta["modified"] = modified
        self._set_meta(index, meta)
        self._tab_widget.set_tab_modified(index, modified)

        # 同步编辑器文档修改状态，避免 Qt 内部状态与元数据不一致
        editor = self.get_editor(index)
        if editor and editor.document().isModified() != modified:
            editor.document().setModified(modified)

    def mark_saved(self, index: int, file_path: str) -> None:
        """
        标记标签为已保存状态

        同时重置编辑器文档的修改状态，确保后续编辑能正确触发
        modificationChanged 信号。

        @param index: 标签索引
        @param file_path: 保存后的文件路径
        """
        if index < 0 or index >= self._tab_widget.count():
            return
        meta = self._get_meta(index)
        if meta is None:
            meta = {}
            self._set_meta(index, meta)

        # 如果是另存为（路径发生变化），更新文件监视器
        old_path = meta.get("file_path")
        if old_path and old_path != file_path:
            if old_path in self._watcher.files():
                self._watcher.removePath(old_path)
                self._logger.debug(f"文件监视器已移除旧路径: {old_path}")
            if os.path.exists(file_path):
                self._watcher.addPath(file_path)
                self._logger.debug(f"文件监视器已添加新路径: {file_path}")
        elif not old_path:
            # 新建文件首次保存，添加到监视器
            if os.path.exists(file_path) and file_path not in self._watcher.files():
                self._watcher.addPath(file_path)
                self._logger.debug(f"文件监视器已添加新路径: {file_path}")
        else:
            # 正常保存（路径未变），恢复被 pause_file_watcher 暂停的监视
            self.resume_file_watcher(file_path)

        old_path_for_lang = meta.get("file_path")
        path_changed = (old_path_for_lang != file_path)

        meta["file_path"] = file_path
        meta["modified"] = False
        self._set_meta(index, meta)
        self._tab_widget.set_tab_modified(index, False)

        title = os.path.basename(file_path)
        self._tab_widget.set_tab_title(index, title)

        if path_changed:
            ext = os.path.splitext(file_path)[1]
            new_language = self._syntax_service.get_language(ext)
            old_language = meta.get("language", "")

            self._logger.debug(f"[高亮] 保存时语言检测 | index={index}, ext={ext!r}, new_language={new_language!r}, old_language={old_language!r}")

            auto_detect = meta.get("syntax_auto_detect", True)
            if new_language and new_language != old_language and auto_detect:
                self._logger.info(
                    f"标签 [{index}] 语言变更: {old_language or '(无)'} -> {new_language}"
                )
                old_highlighter = meta.get("highlighter")
                editor = self.get_editor(index)
                if editor:
                    new_highlighter = self._highlighter_manager.apply_language_to_editor(
                        new_language,
                        editor,
                        meta.get("file_size", 0),
                        self._current_editor_colors,
                        old_highlighter,
                    )
                    self._logger.debug(
                        f"[高亮] 语言变更高亮器重建 | "
                        f"type={type(new_highlighter).__name__ if new_highlighter else 'None'}"
                    )
                    if new_highlighter:
                        meta["highlighter"] = new_highlighter
                        meta["language"] = new_language
                        self._set_meta(index, meta)

        # 重置编辑器文档修改状态，确保后续编辑能正确触发 modificationChanged
        editor = self.get_editor(index)
        if editor:
            editor.document().setModified(False)

        self._logger.info(f"标签已保存: [{index}] {file_path}")

    def is_tab_modified(self, index: int) -> bool:
        """
        查询指定标签是否有未保存的修改

        优先检查元数据中的修改标记，同时校验编辑器文档的实际修改状态，
        确保二者不一致时仍能返回正确结果。

        @param index: 标签索引
        @return: 已修改返回 True，索引无效返回 False
        """
        meta = self._get_meta(index)
        if meta is None:
            return False
        # 元数据标记为已修改，直接返回
        if meta.get("modified", False):
            return True
        # 元数据标记为未修改，但文档实际已修改（状态不同步），
        # 以文档状态为准并同步元数据
        editor = self.get_editor(index)
        if editor and editor.document().isModified():
            meta["modified"] = True
            self._set_meta(index, meta)
            self._tab_widget.set_tab_modified(index, True)
            self._logger.debug(f"标签修改状态已同步: [{index}] -> 已修改")
            return True
        return False

    # ========================================================================
    # 查询方法
    # ========================================================================

    def get_language(self, extension: str) -> str:
        """! 获取文件扩展名对应的语言名称

        公开接口，供上层通过 TabManager 查询语言信息，
        避免直接访问 _syntax_service 私有属性。

        @param extension 文件扩展名（含点号，如 ".py"）
        @return 语言名称，未匹配返回空字符串
        """
        return self._syntax_service.get_language(extension)

    def get_available_languages(self) -> List[str]:
        """! 获取所有支持的语言列表

        @return 语言名称列表
        """
        return self._syntax_service.get_available_languages()

    def tab_count(self) -> int:
        """!@brief 获取当前文件标签总数（不含欢迎页标签）

        @return 文件标签数量
        """
        total = self._tab_widget.count()
        welcome_count = sum(
            1 for i in range(total)
            if self._tab_widget.is_welcome_tab(i)
        )
        return total - welcome_count

    def get_unsaved_tabs(self) -> List[Dict]:
        """
        获取所有未保存标签的信息

        @return: 列表，每项为 {"index": int, "title": str, "file_path": str|None}
        """
        unsaved: List[Dict] = []
        for i in range(self._tab_widget.count()):
            if self._tab_widget.is_welcome_tab(i):
                continue
            if self.is_tab_modified(i):
                meta = self._get_meta(i)
                title = self._tab_widget.tabText(i)
                unsaved.append({
                    "index": i,
                    "title": title,
                    "file_path": meta.get("file_path") if meta else None,
                })
        return unsaved

    def find_tab_by_path(self, file_path: str) -> int:
        """
        根据文件路径查找标签索引

        @param file_path: 文件路径
        @return: 标签索引，未找到返回 -1
        """
        file_path = os.path.abspath(file_path)
        for i in range(self._tab_widget.count()):
            meta = self._get_meta(i)
            if meta is None:
                continue
            fp = meta.get("file_path")
            if fp and os.path.abspath(fp) == file_path:
                return i
        return -1

    def get_untitled_count(self) -> int:
        """
        获取未命名（新建未保存）标签的数量

        @return: 未命名标签数量
        """
        count = 0
        for i in range(self._tab_widget.count()):
            meta = self._get_meta(i)
            if meta and meta.get("file_path") is None:
                count += 1
        return count

    def get_current_encoding(self) -> str:
        """
        获取当前标签的编码

        @return: 编码名称，默认为 'utf-8'
        """
        index = self.get_current_index()
        if index < 0:
            return "utf-8"
        meta = self._get_meta(index)
        if meta is None:
            return "utf-8"
        return meta.get("encoding", "utf-8")

    def get_tab_meta(self, index: int) -> Optional[Dict]:
        """
        获取指定标签的元数据字典

        @param index: 标签索引
        @return: 元数据字典，索引无效时返回 None
        """
        return self._get_meta(index)

    def set_config_service(self, config_service: "ConfigService") -> None:
        """
        设置配置服务引用（用于会话自动保存）

        @param config_service: ConfigService 实例
        """
        self._config_service = config_service
        self._auto_save_timer.start()

    def set_editor_colors(self, colors: Dict[str, str]) -> None:
        """
        设置当前编辑器配色并应用到所有已有编辑器

        @param colors: CodeEditor 所需的配色字典
        """
        self._logger.debug(f"[高亮] set_editor_colors 被调用 | colors_keys={list(colors.keys()) if colors else []}")
        self._current_editor_colors = colors
        syntax_colors = colors.get("syntax_colors") if colors else None

        for i in range(self._tab_widget.count()):
            if self._tab_widget.is_welcome_tab(i):
                continue
            editor = self.get_editor(i)
            if editor:
                editor.set_editor_colors(colors)

            meta = self._get_meta(i)
            if meta and meta.get("highlighter"):
                self._highlighter_manager.update_highlighter_colors(
                    meta["highlighter"], syntax_colors
                )

    def get_current_editor_colors(self) -> Optional[Dict[str, str]]:
        """! @brief 获取当前编辑器配色字典

        @return 当前配色字典，未设置时返回 None
        """
        return self._current_editor_colors

    def set_tab_meta(self, index: int, meta: Dict) -> None:
        """! @brief 设置指定标签的元数据

        公共接口，替代直接访问 _set_meta 私有方法。

        @param index 标签索引
        @param meta 元数据字典
        """
        self._set_meta(index, meta)

    # ========================================================================
    # 会话自动保存
    # ========================================================================

    def save_full_session(self) -> None:
        """
        保存完整会话快照（供 MainWindow 关闭时调用）

        遍历所有文件标签页，保存每个标签的文件路径、光标位置、编码及内容。
        未保存文件（无路径）的内容会被完整保存，以便下次启动恢复。
        已保存文件的内容也会被保存，用于恢复未保存的修改。
        """
        if self._config_service is None:
            return

        try:
            open_files = []
            for i in range(self._tab_widget.count()):
                if self._tab_widget.is_welcome_tab(i):
                    continue
                meta = self._get_meta(i)
                if meta is None:
                    continue
                editor = self.get_editor(i)
                cursor_pos = 0
                content = ""
                if editor is not None:
                    cursor_pos = editor.textCursor().position()
                    content = editor.toPlainText()

                file_path = meta.get("file_path", "")
                is_modified = meta.get("modified", False)

                open_files.append({
                    "path": file_path or "",
                    "cursor_pos": cursor_pos,
                    "encoding": meta.get("encoding", "utf-8"),
                    "content": content,
                    "modified": is_modified,
                    "language": meta.get("language", ""),
                    "syntax_auto_detect": meta.get("syntax_auto_detect", True),
                })

            self._config_service.save_session(open_files)
            self._logger.info(f"完整会话已保存: {len(open_files)} 个文件")
        except Exception as e:
            self._logger.error(f"保存完整会话失败: {e}")

    def _do_auto_save_session(self) -> None:
        """
        自动保存当前会话

        每30秒触发一次，将当前打开的文件列表保存到 ConfigService。
        仅对有未保存修改的文件获取 toPlainText()，未修改文件跳过，
        避免大文件无谓的序列化开销。
        """
        if self._config_service is None:
            return

        try:
            open_files = []
            for i in range(self._tab_widget.count()):
                if self._tab_widget.is_welcome_tab(i):
                    continue
                meta = self._get_meta(i)
                if meta is None:
                    continue
                editor = self.get_editor(i)
                cursor_pos = 0
                content = ""
                if editor is not None:
                    cursor_pos = editor.textCursor().position()

                file_path = meta.get("file_path", "")
                is_modified = meta.get("modified", False)

                if not file_path or is_modified:
                    content = editor.toPlainText() if editor is not None else ""

                open_files.append({
                    "path": file_path or "",
                    "cursor_pos": cursor_pos,
                    "encoding": meta.get("encoding", "utf-8"),
                    "content": content,
                    "modified": is_modified,
                    "language": meta.get("language", ""),
                    "syntax_auto_detect": meta.get("syntax_auto_detect", True),
                })

            self._config_service.save_session(open_files)
            self._logger.debug(f"会话已自动保存: {len(open_files)} 个文件")
        except Exception as e:
            self._logger.error(f"会话自动保存失败: {e}")

    # ========================================================================
    # 编码转换
    # ========================================================================

    def change_encoding_for_tab(self, index: int, target_encoding: str, force: bool = False) -> Tuple[bool, Optional[str]]:
        """! @brief 对指定标签执行编码转换

        编码转换流程（方案A）：
        1. 检查前置条件（路径存在、非只读）
        2. 如有未保存修改，先自动保存当前文件
        3. 暂停文件系统监听
        4. 获取编辑器全文并调用 FileService.change_encoding
        5. 成功后更新 TabEntity.encoding，不重新加载编辑器内容
        6. 恢复文件监听
        7. 发射 SignalBus.file_encoding_changed 信号

        @param index 标签索引
        @param target_encoding 目标编码名称（内部名，如 'utf-8-sig'）
        @param force 是否强制转换（清除不可编码字符）
        @return (成功标志, 错误消息)
        """
        if index < 0 or index >= self._tab_widget.count():
            return False, "无效的标签索引"

        meta = self._get_meta(index)
        if meta is None:
            return False, "无法获取标签元数据"

        file_path = meta.get("file_path")
        if not file_path:
            return False, "未保存的文件无法更改编码"

        old_encoding = meta.get("encoding", "utf-8")
        if old_encoding == target_encoding:
            return True, None

        editor = self.get_editor(index)
        if editor is None:
            return False, "无法获取编辑器实例"

        # 如有未保存修改，先自动保存
        if meta.get("modified", False):
            content = editor.toPlainText()
            save_err = self._file_service.save_file(file_path, content, encoding=old_encoding)
            if save_err:
                self._logger.error(f"编码转换前自动保存失败: {save_err}", file=file_path)
                return False, f"保存失败: {save_err}"
            self.mark_saved(index, file_path)
            self._logger.info("编码转换前自动保存成功", file=file_path)

        # 暂停文件系统监听
        self.pause_file_watcher(file_path)

        # 获取当前编辑器全文
        content = editor.toPlainText()

        # 调用 FileService 执行编码转换
        success, err = self._file_service.change_encoding(file_path, content, target_encoding, force=force)

        if not success:
            self.resume_file_watcher(file_path)
            self._logger.error(f"编码转换失败: {err}", file=file_path)
            return False, err

        # 更新 TabEntity.encoding
        meta["encoding"] = target_encoding
        self._set_meta(index, meta)

        # 恢复文件监听
        self.resume_file_watcher(file_path)

        # 发射编码变更信号
        if self._signal_bus:
            self._signal_bus.file_encoding_changed.emit(file_path, target_encoding)

        self._logger.info(
            f"文件编码转换: {file_path} from {old_encoding} to {target_encoding}"
        )
        return True, None

    # ========================================================================
    # 文件系统监视
    # ========================================================================

    def pause_file_watcher(self, file_path: str) -> None:
        """
        暂停对指定文件的监视（保存前调用，避免原子写入触发外部修改信号）

        @param file_path: 文件路径
        """
        if file_path and file_path in self._watcher.files():
            self._watcher.removePath(file_path)
            self._logger.debug(f"文件监视已暂停: {file_path}")

    def resume_file_watcher(self, file_path: str) -> None:
        """
        恢复对指定文件的监视（保存后调用）

        @param file_path: 文件路径
        """
        if file_path and os.path.exists(file_path):
            if file_path not in self._watcher.files():
                self._watcher.addPath(file_path)
                self._logger.debug(f"文件监视已恢复: {file_path}")

    def _on_file_externally_changed(self, file_path: str) -> None:
        """
        文件被外部修改时的处理

        发射 file_externally_modified 信号通知上层处理。

        @param file_path: 被修改的文件路径
        """
        self._logger.info(f"检测到外部文件修改: {file_path}")
        self.file_externally_modified.emit(file_path)

    # ========================================================================
    # 标签切换
    # ========================================================================

    def switch_to_tab(self, index: int) -> bool:
        """
        切换到指定标签

        @param index: 目标标签索引
        @return: 是否切换成功（False 表示索引无效）
        """
        if index < 0 or index >= self._tab_widget.count():
            self._logger.warning(f"切换标签失败: 索引 {index} 超出范围")
            return False

        self._tab_widget.setCurrentIndex(index)
        self._logger.debug(f"已切换到标签: [{index}]")
        self.tab_switched.emit(index)
        return True

    # ========================================================================
    # 内部辅助
    # ========================================================================
