# PKULaw CLI Crawler — Spec Design Document v2

## 1. 项目定位

面向科研用户（高校内网）的北大法宝 V6 数据采集 CLI 工具。用户通过命令行参数或 JSON 查询文件描述检索条件，工具负责认证、搜索、采集、导出。核心目标：在 API 分页限制下，尽可能爬取所有符合条件的数据。

## 2. 输入设计

### 2.1 两种输入方式

**方式一：CLI 简写参数**（适合简单查询）

```bash
pkulaw crawl --full-text "抗诉" --trial-step "二审,再审" --category "刑事"
```

**方式二：JSON 查询文件**（适合复杂/层级查询）

```bash
pkulaw crawl --query query.json
```

两种方式可组合使用：CLI 参数补充 JSON 文件（CLI 覆盖 JSON 中的同名字段）。

### 2.2 JSON 查询文件格式

```json
{
  "fieldNodes": [
    {
      "field": "FullText",
      "value": "抗诉",
      "scope": "不限",
      "match": "同篇"
    },
    {
      "field": "TrialStep",
      "combine": "and",
      "values": ["二审", "再审"]
    },
    {
      "field": "CategoryNew",
      "values": ["刑事"],
      "children": {
        "刑事": ["危害公共安全罪", "侵犯财产罪"],
        "危害公共安全罪": ["放火罪", "交通肇事罪"]
      }
    },
    {
      "field": "CaseGrade",
      "values": ["指导性案例", "参考案例", "公报案例"]
    },
    {
      "field": "CourtGrade",
      "values": ["高级人民法院", "中级人民法院"]
    },
    {
      "field": "LastInstanceDate",
      "range": ["2020", "2025"]
    },
    {
      "field": "LastInstanceCourt",
      "value": "最高人民法院"
    },
    {
      "field": "Accusation",
      "values": ["盗窃罪", "诈骗罪"]
    }
  ],
  "orderBy": ["LastInstanceDate Desc", "LastInstanceDate Asc"],
  "settings": {
    "format": ["json", "xlsx"],
    "output_dir": "output",
    "chunk_size": 0,
    "delay": 0.5,
    "max_pages": 10
  }
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `field` | string | API fieldName（必填） |
| `value` | string | 文本型检索值（text 类型字段） |
| `values` | string[] | 多值选择（select/checkbox 类型字段） |
| `scope` | string | 全文检索范围：不限/审理经过/辩方观点/诉讼请求/争议焦点/法院查明/法院认为/裁判结果 |
| `match` | string | 匹配模式：同篇/同段/同句/间隔N字 |
| `combine` | string | 与前一个检索项的逻辑：and/or/not |
| `children` | object | 层级选择的子类映射，key=父类名，value=子类名列表 |
| `range` | [string, string] | 日期范围，如 ["2020", "2025"] |

### 2.3 CLI 简写参数

所有 CLI 参数均可通过 JSON 文件替代。CLI 参数用于快速指定常用字段：

```
# 检索项
--query <file>                    JSON 查询文件（指定后其他检索参数被忽略）
--full-text <keyword>             全文检索
--title <keyword>                 标题检索
--case-flag <keyword>             案号检索
--gist <keyword>                  裁判要点
--party <keyword>                 当事人
--judge <keyword>                 审理法官
--lawyer <keyword>                代理律师
--law-firm <keyword>              代理律所

# 选择型检索项（逗号分隔）
--category <values>               案由分类（支持层级：刑事>危害公共安全罪）
--trial-step <values>             审理程序
--court-grade <values>            法院级别
--court <values>                  审理法院
--case-grade <values>             参照级别
--case-class <values>             案件类型
--doc-type <values>               文书类型
--result <values>                 终审结果
--topic <values>                  专题分类
--punishment <values>             刑罚
--accusation <values>             判定罪名

# 日期范围
--date-range <start-end>          审结日期范围
--issue-date-range <start-end>    发布日期范围

# 逻辑
--combine <logic>                 多检索项关系：and/or（默认：and）

# 输出
--format <formats>                json/xlsx/csv（默认：json,xlsx）
--output-dir <path>               输出目录（默认：output）
--chunk-size <n>                  分表大小，0=不分（默认：0）

# 运行控制
--log-file <path>                 日志文件（默认：output/crawl.log）
--delay <seconds>                 请求间隔（默认：0.5）
--max-pages <n>                   每组最大页数（默认：10）
--browser <path>                  Chromium 路径（默认：/usr/bin/chromium）
--no-headless                     显示浏览器
```

### 2.4 CLI 示例

```bash
# 简单查询
pkulaw estimate --full-text "抗诉" --trial-step "二审,再审" --category "刑事"
pkulaw crawl --full-text "抗诉" --trial-step "二审,再审" --category "刑事"

# 层级案由
pkulaw crawl --category "刑事>侵犯财产罪>盗窃罪" --format json,csv

