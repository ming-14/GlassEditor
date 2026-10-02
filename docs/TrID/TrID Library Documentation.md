# TrID Library Documentation

TrID 是一个文件类型识别库，通过分析文件的二进制特征（固定偏移的模式与可搜索的字符串）来判断文件格式。本模块将原始的命令行工具重构为一个可直接 `import` 使用的 Python 库，仅暴露必要的编程接口。

---

## 许可说明

本库基于 [TrID](https://mark0.net/soft-trid-e.html) 的核心逻辑构建，**原始版权归 Marco Pontello 所有**，采用双许可：

- **个人或非商业用途**：遵循 GNU AGPLv3 协议免费使用。
- **商业用途**（包括任何盈利、商务相关活动或由营利实体使用）：需要从作者处获得单独的商业许可（联系 marcopon@gmail.com）。

使用本模块时，您需遵守原始 TrID 的许可条款。

---

## 依赖

- **Python** ≥ 3.7
- **stringzilla**（可选，但强烈推荐）：可大幅加速字符串搜索。安装方式：
  ```bash
  pip install stringzilla
  ```

---

## 快速开始

```python
from trid import load_definitions, identify_file, identify_data

# 1. 加载定义（只需执行一次，或使用默认路径自动加载）
load_definitions("triddefs.trd")

# 2. 从文件路径识别
results = identify_file("example.pdf")
for res in results[:3]:
    print(f"{res.perc:.1f}% - {res.triddef.filetype} ({res.triddef.ext})")

# 3. 从二进制数据识别
with open("unknown.bin", "rb") as f:
    data = f.read()
results = identify_data(data)
```

---

## 主要类

### `TrIDDef`
一个文件类型定义的内部表示，包含以下属性：

| 属性       | 类型   | 说明                     |
|------------|--------|--------------------------|
| `filetype` | `str`  | 文件类型描述（如 "PDF document"） |
| `ext`      | `str`  | 关联扩展名，多个以 `/` 分隔（如 "pdf/doc"） |
| `mime`     | `str`  | MIME 类型                |
| `filename` | `str`  | 定义文件名               |
| `tag`      | `int`  | 标签编号                 |
| `rem`      | `str`  | 备注                     |
| `refurl`   | `str`  | 参考 URL                 |
| `user`     | `str`  | 贡献者用户名             |
| `email`    | `str`  | 贡献者邮箱               |
| `home`     | `str`  | 贡献者主页               |
| `filenum`  | `int`  | 匹配的文件数量           |
| `patterns` | `list` | 固定模式列表，元素为 `(offset, bytes)` |
| `strings`  | `list` | 搜索字符串列表，元素为 `bytes` |

### `TrIDResult`
一次匹配的结果，包含以下属性：

| 属性      | 类型      | 说明                                        |
|-----------|-----------|---------------------------------------------|
| `perc`    | `float`   | 匹配百分比（所有可能定义得分总和中的比例）  |
| `pts`     | `int`     | 原始匹配分数                                |
| `patt`    | `int`     | 匹配到的固定模式数量                        |
| `str`     | `int`     | 匹配到的字符串数量                          |
| `triddef` | `TrIDDef` | 指向对应定义对象的引用                      |

结果列表**按分数从高到低排序**。

### `TrIDDefsBlock`
内部定义集容器，通常无需直接访问。可通过 `load_definitions()` 返回。

---

## 公共 API

### `load_definitions(trdfile=None, usecache=True)`
加载 TrID 定义包。**建议在分析前显式调用一次**，避免自动加载时的重复解析。

**参数：**
- `trdfile` (`str` 或 `None`) – 指向 `.trd` 定义包的路径。若为 `None`，则使用该模块目录下的 `triddefs.trd`。
- `usecache` (`bool`) – 若为 `True`，尝试使用缓存的解析结果（`.triddefs.trd.cache`），加速重复加载。

**返回：** `TrIDDefsBlock` 对象。

**异常：**
- `FileNotFoundError` – 指定文件不存在。
- `ValueError` – 文件格式无效。

---

### `identify_file(file_path, trdfile=None)`
根据文件路径识别文件类型。

**参数：**
- `file_path` (`str` 或 `os.PathLike`) – 待分析文件的路径。
- `trdfile` (`str` 或 `None`) – 可选的自定义定义包路径。若未提供且定义尚未加载，将自动使用默认路径加载。

**返回：** `list[TrIDResult]`，按匹配分数降序排列。若文件为空或无法识别，返回空列表。

**异常：**
- `FileNotFoundError` – 文件不存在。
- `PermissionError` – 没有读取权限。

---

### `identify_data(data, trdfile=None)`
根据内存中的二进制数据识别文件类型。

**参数：**
- `data` (`bytes`) – 文件内容的字节串。
- `trdfile` (`str` 或 `None`) – 自定义定义包路径，用法同 `identify_file`。

**返回：** `list[TrIDResult]`，排序规则同上。

---

## 算法说明

1. **前端模式匹配**：读取文件头部最多 2048 字节，检查各定义中固定偏移处的字节序列是否完全匹配。若第一条模式（偏移 0）匹配，分数会获得 1000 倍放大。
2. **字符串搜索**（始终启用）：对于通过模式匹配的定义，继续检查其关联字符串是否存在于文件内（大文件仅检查首尾各 5 MB）。命中的字符串将按长度给予 500 倍分数加成；任一字符串未找到则排除该定义。
3. 所有候选定义的得分汇总后，计算每个结果的百分比。
4. **性能优化**：
   - 定义按首字节分组，仅匹配对应的候选定义。
   - 全局字符串缓存：首次找到的字符串在整个分析过程中复用；首次未找到的字符串也将被记录，避免重复搜索。
   - 若 `stringzilla` 可用，字符串搜索将获得显著加速。

---

## 完整示例

```python
import sys
from trid import load_definitions, identify_file, identify_data

# 加载定义（可指向自定义 trd 文件）
try:
    load_definitions("mypackage.trd", usecache=True)
except FileNotFoundError:
    print("定义文件未找到，请检查路径。")
    sys.exit(1)

# 示例1：分析磁盘文件
file_path = "sample.docx"
results = identify_file(file_path)
if results:
    top = results[0]
    print(f"文件: {file_path}")
    print(f"  类型: {top.triddef.filetype}")
    print(f"  置信度: {top.perc:.1f}%")
    print(f"  常见扩展名: {top.triddef.ext}")
    print(f"  MIME: {top.triddef.mime}")
    if len(results) > 1:
        print(f"  其他可能性:")
        for r in results[1:4]:
            print(f"    - {r.triddef.filetype} ({r.perc:.1f}%)")
else:
    print("无法识别该文件。")

# 示例2：分析内存中的数据（例如网络流）
data = b'\x89PNG\r\n\x1a\n...'  # 假设这是一段 PNG 头
results = identify_data(data)
if results:
    print(f"数据识别结果: {results[0].triddef.filetype}")
```

---

## 注意事项

1. **定义文件**：模块默认在当前脚本目录寻找 `triddefs.trd`。您也可以调用 `load_definitions("your_path")` 使用自己的定义包。
2. **大文件处理**：完整内容仅用于字符串搜索，且大文件只采用首尾各 5 MB 拼接后的数据，这可能导致部分字符串遗漏，但能保持性能。
3. **字符串匹配**：所有字符串搜索均为区分大小写的字节匹配，且分析前数据已转为大写，因此定义中的字符串应为大写字节。
4. **线程安全**：`identify_file` 和 `identify_data` 内部使用了缓存字典（`foundcache`/`stopcache`），这些缓存**在单次调用内有效**，多次调用之间互不影响。若需并行处理，每个线程可共享加载的 `_TDB` 对象，分析函数本身是线程安全的。
5. **许可合规**：商业产品中使用本库请务必获取商业授权，否则可能违反 AGPLv3 条款。

---

## 获取定义文件

可以从 TrID 官网下载最新定义包：
- 在线更新：[http://mark0.net/soft-trid-e.html](http://mark0.net/soft-trid-e.html)
- 直接链接：[http://mark0.net/download/triddefs.zip](http://mark0.net/download/triddefs.zip)  
  解压后将 `triddefs.trd` 放在模块同目录或指定路径即可。
