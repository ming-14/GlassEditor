"""
基础文件IO模块 -- 底层文件读写能力

设计依据: doc/架构设计.md 2.4节 FileIO
"""

from pathlib import Path
from typing import Optional, Tuple

from atomicwrites import atomic_write

from src.infrastructure.logger import get_logger

_logger = get_logger("FileIO")


class FileIO:
    """
    底层文件读写封装

    支持文本模式读取，原子安全写入。
    安全写入通过 atomicwrites 库实现 tempfile + os.replace 的原子替换模式，
    避免写入中断导致文件损坏。
    """

    @classmethod
    def read_text(
        cls,
        file_path: str,
        encoding: str = "utf-8",
        max_size: Optional[int] = None,
    ) -> Tuple[str, Optional[str]]:
        """
        以文本模式读取文件

        @param file_path: 文件路径
        @param encoding: 编码
        @param max_size: 最大读取字节数，超过则截断（None表示不限制）
        @return: (内容, 错误信息)，成功时错误信息为None
        """
        path = Path(file_path)
        if not path.exists():
            return "", f"文件不存在: {file_path}"
        if not path.is_file():
            return "", f"路径不是文件: {file_path}"
        try:
            file_size = path.stat().st_size
            with open(path, "r", encoding=encoding, errors="replace") as f:
                if max_size and file_size > max_size:
                    content = f.read(max_size)
                else:
                    content = f.read()
            return content, None
        except UnicodeDecodeError:
            return "", f"无法以 {encoding} 解码文件"
        except PermissionError:
            return "", f"无权读取文件: {file_path}"
        except OSError as e:
            return "", f"读取文件失败: {e}"

    @classmethod
    def write_text(
        cls,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        safe: bool = True,
    ) -> Optional[str]:
        """
        以文本模式写入文件

        @param file_path: 文件路径
        @param content: 文本内容
        @param encoding: 编码
        @param safe: 是否使用原子安全写入（先写临时文件再原子替换）
        @return: 成功返回None，失败返回错误信息
        """
        try:
            if safe:
                with atomic_write(
                    file_path, mode="w", overwrite=True, encoding=encoding
                ) as f:
                    f.write(content)
            else:
                with open(file_path, "w", encoding=encoding) as f:
                    f.write(content)
            return None
        except PermissionError:
            _logger.warning(f"无权写入文件: {file_path}")
            return f"无权写入文件: {file_path}"
        except OSError as e:
            _logger.warning(f"写入文件失败: {e}")
            return f"写入文件失败: {e}"

    @classmethod
    def get_file_size(cls, file_path: str) -> int:
        """获取文件大小（字节），文件不存在返回-1"""
        path = Path(file_path)
        if path.exists() and path.is_file():
            return path.stat().st_size
        return -1

    @classmethod
    def exists(cls, file_path: str) -> bool:
        """检查文件是否存在"""
        return Path(file_path).is_file()