# 复杂查询用 JSON 文件
pkulaw crawl --query my_research.json --format json --chunk-size 5000

# 查看进度
pkulaw status
```

### 2.5 层级参数的 CLI 写法

对于 `--category`、`--accusation` 等有层级的字段，CLI 用 `>` 分隔层级：

```bash
# 二级：刑事 > 危害公共安全罪
--category "刑事>危害公共安全罪"

# 三级：刑事 > 侵犯财产罪 > 盗窃罪
--category "刑事>侵犯财产罪>盗窃罪"

# 多个层级值（逗号分隔）
--category "刑事>侵犯财产罪>盗窃罪,刑事>侵犯财产罪>诈骗罪"
```

### 2.6 参数映射表

CLI 中文值 → API id 的映射由程序内置，从 API 动态获取或硬编码：

**CategoryNew（案由）**：
```
刑事=001, 民事=002, 行政=005, 执行=006, 国家赔偿=007
  刑事>危害国家安全罪=001001, 刑事>危害公共安全罪=001002, ...
    刑事>危害公共安全罪>放火罪=001002001, ...
```

**TrialStep（审理程序）**：
```
一审=001, 二审=002, 再审=003, 死刑复核=004, 简易程序=011, 速裁程序=012, 特别程序=013
```

**CaseGrade（参照级别）**：
```
指导性案例=01, 参考案例=11, 公报案例=02, 典型案例=03, 参阅案例=04,
评析案例=09, 优秀案例=10, 经典案例=05, 应用案例=08, 法宝推荐=06, 普通案例=07
```

**CourtGrade（法院级别）**：
```
最高人民法院=01, 高级人民法院=02, 中级人民法院=03, 基层人民法院=04, 专门人民法院=05
```

**DocumentAttr（文书类型）**：
```
判决书=001, 裁定书=002, 决定书=003, 调解书=004, 其他文书=005
```

## 3. 子命令设计

### 3.1 `estimate` 命令

计算可爬取数据量，不开始爬取。

**递归分区算法**：

```
function estimate(query):
    total = api_search(query).total

    if total <= max_pages * page_size (1000):
        return {total: total, partitions: [query]}

    # 尝试所有可用分区维度
    for dimension in [CategoryNew_sub, CaseGrade, LastInstanceDate_year, CourtGrade, TrialStep]:
        sub_queries = split_by(query, dimension)
        if len(sub_queries) > 1:
            result = sum(estimate(sub) for sub in sub_queries)
            if result.coverage > best.coverage:
                best = result

    return best
```

分区维度优先级（按区分度排序）：

1. **LastInstanceDate（年份）**：2026→2000，27 个分区
2. **CategoryNew 二级**：刑事下 12 个子类
3. **CaseGrade（参照级别）**：11 个级别
4. **CourtGrade（法院级别）**：5 个级别
5. **CategoryNew 三级**：具体罪名（数百个）
6. **TrialStep**：7 个值
7. **DocumentAttr**：5 个类型

对每个分区，使用 4 种排序（LastInstanceDate Desc/Asc, SortNum Desc/Asc）进一步扩大覆盖。

**输出示例**：

```
=== PKULaw 数据量估算 ===

检索条件：
  全文：抗诉
  审理程序：二审、再审
  案由：刑事

数据库总量：308,857 篇

分区策略（递归）：
  Level 1 — 年份 (27 个分区)：
    2026: 305      → 完整爬取 ✓
    2025: 3,683    → 需要进一步分区
      Level 2 — 参照级别 (11 个分区)：
        指导性案例: 5    → 完整爬取 ✓
        参考案例: 42     → 完整爬取 ✓
        经典案例: 2,841  → 需要进一步分区
          Level 3 — 罪名二级分类：
            ...

预计可爬取：XX,XXX / 308,857 (XX.X%)
分组总数：XXX 组
耗时预估：XX 小时（@0.5s/请求）
```

### 3.2 `crawl` 命令

执行搜索 + 采集 + 导出。

**搜索阶段**：
1. 运行 estimate 的分区算法，确定最优分组策略
2. 对每个分区组合 (groupBy + orderBy)，调用搜索 API
3. 按 gid 去重，保存到 search_results.json
4. 每个分区完成后增量保存

**采集阶段**：
- 从 search_results.json 读取 gid 列表
- 跳过 progress.json 中已采集的 gid
- 逐条访问详情页，解析 HTML
- 容错：浏览器重启、认证重试、跳过失败案例
- 每 500 条自动保存

**导出阶段**：
- 按指定格式输出（json/xlsx/csv）
- sanitize 非法控制字符
- 如指定 chunk-size，分表输出

### 3.3 `status` 命令

从日志文件和数据文件读取状态，不依赖任何特殊逻辑。无活跃爬取时自然显示空值。

**输出**：

```
=== PKULaw 爬取状态 ===
时间：2026-05-29 01:30:00

