# PKULaw Case Crawler

从 [北大法宝](https://www.pkulaw.com) 司法案例数据库批量爬取案例，用于学术研究。

## 功能

- **参数化检索** — 支持全文关键词、审理程序、案件类别等组合检索条件
- **大规模采集** — 按年份分区 + 多排序策略，突破 API 分页上限，单次可采集万级案例
- **动态段落提取** — 自动扫描所有【】标记段落，无需预设标签名单
- **断点续爬** — 进度实时持久化，中断后重新运行自动跳过已采集案例
- **自动重试** — 浏览器会话崩溃、认证失败、限流等异常自动恢复，无需人工干预
- **多格式导出** — 同时输出 JSON 和 Excel (.xlsx)，附带分表脚本
- **日志监控** — 完整爬取日志，支持 `tail -f` 实时监控

## 检索条件

| 字段 | 值 | API 映射 |
|------|------|---------|
| 全文 | 抗诉 | `fieldNodes[0].fieldName=FullText` |
| 审理程序 | 二审、再审 | `fieldNodes[1].fieldName=TrialStep` |
| 案件类别 | 刑事 | `clusterFilters.CategoryNew=001` |
| 数据库总量 | ~308,857 篇 | API 返回 total |

## 环境要求

- Python 3.10+
- Chromium（`/usr/bin/chromium`，或修改 `crawler.py` 中的路径）
- 学校内网访问 pkulaw.com（IP 自动认证）

## 安装

```bash
pip install -r requirements.txt
playwright install chromium  # 仅当系统未安装 Chromium 时
```

## 使用

### 全量采集

```bash
python main.py
```

自动按年份（2026→2000）和 4 种排序（LastInstanceDate Desc/Asc、SortNum Desc/Asc）搜索，去重后逐条抓取详情页。后台运行：

```bash
nohup python -u main.py > output/crawl_full.log 2>&1 &
```

### 监控进度

```bash
tail -f output/crawl_full.log
```

或使用状态检查脚本：

```bash
python3 -c "
import json
p=json.load(open('output/progress.json'))
s=json.load(open('output/search_results.json'))
print(f'Fetched: {len(p[\"fetched_gids\"])}/{len(s)}')
"
```

### 修复失败案例

```bash
python -c "from src.refetch import refetch; refetch()"
```

### 分表导出

将大表格按指定条数切分为多个小文件，每个文件保留完整表头：

```bash
# 默认每 10,000 条一个文件，同时输出 JSON 和 Excel
python split_excel.py

# 自定义参数
python split_excel.py --input output/pkulaw_cases.json --output-dir output/split --chunk-size 5000 --format excel
```

## 输出

文件保存在 `output/` 目录：

| 文件 | 说明 |
|------|------|
| `pkulaw_cases.json` | 全部案例（JSON） |
| `pkulaw_cases.xlsx` | 全部案例（Excel） |
| `search_results.json` | 搜索结果缓存（gid 列表） |
| `progress.json` | 已采集 gid 列表，断点续爬用 |
| `crawl_full.log` | 完整爬取日志 |
| `split/` | 分表后的文件目录 |

### 数据结构

每条案例包含：

- **基础字段**：`gid`、`url`、`title`
- **系统字段**：`法宝引证码`、`时效性`
- **元数据字段**：`案由`、`案号`、`审理法院`、`审结日期`、`审理程序` 等（共 18 个）
- **【】段落字段**：动态提取所有 `【标签名】` 下的内容（如 `关键词`、`裁判要旨`、`典型意义`、`指导意义`、`检察机关履职过程` 等，共 217 列）
- **`full_text`**：案例正文全文

### 首次采集结果（2026-05-29）

| 指标 | 数值 |
|------|------|
| 搜索覆盖 | 12,827 unique gids |
| 实际抓取 | 13,594 cases |
| 有效内容 (>500字) | 12,113 (89%) |
| 含全文 | 13,561 (99.8%) |
| 动态列数 | 217 |

## 项目结构

```
├── main.py              # 入口
├── split_excel.py       # 分表脚本
├── requirements.txt
├── src/
│   ├── crawler.py       # 主爬虫（认证、搜索、详情采集、导出）
│   ├── parser.py        # HTML 解析（动态提取所有【】段落）
│   ├── exporter.py      # JSON / Excel 导出（动态列）
│   └── refetch.py       # 失败案例重爬
├── output/              # 输出目录（运行后生成）
└── docs/
    ├── spec.md          # 设计规格
    └── plan.md          # 执行计划
```

## 工作原理

### 搜索策略

API 对每次查询限制 10 页（每页 100 条 = 1000 条）。爬虫通过 **年份分区 + 多排序** 策略最大化覆盖：

1. `groupBy: {"LastInstanceDate": "YYYY"}` 按审结日期过滤到单个年份
2. 对每个年份使用 4 种 `orderBy` 排序（LastInstanceDate Desc/Asc、SortNum Desc/Asc）
3. 不同排序的结果几乎无重叠，每个年份可获取约 3500-4000 条
4. 通过 gid 去重确保跨排序不重复

预计覆盖：~12,800 条（约占数据库总量 308,857 的 4%）。这是 API 分页限制下的最大可达量。

### 认证

Playwright 无头浏览器访问 pkulaw.com，学校内网 IP 自动完成 Keycloak OAuth2 认证，从 `localStorage` 提取 JWT token。

### 容错机制

- **浏览器会话崩溃**：连续 5 次错误后自动关闭浏览器，10-15s 后重建新会话
- **认证失败**：外层 try/except 捕获，15s 后重试认证
- **单个案例失败**：跳过并继续，不阻断整体流程
- **进度持久化**：每 500 条自动保存，重启后从断点继续

### 解析

动态扫描页面文本中所有 `【...】` 标记，提取标签名和后续内容，存为独立字段。跳过系统标签（法宝引证码、时效性）和纯年份数字。

## 已知限制

- API 单次查询最多 1000 条结果，多排序后每年约 4000 条，无法获取全部 30 万+
- 经典案例 (CaseGrade=07) 占总量 90%+，每年可达数万条，受分页限制影响最大
- JWT token 有效期约 30 分钟，但浏览器 cookie 保持会话，长时间运行通常不受影响

## 许可

本项目仅供学术研究使用。数据来源于北大法宝数据库，使用时请遵守相关许可协议。
