"""
文件服务模块 —— 文件打开、保存、重载、编码检测与最近文件管理

设计依据: doc/架构设计.md 2.3节 FileService, doc/功能设计.md 2.1节
"""

import os
from typing import List, Dict, Tuple, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from src.infrastructure.logger import get_logger
from src.infrastructure.file_io import FileIO
from src.infrastructure.encoding_detector import EncodingDetector
from src.infrastructure.encoding_utils import try_encode_content, force_encode_content
from src.infrastructure.settings import Settings
from src.infrastructure.app_constants import AppConstant


class FileService(QObject):
    """
    文件服务 —— 封装文件读写、编码检测、最近文件列表管理

    所有事件通过 SignalBus 统一广播，监听者只需连接 SignalBus。
    """

    # 大文件阈值（字节）
    LARGE_FILE_THRESHOLD = AppConstant.LARGE_FILE_THRESHOLD  # 10 MB

    # 最近文件列表最大条数
    MAX_RECENT_FILES = AppConstant.MAX_RECENT_FILES

    # 最近文件列表的配置键
    _RECENT_FILES_KEY = "recent_files"

    def __init__(self, signal_bus=None, parent: Optional[QObject] = None):
        """
        构造函数

        @param signal_bus: SignalBus 实例（必须），用于发射信号
        @param parent: Qt父对象
        """
        super().__init__(parent)
        self._logger = get_logger("FileService")
        self._settings = Settings()
        self._signal_bus = signal_bus

    def open_file(self, file_path: str, encoding: str = None) -> Tuple[str, str, str, Optional[str]]:
        """! @brief 打开文件，自动检测编码和换行符

        @param file_path 文件路径
        @param encoding  指定编码（None 表示自动检测）
        @return (文本内容, 编码名称, 换行符类型, 错误信息)
                成功时错误信息为None，换行符类型为 'LF'/'CRLF'/'CR'
        """
        file_path = os.path.abspath(file_path)

        # 检查文件是否存在
        if not FileIO.exists(file_path):
            err = f"文件不存在: {file_path}"
            self._logger.warning(err)
            return "", "utf-8", "LF", err

        # 检测编码（若指定了编码则优先使用，否则自动检测）
        if encoding is None:
            encoding, confidence = EncodingDetector.detect_from_file(file_path)
            self._logger.info(f"编码检测结果: {encoding} (置信度: {confidence:.2f})", file=file_path)
        else:
            self._logger.info(f"使用指定编码: {encoding}", file=file_path)

        # 读取文件内容
        content, err = FileIO.read_text(file_path, encoding=encoding)
        if err:
            self._logger.error(f"读取文件失败: {err}", file=file_path)
            return "", encoding, "LF", err

        # 检测换行符类型
        line_ending = self.detect_line_ending(content)

        # 更新最近文件列表
        self._add_recent_file(file_path)

        self._logger.info(f"文件已打开: {file_path}", encoding=encoding, line_ending=line_ending)
        if self._signal_bus:
            self._signal_bus.file_opened.emit(file_path)

        return content, encoding, line_ending, None

    def save_file(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
    ) -> Optional[str]:
        """
        保存文件内容

        @param file_path: 文件路径
        @param content: 文本内容
        @param encoding: 编码
        @return: 成功返回None，失败返回错误信息字符串
        """
        file_path = os.path.abspath(file_path)
        err = FileIO.write_text(file_path, content, encoding=encoding, safe=True)
        if err:
            self._logger.error(f"保存文件失败: {err}", file=file_path)
            return err

        # 更新最近文件列表
        self._add_recent_file(file_path)

        self._logger.info(f"文件已保存: {file_path}", encoding=encoding)
        if self._signal_bus:
            self._signal_bus.file_saved.emit(file_path)
        return None

    def reload_file(
        self,
        file_path: str,
        encoding: str = "utf-8",
    ) -> Tuple[str, Optional[str]]:
        """
        重新加载文件内容（不改变编码设置）

        @param file_path: 文件路径
        @param encoding: 编码
        @return: (文本内容, 错误信息)
        """
        file_path = os.path.abspath(file_path)
        content, err = FileIO.read_text(file_path, encoding=encoding)
        if err:
            self._logger.warning(f"重载文件失败: {err}", file=file_path)
            return "", err

        self._logger.info(f"文件已重载: {file_path}")
        return content, None

    def detect_encoding(self, file_path: str) -> str:
        """
        检测文件编码

        @param file_path: 文件路径
        @return: 编码名称
        """
        encoding, _ = EncodingDetector.detect_from_file(file_path)
        self._logger.info(f"编码检测: {file_path} -> {encoding}")
        return encoding

    @staticmethod
    def detect_line_ending(content: str) -> str:
        """
        检测文本内容中的换行符类型

        @param content: 文本内容
        @return: 'CRLF' / 'LF' / 'CR'，默认为 'LF'
        """
        if not content:
            return "LF"
        crlf_count = content.count("\r\n")
        lf_count = content.count("\n") - crlf_count
        cr_count = content.count("\r") - crlf_count

        max_count = max(crlf_count, lf_count, cr_count)
        if max_count == 0:
            return "LF"
        if max_count == crlf_count:
            return "CRLF"
        if max_count == lf_count:
            return "LF"
        return "CR"

    # —— 最近文件列表管理 ——

    def get_recent_files(self) -> List[str]:
        """
        获取最近文件列表

        @return: 文件路径列表，最多20条
        """
        data = self._settings.read("settings.json", {})
        files = data.get(self._RECENT_FILES_KEY, [])
        valid_files = [f for f in files if FileIO.exists(f)]
        if len(valid_files) != len(files):
            data[self._RECENT_FILES_KEY] = valid_files
            self._settings.write("settings.json", data)
        return valid_files[: self.MAX_RECENT_FILES]

    def _add_recent_file(self, file_path: str) -> None:
        """
        将文件路径添加到最近文件列表（去抖写入）

        @param file_path: 文件路径
        """
        data = self._settings.read("settings.json", {})
        files: List[str] = data.get(self._RECENT_FILES_KEY, [])
        files = [f for f in files if f != file_path]
        files.insert(0, file_path)
        files = files[: self.MAX_RECENT_FILES]
        data[self._RECENT_FILES_KEY] = files
        self._settings.write("settings.json", data)

    def remove_recent_file(self, file_path: str) -> None:
        """
        从最近文件列表中移除指定文件

        @param file_path: 文件路径
        """
        data = self._settings.read("settings.json", {})
        files: List[str] = data.get(self._RECENT_FILES_KEY, [])
        if file_path in files:
            files.remove(file_path)
            data[self._RECENT_FILES_KEY] = files
            self._settings.write("settings.json", data)
            self._logger.info(f"已从最近文件列表移除: {file_path}")

    def clear_recent_files(self) -> None:
        """
        清空最近文件列表
        """
        data = self._settings.read("settings.json", {})
        data[self._RECENT_FILES_KEY] = []
        self._settings.write("settings.json", data)
        self._logger.info("最近文件列表已清空")

    def change_encoding(
        self,
        file_path: str,
        content: str,
        target_encoding: str,
        force: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """! @brief 将文本内容编码为目标编码并原子写入文件

        编码转换的核心逻辑：
        1. 尝试将 Unicode 字符串编码为目标编码
        2. 编码成功后以原子写入方式写回原文件路径
        3. 编码失败时：
           - force=False：返回详细错误信息
           - force=True：清除无法编码的字符后继续写入

        @param file_path 文件路径（绝对路径）
        @param content Unicode 文本内容
        @param target_encoding 目标编码名称
        @param force 是否强制转换（清除不可编码字符）
        @return (成功标志, 错误消息)
                成功时错误消息为 None；失败时错误消息包含详细信息
        """
        file_path = os.path.abspath(file_path)

        # 尝试编码
        encoded_bytes, encode_err, bad_chars = try_encode_content(content, target_encoding)
        if encode_err:
            if not force:
                self._logger.error(
                    f"编码转换失败: 无法用 {target_encoding} 编码",
                    file=file_path,
                    bad_char_count=len(bad_chars) if bad_chars else 0,
                )
                return False, encode_err

            # 强制模式：清除无法编码的字符
            encoded_bytes, removed_count = force_encode_content(content, target_encoding)
            self._logger.warning(
                f"强制编码转换: 清除 {removed_count} 个无法编码的字符",
                file=file_path,
                target_encoding=target_encoding,
            )

        # 原子写入编码后的字节流
        try:
            from atomicwrites import atomic_write
            with atomic_write(file_path, mode="wb", overwrite=True) as f:
                f.write(encoded_bytes)
            self._logger.info(
                f"文件编码转换写入成功: {file_path}",
                target_encoding=target_encoding,
                byte_count=len(encoded_bytes),
            )
            return True, None
        except PermissionError:
            err = f"无法写入文件，可能被其他程序占用: {file_path}"
            self._logger.error(err)
            return False, err
        except OSError as e:
            err = f"写入文件失败: {e}"
            self._logger.error(err, file=file_path)
            return False, err