检索条件：（从 search_results.json 的 query 字段读取）
  全文：抗诉 | 审理程序：二审,再审 | 案由：刑事

搜索缓存：12,827 条（已完成 ✓）
已采集：10,500 / 12,827 (81.9%)
有效数据：9,472 条 (>500字, 90.2%)
剩余：2,327 条
输出文件：13,069 条 (output/pkulaw_cases.json, 161MB)

进程：运行中 (PID: 657768, 内存: 1.2GB) / 已停止

最近日志（output/crawl.log 最后 20 行）：
  [2026-05-29 01:28:00] INFO  [1000/3565] (熊某某等故意伤害案)
  [2026-05-29 01:28:15] INFO  Saved: 13069 cases, 12500 fetched
  [2026-05-29 01:28:30] ERROR [1032/3565] Execution context destroyed
```

## 4. 日志系统

### 4.1 格式

```
[2026-05-29 01:30:15] INFO  Authenticated (Bearer eyJhbG...)
[2026-05-29 01:30:16] INFO  Fetching 5270 cases (search cache: 12827)
[2026-05-29 01:30:45] INFO  [50/5270] (汤成盗窃一案)
[2026-05-29 01:31:00] ERROR [211/5270] Execution context destroyed
[2026-05-29 01:31:01] INFO  Page recovery succeeded
[2026-05-29 01:33:00] INFO  Saved: 8069 cases, 8000 fetched, 7686 loaded
[2026-05-29 01:40:00] WARN  Browser restart: 5 consecutive errors
```

### 4.2 内容要求（比现有只多不少）

保留所有现有信息 + 新增：
- 检索条件记录（启动时写入完整参数）
- 启动/停止时间
- 累计运行时间
- 浏览器重启次数
- 认证失败次数
- 跳过案例数（含 gid 和原因）
- 每次保存时的完整统计

### 4.3 search_results.json 增强

```json
{
  "query": {
    "fieldNodes": [
      {"field": "FullText", "value": "抗诉"},
      {"field": "TrialStep", "values": ["二审", "再审"]}
    ],
    "raw_cli": "pkulaw crawl --full-text 抗诉 --trial-step 二审,再审 --category 刑事",
    "started_at": "2026-05-28T08:30:00",
    "completed_at": "2026-05-28T08:45:00"
  },
  "partition_strategy": {
    "dimensions": ["LastInstanceDate", "CaseGrade"],
    "sort_orders": ["LastInstanceDate Desc", "LastInstanceDate Asc", "SortNum Desc", "SortNum Asc"],
    "total_groups": 108
  },
  "total_unique": 12827,
  "results": [
    {"gid": "...", "title": "...", "search_year": 2026}
  ]
}
```

## 5. 输出格式

### 5.1 JSON

与现有相同：`[{gid, url, title, ..., full_text}, ...]`

### 5.2 Excel (.xlsx)

与现有相同：扁平表，动态列（含所有【】段落列），sanitize 非法字符。

### 5.3 CSV

UTF-8 with BOM，动态列与 Excel 相同，sanitize 换行符和引号。full_text 直接内嵌，不截断。

## 6. 容错机制

| 场景 | 处理 |
|------|------|
| 浏览器会话崩溃 | 新建 page tab，失败则关闭浏览器重启 |
| 连续 5 次错误 | 关闭浏览器，15s 后重建 |
| 认证失败 | 外层 try/except，15s 后重试 |
| 单个案例失败 | 跳过并记录到日志（含 gid 和错误原因） |
| Excel/CSV 非法字符 | sanitize 控制字符 |
| Ctrl+C | 保存进度，友好退出 |
| 系统崩溃 | 下次从 progress.json 恢复 |

## 7. 项目结构

```
├── pkulaw.py                    # CLI 入口
├── setup.py / pyproject.toml    # pip install -e . 支持
├── src/
│   ├── __init__.py
│   ├── cli.py                   # argparse 命令解析、JSON 查询文件解析
│   ├── config.py                # 参数映射表（中文→API id）、常量
│   ├── crawler.py               # 主爬虫（搜索+采集+递归分区+容错）
│   ├── parser.py                # HTML 解析（动态【】提取）
│   ├── exporter.py              # JSON/Excel/CSV 导出
│   ├── log.py                   # 日志配置
│   └── refetch.py               # 失败案例重爬
├── docs/
│   └── spec-v2.md               # 本文件
├── requirements.txt
├── .gitignore
└── README.md
```

## 8. 非功能需求

- Python 3.10+
- 双入口：`python pkulaw.py` 或 `pkulaw`（pip install -e .）
- 断点续爬
- 进度保存：每 500 条
- 请求延迟：默认 0.5s
- 内存控制：浏览器会话定期重建
- git 管理，无 co-author
