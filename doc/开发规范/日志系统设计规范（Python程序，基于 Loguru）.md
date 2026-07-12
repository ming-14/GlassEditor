# 日志系统设计规范（Python程序，基于 Loguru）

## 整体架构

基于 Loguru 库构建，利用其内置的异步队列、文件轮转、线程安全等特性，无需自行实现底层组件。

- **全局日志器**：Loguru 提供的 `logger` 单例，所有模块共享。
- **模块级隔离**：通过 `logger.bind(module=name)` 创建子日志器，自动携带模块标识。
- **异步处理**：在添加 Sink 时设置 `enqueue=True`，所有日志调用仅将记录放入无锁队列，后台线程批量写入。
- **可插拔 Sink**：支持控制台、文件、网络、数据库等多种输出目标，每个 Sink 可独立配置级别、格式、过滤规则。

## 日志级别体系

Loguru 原生支持 `TRACE < DEBUG < INFO < SUCCESS < WARNING < ERROR < CRITICAL`。自定义级别映射如下：

| 级别 | Loguru 级别 | 显示标签 | 典型用途 | 默认输出 |
|------|-------------|----------|----------|----------|
| ERROR | `ERROR` | `[ERROR]` | 严重错误，程序可能无法继续 | stderr + 文件 |
| WARNING | `WARNING` | `[WARN]` | 潜在问题，可恢复错误，降级行为 | stdout + 文件 |
| SUCCESS | `SUCCESS` | `[OK]` | 关键操作成功完成（Loguru 内置） | stdout + 文件 |
| INFO | `INFO` | `[INFO]` | 常规信息、状态变化、任务进展 | stdout + 文件 |
| DEBUG | `DEBUG` | `[DEBUG]` | 调试信息、详细执行路径 | 仅文件（生产环境关闭） |
| TRACE | `TRACE` | `[TRACE]` | 极细粒度跟踪（函数入参、循环体） | 仅文件（开发环境） |

级别过滤：通过 Sink 的 `level` 参数控制，`logger.level("WARNING")` 可动态修改全局阈值。

## 日志格式规范

Loguru 支持完全自定义格式，通过 `format` 参数传入函数或字符串模板。

- **简洁文本格式（默认）**：`[时间] [级别] [模块名] 消息 | {key=value, key=value}`
  - 时间戳：`YYYY-MM-DD HH:MM:SS.mmm`，毫秒精度
  - 模块名：通过 `bind(module=...)` 传入
  - 扩展字段：通过 `bind()` 或关键字参数传递，自动格式化为 `{key=value}` 形式
- **结构化 JSON 格式（可选）**：设置 `serialize=True`，Loguru 自动输出 JSON，包含时间、级别、模块、消息、异常、进程/线程 ID 及 `extra` 中的所有字段。

## 异步日志核心机制

- **无阻塞设计**：所有 Sink 配置 `enqueue=True`，日志调用仅将记录放入线程安全队列（多生产者单消费者），业务线程永不等待 I/O。
- **队列容量控制**：通过 `queue_size` 参数限制队列最大长度，可选 `overflow_policy` 为 `"drop"`（丢弃新日志）或 `"block"`（阻塞等待）。
- **批量写入**：Loguru 内部自动批量消费队列，减少系统调用。
- **延迟格式化**：仅在日志级别通过过滤后才执行格式化，避免无用字符串拼接。

## 文件日志管理

利用 Loguru 的 `rotation` / `retention` / `compression` 参数实现全功能文件管理。

- **存储目录**：`./logs/`，自动创建
- **文件命名**：`app_{time:YYYY-MM-DD}_{number}.log`
- **轮转策略**：
  - 按大小：`rotation="100 MB"`
  - 按时间：`rotation="00:00"` 或 `rotation="1 day"`
  - 可组合自定义函数，同时检查大小和时间
- **保留策略**：`retention` 支持保留文件数量（如 `30`）或保留天数（如 `"7 days"`）
- **压缩归档**：`compression="gz"`，轮转后自动压缩
- **线程安全**：Loguru 内置文件锁，多线程安全；多进程建议使用 `enqueue=True` 避免竞争

