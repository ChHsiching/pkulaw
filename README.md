# PKULaw CLI Crawler

从 [北大法宝](https://www.pkulaw.com) 司法案例数据库批量爬取案例，用于学术研究。

## 功能

- **递归分区搜索** — 自动选择最优分区维度，突破 API 分页上限
- **参数化检索** — CLI 参数或 JSON 查询文件，支持全文关键词、审理程序、案件类别等 25 个检索字段
- **断点续爬** — 进度实时持久化，中断后重新运行自动跳过已采集案例
- **自动容错** — 浏览器崩溃、认证失败等异常自动恢复
- **多格式导出** — JSON、Excel (.xlsx)、CSV，UTF-8 编码
- **状态监控** — `pkulaw status` 实时查看爬取进度

## 环境要求

- Python 3.10+
- Chromium（默认 `/usr/bin/chromium`）
- 学校内网访问 pkulaw.com（IP 自动认证）

## 安装

```bash
pip install -r requirements.txt
pip install -e .
```

## 使用

### 数据量估算

估算符合检索条件的数据量（不实际爬取）：

```bash
pkulaw estimate --full-text "抗诉" --trial-step "二审,再审" --category "刑事"
```

### 数据爬取

搜索 + 采集 + 导出一步完成：

```bash
# 基本用法
pkulaw crawl --full-text "抗诉" --category "刑事"

# 指定输出格式和每页条数
pkulaw crawl --full-text "抗诉" --format json,csv --max-pages 10

# 后台运行
nohup python -u pkulaw.py crawl --full-text "抗诉" > output/crawl.log 2>&1 &
```

### 查看状态

```bash
pkulaw status
```

输出示例：

```
=== PKULaw 爬取状态 ===
时间：2026-05-29 01:30:00

检索条件：
  全文：抗诉 | 审理程序：二审, 再审 | 案由：刑事

搜索缓存：12,827 条（已完成 ✓）
已采集：10,500 / 12,827 (81.9%)
有效数据：9,472 条 (>500字, 90.2%)
剩余：2,327 条
输出文件：13,069 条 (output/pkulaw_cases.json, 161MB)

进程：运行中 (PID: 657768, 内存: 1.2GB)
```

### JSON 查询文件

复杂查询条件写入 JSON 文件：

```bash
pkulaw crawl --query query.json
```

`query.json` 格式：

```json
{
  "fieldNodes": [
    {"field": "FullText", "value": "抗诉"},
    {"field": "TrialStep", "values": ["二审", "再审"]},
    {"field": "CategoryNew", "values": ["刑事"]}
  ],
  "settings": {
    "delay": 0.5,
    "max_pages": 10,
    "format": ["json", "xlsx"],
    "output_dir": "output"
  }
}
```

CLI 参数与 JSON 文件可组合使用，CLI 参数覆盖 JSON 中的同名字段。

### CLI 参数

| 参数 | 字段 | 说明 |
|------|------|------|
| `--full-text` | FullText | 全文关键词 |
| `--title` | Title | 标题关键词 |
| `--category` | CategoryNew | 案由分类（支持层级，逗号分隔） |
| `--trial-step` | TrialStep | 审理程序（二审/再审/...） |
| `--court-grade` | CourtGrade | 法院级别 |
| `--case-grade` | CaseGrade | 参照级别 |
| `--date-range` | LastInstanceDate | 审结日期范围 (2020-2025) |
| `--format` | — | 输出格式 (json,xlsx,csv)，默认 json,xlsx |
| `--delay` | — | 请求间隔秒数，默认 0.5 |
| `--max-pages` | — | 每个分区最大页数，默认 10 |
| `--output-dir` | — | 输出目录，默认 output |

## 输出

文件保存在 `output/` 目录：

| 文件 | 说明 |
|------|------|
| `pkulaw_cases.json` | 全部案例（JSON） |
| `pkulaw_cases.xlsx` | 全部案例（Excel） |
| `pkulaw_cases.csv` | 全部案例（CSV, UTF-8 BOM） |
| `search_results.json` | 搜索结果缓存 + 查询元数据 |
| `progress.json` | 已采集 gid 列表（断点续爬） |
| `crawl.log` | 爬取日志 |

### 数据结构

每条案例包含：

- **基础字段**：`gid`、`url`、`title`
- **元数据字段**：`案由`、`案号`、`审理法院`、`审结日期`、`审理程序` 等 18 个
- **【】段落字段**：动态提取所有 `【标签名】` 下的内容
- **`full_text`**：案例正文全文

## 项目结构

```
├── pkulaw.py                    # CLI 入口
├── pyproject.toml               # pip install 支持
├── src/
│   ├── cli.py                   # argparse 命令解析
│   ├── config.py                # 参数映射表（中文→API id）
│   ├── config_data.py           # 自动生成的 API 映射数据
│   ├── crawler.py               # 搜索（分区）+ 采集（容错）
│   ├── parser.py                # HTML 解析（动态【】提取）
│   ├── exporter.py              # JSON / Excel / CSV 导出
│   ├── auth.py                  # 浏览器认证 + API 调用
│   ├── query.py                 # SearchConfig → API body
│   ├── partition.py             # 递归分区算法
│   ├── log.py                   # 日志配置
│   └── refetch.py               # 失败案例重爬
├── tests/                       # 测试
└── docs/
    └── spec-v2.md               # 设计规格
```

## 工作原理

### 搜索策略

API 对每次查询限制返回约 1000 条。爬虫使用 **递归分区** 策略：

1. 先查询总量，如果超过阈值则按维度（年份 → 参照级别 → 案由 → ...）递归拆分
2. 对每个分区使用 4 种排序（LastInstanceDate/SortNum × Asc/Desc）
3. 通过 gid 去重确保不重复

### 容错机制

- **浏览器会话崩溃**：新建 page tab，失败则重启浏览器
- **连续 5 次错误**：关闭浏览器，15s 后重建
- **单个案例失败**：跳过并记录到日志
- **进度持久化**：每 500 条自动保存，重启后从断点继续

## 已知限制

- API 分页限制导致无法获取全部数据（单分区 ≤ 4000 条）
- 需要学校内网环境进行认证
- JWT token 有效期约 30 分钟（浏览器 cookie 保持会话）

## 许可

AGPL-3.0-only · Copyright (c) 2026 ChHsiching —— 见 [LICENSE](LICENSE)。

- 使用（含公司内部使用）、修改、分发均免费；但分发或以本代码提供网络服务时，衍生作品须以 AGPL-3.0 开源。
- 闭源商用须另行获取商业授权：hsichingchang@gmail.com

### 贡献条款

提交 PR 即表示你同意以 AGPL-3.0 授权你的贡献，并授予维护者在 AGPL 之外另行提供商业授权的权利（你的贡献始终以 AGPL 对所有人开放）。

## 研究用途与数据合规

本工具为学术研究目的开发，仅供通过您所在机构的合法订阅访问北大法宝数据库使用。数据来源于北大法宝数据库。使用人应自行确保遵守北大法宝服务条款、《反不正当竞争法》《数据安全法》《个人信息保护法》等法律法规，禁止转售、再分发或商业性利用抓取的数据。因使用本工具产生的一切法律责任由使用人自行承担。
