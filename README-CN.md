# archive-kit

[English](README.md)

用于归档文件检查、成员读取和批量解压的 Python 库，支持嵌套归档。
要求 Python 3.10 及以上版本。

分发包名为 `archive-kit`，Python 导入名为 `archive_kit`：

```python
from archive_kit import PasswordPolicy, PasswordStrategy, unpack_one
```

## 功能

- 支持 ZIP、7z、RAR、TAR、gzip 压缩的 TAR 和 xz 压缩的 TAR。
- 按文件后缀识别格式，不区分大小写，支持 `.tgz` 和 `.txz` 别名。
- 递归列出成员，提供大小、可获得的加密信息、嵌套深度及来源归档链。
- 递归解压并保留目录结构，嵌套归档解压到其旁边的同名目录。
- 查询成员是否存在，读取成员的字节或文本。
- 支持候选密码，以及缺少密码、密码错误时各自独立的处理策略。
- 探测依赖，生成逐归档批处理结果、汇总统计和 JSON 报告。

当前公开 API 不包含创建归档和命令行入口。

## 安装

在本项目目录执行：

```bash
python -m pip install .
# 额外安装处理 7z 和 RAR 的 Python 后端：
python -m pip install ".[full]"
```

基础安装通过 Python 标准库的 `zipfile`、`tarfile` 处理 ZIP 和 TAR 系列格式，
并依赖已发布的 `cells-json`、`cells-log` 输出 JSON 报告及诊断日志。`full` 额外安装
`py7zr` 和 `rarfile`。

CLI 后端需要另行安装 7-Zip。程序会查找 PATH 中的 `7z`、`7zz`、`7za`，
以及 Windows 常见安装目录。`rarfile` 解压部分 RAR 文件时也需要外部辅助程序。

| 格式 | 后端优先顺序 |
| --- | --- |
| `.zip` | `zipfile`，然后 `7zcli` |
| `.7z` | `7zcli`，然后 `py7zr` |
| `.rar` | `7zcli`，然后 `rarfile` |
| `.tar`、`.tar.gz`、`.tgz`、`.tar.xz`、`.txz` | `tarfile`，然后 `7zcli` |

`safe` 策略排除 `7zcli`。通过 `probe_support()` 查看后端可用性和依赖提示；
其中的 `supported_types` 表示程序认识的格式类别，也包含当前缺少可选后端的格式。

## 快速开始

```python
from archive_kit import inspect_one, member_exists, read_member_text, unpack_one

result = inspect_one("sample.zip", recursive=False)
for entry in result.entries:
    print(entry.relative_path, entry.size, entry.encrypted)

if member_exists("sample.zip", "docs/readme.txt").exists:
    print(read_member_text("sample.zip", "docs/readme.txt"))

extracted = unpack_one("sample.zip", output_dir="./output/sample", profile="balanced")
print(extracted.status.value, extracted.extracted_file_count)
print(extracted.warnings)
```

省略 `output_dir` 时，`sample.tar.gz` 会解压到归档旁边的 `sample/`。
启用递归后，解出的 `bundles/child.zip` 会继续解压到 `bundles/child/`。

## 公开 API

以下函数均从 `archive_kit` 导出，文件路径接受 `str` 或 `pathlib.Path`。

| 函数 | 返回值和用途 |
| --- | --- |
| `probe_support()` | `ArchiveSupportReport`：后端可用性及依赖提示。 |
| `inspect_one(file_path, recursive=None, profile=None, password_policy=None)` | `ArchiveInspectResult`：成员及检查诊断信息。 |
| `unpack_one(file_path, output_dir=None, recursive=None, profile=None, password_policy=None)` | `ArchiveExtractResult`：输出路径及解压诊断信息。 |
| `list_member_paths(file_path, recursive=None, profile=None, password_policy=None)` | 排序、去重后的成员路径 `list[str]`。 |
| `member_exists(file_path, member_path, profile=None, password_policy=None)` | `MemberLookupResult`，通过 `.exists` 读取结果；仅查询指定归档自身。 |
| `read_member_bytes(file_path, member_path, profile=None, password_policy=None)` | 指定归档中成员文件的 `bytes`。 |
| `read_member_text(file_path, member_path, encoding="utf-8", errors="strict", profile=None, password_policy=None)` | 解码后的 `str`；编码和错误处理参数遵循 Python 的解码规则。 |
| `batch_inspect(source_dir, profile=None, recursive_scan=True, password_policy=None)` | 用于检查的 `BatchProcessResult`。 |
| `batch_unpack(source_dir, target_dir=None, profile=None, recursive_scan=True, password_policy=None)` | 用于解压的 `BatchProcessResult`。 |
| `batch_result_to_dict(result)` | 可序列化为 JSON 的字典；路径、枚举和时间戳转换为字符串。 |
| `write_batch_report_json(result, output_path, *, indent=2, ensure_ascii=False)` | 写入 UTF-8 JSON，返回目标 `Path`；自动创建父目录并替换已有报告。 |

`profile=None` 使用 `balanced`。`recursive=None` 使用策略中的递归设置，
显式布尔值可以覆盖该设置。`recursive_scan` 控制批处理是否扫描子目录，
批处理中归档内部的递归处理由策略决定。

成员查询和读取仅针对指定归档自身的成员。递归的 `list_member_paths` 会合并各层归档的路径，
同名路径会被去重；需要区分来源时使用 `inspect_one`。
最外层成员的深度为 0，嵌套成员的 `source_archive` 使用正斜杠，
不同归档层以 `!/` 分隔，例如 `bundles/middle.zip!/inner/deep.zip`。