## 高级特性

### 上下文绑定

通过 `logger.bind(key=value)` 创建带静态上下文的子日志器，自动将绑定字段附加到后续每条日志的 `extra` 中。

- 每个模块通过 `get_logger(name)` 返回 `logger.bind(module=name)` 的实例
- 支持链式绑定：`logger.bind(user_id=123).bind(session="abc")`
- 绑定字段不可变，如需修改可创建新的绑定实例

### 智能采样与节流

Loguru 不直接提供采样节流，通过自定义过滤器实现：

- 过滤器维护一个字典，记录每个 `throttle_key` 的最后记录时间与次数
- 在指定时间窗口内超过最大次数则丢弃后续日志
- 过滤器通过 Sink 的 `filter` 参数注入，对业务代码透明

### 异常自动捕获

- 使用 `logger.opt(exception=True).error(...)` 或 `logger.exception(...)` 自动附加调用栈
- 异常信息以 `{exception}` 字段形式存入日志，格式包含异常类型、消息和堆栈

### 动态配置热加载

- 通过 `logger.configure()` 可在运行时动态修改全局配置（级别、Sink、格式等）
- 结合文件监听（如 `watchdog`）检测配置文件变化，自动调用 `logger.configure()` 重新加载
- 支持热加载的内容：Sink 增删、级别调整、格式变更、过滤规则修改

## 接口定义与使用示例（设计层面）

- **获取日志器**：`get_logger(name: str) -> Logger`
  - 参数 `name` 为模块名（大驼峰或点分路径）
  - 返回绑定了 `module=name` 的 Logger 实例
  - 工厂函数缓存已创建的 Logger，避免重复绑定开销

- **日志方法**：`logger.error(msg, **extra)`、`logger.warning(...)`、`logger.success(...)`、`logger.info(...)`、`logger.debug(...)`、`logger.trace(...)`
  - 所有额外关键字参数自动合并到 `extra` 字段
  - 敏感字段自动脱敏（通过全局过滤器实现）

- **控制接口**：
  - `logger.level("WARNING")` 设置全局级别
  - `logger.disable(name)` / `logger.enable(name)` 按模块启停
  - `logger.remove()` 移除所有 Sink，彻底关闭日志输出

## 安全与性能规范

### 禁止记录的内容

- **绝对禁止**：明文密码、API Key、Token、身份证号、手机号、邮箱
- **需要脱敏**：IP 地址（保留前三段）、用户昵称（哈希）、文件路径（去除用户名部分）
- **自动脱敏**：全局过滤器扫描 `extra` 字典中所有键名包含 `password`、`secret`、`token`、`api_key` 的字段，将其值替换为 `"***"`

### 性能目标

| 场景 | 最大开销 |
|------|----------|
| 被过滤的日志（级别不满足） | < 0.2 μs |
| 允许的日志（异步入队） | < 1 μs |
| 允许的日志（含格式化和 extra 序列化） | 5-10 μs |
| 后台批量写入（每 200 条） | < 3 ms |

### 内存安全

- 队列容量建议设置为 20000，单条记录平均约 200 字节，总内存占用 ≤ 4 MB
- 使用 `catch=True` 参数使 Sink 内部异常不会导致消费者线程崩溃

## 扩展点与定制

- **自定义 Sink**：任何可调用对象（函数或实现了 `__call__` 的类）接受一个 `dict` 参数（日志记录）即可作为 Sink
- **自定义过滤器**：函数接受 `record` 参数，返回 `True` 保留、`False` 丢弃
- **回调机制**：可在过滤器中触发外部回调（如发送告警），不影响日志流

## 配置参考（设计结构）

配置文件采用 YAML 格式，包含以下顶层字段：

- `level`：全局日志级别
- `queue_size`：异步队列容量
- `overflow_policy`：队列满时策略（`drop` / `block`）
- `sinks`：列表，每个元素包含 `sink`（目标标识）、`level`、`format`、`enqueue`、`rotation`、`retention`、`compression`、`serialize` 等
- `extra`：全局静态上下文字典
- `filters`：预置过滤器配置（如脱敏规则、节流参数）