"""! @brief 单实例守护模块

基于 QSharedMemory 进程锁 + QLocalServer IPC 实现单实例保障。
新启动的实例检测已有实例后，通过 IPC 委托操作（打开文件等），自身退出。

帧协议: [4字节大端N][N字节UTF-8 JSON]
"""

import json
import struct
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal, QSharedMemory
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

from src.infrastructure.app_constants import AppConstant
from src.infrastructure.logger import get_logger


class SingleInstanceGuard(QObject):
    """! @brief 单实例守护

    通过 QSharedMemory 进程锁和 QLocalServer IPC 通信
    确保应用仅运行一个实例，第二实例通过 IPC 委托操作。

    @var message_received: 当收到其他实例发来的 IPC 消息时发射
    """

    message_received = pyqtSignal(dict)

    def __init__(self, server_name: str = AppConstant.IPC_SERVER_NAME):
        """! @brief 构造单实例守护

        @param server_name IPC 服务器名称，同时用作 QSharedMemory 键名
        """
        super().__init__()
        self._logger = get_logger("SingleInstanceGuard")
        self._server_name = server_name
        self._shared_mem = QSharedMemory(server_name)
        self._server = QLocalServer()

    def try_lock(self) -> bool:
        """! @brief 尝试获取单实例锁

        首次调用时尝试创建 QSharedMemory 锁并启动 IPC 服务器。
        若已有实例运行则返回 False。

        @return True 表示获取锁成功（本进程为主实例），False 表示已有实例运行
        """
        if self._shared_mem.attach():
            self._logger.info("检测到已有实例运行 (QSharedMemory 已存在)")
            self._shared_mem.detach()
            return False

        if self._shared_mem.error() == QSharedMemory.AlreadyExists:
            self._logger.warning("检测到崩溃残留的 QSharedMemory 锁，尝试清理")
            if self._shared_mem.attach():
                self._shared_mem.detach()
            if not self._shared_mem.create(1):
                self._logger.error(
                    f"清理残留锁后仍无法创建 QSharedMemory: "
                    f"{self._shared_mem.errorString()}"
                )
                return False
        else:
            if not self._shared_mem.create(1):
                self._logger.error(
                    f"无法创建 QSharedMemory: {self._shared_mem.errorString()}"
                )
                return False

        if not self._server.listen(self._server_name):
            self._logger.error(
                f"IPC 服务器监听失败: {self._server.errorString()}"
            )
            if self._shared_mem.isAttached():
                self._shared_mem.detach()
            return False

        self._server.newConnection.connect(self._on_new_connection)
        self._logger.info(
            f"单实例锁定成功, IPC 服务器已启动: {self._server_name}"
        )
        return True

    def send_message(self, data: dict) -> bool:
        """! @brief 向主实例发送 IPC 消息

        由第二实例调用，将操作请求发送给已运行的主实例。

        @param data 消息字典，需包含 "action" 字段
        @return True 表示消息发送成功，False 表示发送失败
        """
        socket = QLocalSocket()
        socket.connectToServer(self._server_name)

        if not socket.waitForConnected(AppConstant.IPC_TIMEOUT_MS):
            self._logger.error(
                f"IPC 连接超时: {socket.errorString()}"
            )
            socket.disconnectFromServer()
            return False

        json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        header = struct.pack("!I", len(json_bytes))
        frame = header + json_bytes

        socket.write(frame)
        if not socket.waitForBytesWritten(AppConstant.IPC_TIMEOUT_MS):
            self._logger.error(
                f"IPC 数据写入超时: {socket.errorString()}"
            )
            socket.disconnectFromServer()
            return False

        if not socket.waitForReadyRead(AppConstant.IPC_TIMEOUT_MS):
            self._logger.warning("IPC 确认读取超时，消息可能已送达")
            socket.disconnectFromServer()
            return True

        socket.disconnectFromServer()
        self._logger.info(f"IPC 消息已发送: {data.get('action', '未知')}")
        return True

    def release(self):
        """! @brief 释放单实例锁

        关闭 IPC 服务器并释放 QSharedMemory，供退出时调用。
        """
        try:
            self._server.close()
            if self._shared_mem.isAttached():
                self._shared_mem.detach()
            self._logger.info("单实例守护已释放")
        except Exception as e:
            self._logger.error(f"释放单实例锁时异常: {e}")

    def _on_new_connection(self):
        """! @brief 处理新的 IPC 连接

        当第二实例连接到本实例的 IPC 服务器时触发，
        读取并解析其发送的消息。
        """
        socket = self._server.nextPendingConnection()
        if socket is None:
            self._logger.warning("IPC 接收到空连接")
            return
        socket.readyRead.connect(lambda: self._read_message(socket))

    def _read_message(self, socket: QLocalSocket):
        """! @brief 从 IPC 套接字读取并解析消息

        按帧协议读取: 先读 4 字节头部获取载荷长度，再读载荷内容。

        @param socket 已建立连接的本地套接字
        """
        try:
            if socket.bytesAvailable() < AppConstant.IPC_HEADER_SIZE:
                return

            header = socket.read(AppConstant.IPC_HEADER_SIZE)
            payload_length = struct.unpack("!I", header)[0]

            if payload_length > 10 * 1024 * 1024:
                self._logger.warning(
                    f"IPC 载荷过长 ({payload_length} 字节), 丢弃连接"
                )
                socket.disconnectFromServer()
                return

            if socket.bytesAvailable() < payload_length:
                return

            payload = bytes(socket.read(payload_length))
            data = json.loads(payload.decode("utf-8"))

            if not isinstance(data, dict) or "action" not in data:
                self._logger.warning(f"IPC 消息格式无效: {data}")
                socket.disconnectFromServer()
                return

            self._logger.info(f"IPC 消息接收: {data.get('action', '未知')}")
            self.message_received.emit(data)

            socket.write(b"ok")
            socket.waitForBytesWritten(AppConstant.IPC_TIMEOUT_MS)
            socket.disconnectFromServer()

        except json.JSONDecodeError as e:
            self._logger.warning(f"IPC 消息 JSON 解码失败: {e}")
            socket.disconnectFromServer()
        except struct.error as e:
            self._logger.warning(f"IPC 帧头解析失败: {e}")
            socket.disconnectFromServer()
        except Exception as e:
            self._logger.error(f"IPC 消息读取异常: {e}")
            socket.disconnectFromServer()