成员读取会先将归档解压到临时目录，再读取目标文件。递归检查也会临时解压。
这两类操作会向磁盘写入临时数据，并在结束后清理。

## 策略

| 设置 | `safe` | `balanced`（默认） | `aggressive` |
| --- | --- | --- | --- |
| 允许 CLI 后端 | 否 | 是 | 是 |
| 默认递归 | 否 | 是 | 是 |
| 最大嵌套深度 | 1 | 8 | 不限制 |
| 替换非空输出目录 | 否 | 否 | 是 |
| 删除成功展开的嵌套归档 | 否 | 否 | 是 |
| 将解出文件设为可写 | 否 | 是 | 是 |

`aggressive` 会在解压前删除已有的非空输出目录，也会删除成功展开的嵌套归档文件。
原始来源归档会保留。包含来源归档的输出目录，以及本身为符号链接的输出目录，会被拒绝。

可以基于内置策略定制：

```python
from dataclasses import replace
from archive_kit.profiles import BALANCED_PROFILE

profile = replace(BALANCED_PROFILE, name="shallow", max_depth=2)
```

## 密码和错误处理

```python
from archive_kit import PasswordPolicy, PasswordStrategy, unpack_one

policy = PasswordPolicy(
    passwords=("candidate-one", "candidate-two"),
    missing_password_strategy=PasswordStrategy.SKIP,
    invalid_password_strategy=PasswordStrategy.RAISE,
)
result = unpack_one("protected.7z", output_dir="./output/protected", password_policy=policy)
print(result.status.value, result.skipped_reason, result.warnings)
```

默认候选密码为空，两项策略均为 `SKIP`。
ZIP 和 RAR 的 Python 后端可以跳过单个加密成员，并返回带警告的 `success`。
7z 后端采用整包跳过策略。判断是否存在部分处理时，同时查看 `warnings` 和 `status`。

单归档操作失败时抛出异常。密码策略为 `RAISE` 时，
会保留 `archive_kit.errors` 中的 `PasswordRequiredError` 或 `InvalidPasswordError`。
其他异常包括 `UnsupportedArchiveError`、`MissingDependencyError`、
`InspectionFailedError`、`ExtractionFailedError` 和 `ArchiveSecurityError`。
无效输入路径抛出文件系统异常；非空输出目录在未启用替换时抛出 `FileExistsError`。

批处理会记录单个归档的失败并继续处理其他归档；无效来源目录会在批处理开始前直接抛错。

## 批处理和报告

```python
from archive_kit import batch_inspect, batch_unpack, write_batch_report_json

inspected = batch_inspect("./input", profile="safe")
result = batch_unpack("./input", target_dir="./output", profile="balanced")
report_path = write_batch_report_json(result, "./output/archive-report.json")
print(result.total_tasks, result.success_count, result.failed_count, result.skipped_count)
print(result.statistics)
print(report_path)
```

指定目标目录后保留来源目录结构：
`input/a/b/sample.tar.gz` 对应 `output/a/b/sample/`。
省略 `target_dir` 时，每个归档在自身旁边解压。批处理按顺序执行。

检查结果提供 `entries`、`entries_count`、`backend_used`、
`encrypted_entries_count` 和 `temp_extraction_used`。
解压结果提供 `output_dir`、`extracted_files`、`nested_archives_processed`、
`deleted_nested_archives` 及相应计数。
两者都提供 `status`、`warnings`、`encrypted_archive` 和 `skipped_reason`。

批处理结果包含逐归档 `reports`、UTC 开始与结束时间、耗时及汇总 `statistics`，
涵盖警告、错误、跳过、加密标记、检查成员数、解出文件数、
已处理及已删除的嵌套归档数，以及按格式和状态分类的计数。
加密标记取决于后端元数据和诊断信息，不能据此证明所有成员均已解密。

## 日志

库通过 `cells.log` 输出结构化事件，日志名称位于 `archive_kit` 下。
在调用方应用中配置日志：

```python
from cells.log import LogConfig, configure_logging, shutdown_logging
from archive_kit import batch_inspect

configure_logging(LogConfig(app_name="archive-job", level="INFO"))
try:
    result = batch_inspect("./input", profile="safe")
finally:
    shutdown_logging()
```

批处理开始和汇总使用 INFO；后端回退、跳过、策略拒绝及部分解压使用 WARNING；
后端全部失败、批处理单任务失败及命令超时使用 ERROR；后端尝试及完成详情使用 DEBUG。
诊断字段不记录密码、完整命令参数、文件内容或异常消息。
日志配置和关闭由应用负责，库自身不配置输出目标或创建日志文件。
结果对象仍保留警告和错误，供调用方进行程序化处理。

## 当前限制

- 通过文件名后缀识别格式，不检查内容签名。
- 尚未限制解压总字节数、成员数量、内存或整次任务耗时。
  每次 7-Zip 命令的超时为 300 秒，且无法读取交互输入。
- ZIP、TAR 的 Python 后端校验成员目标路径；TAR 的链接和特殊文件会被跳过。
  可选后端沿用各自的解压行为。
- `py7zr` 对密码错误与归档损坏的区分仍为尽力判断；
  RAR 辅助程序及归档特性的可用性可能因平台不同而变化。
- 成员读取会将目标文件完整载入内存。

## 测试

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

使用 [MIT 许可证](LICENSE)。
