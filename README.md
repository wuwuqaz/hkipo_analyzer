# 港股 IPO 打新分析 (hkipo_analyzer)

自动获取港股招股IPO列表，下载招股书PDF，解析财务数据，运行多维度评分，通过Streamlit Web UI 展示或导出 PDF/JSON 报告。

## 快速开始

```bash
cd hkipo_analyzer
pip install -r requirements.txt

# 启动 Web UI
streamlit run app.py

# 或使用 CLI 模式
python -c "from ipo_analyzer.core import main; main()"
```

## 项目结构

```
hkipo_analyzer/
├── app.py                          # Streamlit Web UI 入口
├── style.css                       # 前端样式
├── requirements.txt                # 依赖
├── data/
│   ├── peer_comps.yaml             # 同行对比数据库（半动态：可手动更新或通过行情刷新）
│   └── backups/                    # 更新前自动备份（自动生成）
├── ui/
│   ├── __init__.py
│   └── pages/
│       ├── __init__.py
│       └── peer_admin_page.py      # 同行库管理 Streamlit 页面
├── ipo_analyzer/
│   ├── __init__.py                 # 轻量包初始化（不 eager import 重依赖）
│   ├── core.py                     # 核心编排（数据流 + 评分 pipeline）
│   ├── peer_comps.py               # 同行对比与相对估值分析（懒加载 pyyaml）
│   ├── peer_data.py                # 同行库数据服务层（YAML 读写/备份/行情更新）
│   ├── downloader.py               # AiPO 孖展数据 + HKEX 招股书下载
│   ├── parser.py                   # PDF 招股书解析（PyMuPDF / PyPDF2）
│   ├── analyzers.py                # 8 个分析器（估值/业务/地理/客户/现金流/产能/研发/风险）
│   ├── peer_comps.py               # 同行对比与相对估值分析（v2 新增）
│   ├── scoring.py                  # 评分系统（基本面/进阶框架/综合评分）
│   ├── cornerstone.py              # 基石投资者分析
│   ├── cache.py                    # 结果缓存（7天 TTL）
│   ├── history.py                  # 历史数据持久化
│   ├── report.py                   # PDF 报告生成（ReportLab）
│   ├── table_extraction.py         # 财务表格提取
│   └── utils.py                    # 共用工具函数
├── scripts/
│   └── test_peer_comps.py          # 同行对比单元测试
└── temp/                           # 临时文件 / 缓存 / 输出
```

## 评分体系

最终评分 = 申购热度 × 0.35 + 基本面 × 0.45 + 基础分(20) + 调整项

### 调整项

| 类型 | 范围 | 说明 |
|------|------|------|
| 风险扣分 | 0～-20 | 招股书风险因子 + VBP + 客户集中度 |
| 进阶框架 | -10～+10 | 7维度框架（真实资金/筹码/基石/估值/主线/入通/数据质量） |
| **同行估值调整** | **-5～+6** | **v2新增：基于同行对比评分的估值修正** |

## 估值逻辑（v2 改进）

### 旧逻辑（v1）
简单 PS/PE 绝对阈值判断：
- PS > 15 → "很贵"（扣5分）
- PS > 8 → "偏贵"（扣2分）

### 新逻辑（v2）
三层次综合判断：
1. **绝对估值**（保留原始阈值）
2. **同行相对估值**：公司 PS vs 同行 PS 中位数
3. **稀缺性评分**（0-10）：上市同行数量、技术壁垒、赛道类型、基石质量、增长速度

综合结论覆盖"偏贵但可解释"、"赛道合理"、"PS辅助"等场景，避免成长型/稀缺赛道公司被简单阈值误判。

## 更新日志

### v4 — 2026-05-06
- **fix: argparse `--dry-run` 参数**（`scripts/update_peer_comps.py`）：默认预览模式，`--write` 写入
- **fix: YahooFinanceProvider 币种和单位**：`get_fx_to_hkd()` 汇率表、`to_hkd_million()` 单位转换、`normalize_ticker_for_yahoo()` ticker 标准化
- **fix: PeerMetricsUpdater 批量写入**：`update_all` / `update_subsector` 改为先 load → 内存批量修改 → 统一 backup + save，避免多次备份
- **fix: peer_admin_page.py 两阶段更新**：预览过期/预览全部 → 确认写入，新增 low quality / missing PS/PE 筛选器
- **fix: match_confidence 改为 `_best_hits_to_confidence(best_hits)`**，不再用 `len(all_matches)` 判断
- **fix: prospectus_peer_candidates** = extracted_competitors + unmatched_peer_candidates 去重，不自动加入 YAML
- **fix: detail_view.py 展示 unmatched/extracted 同行候选**
- **fix: app.py set_page_config 顺序**（必须在第一个 Streamlit 命令前调用）
- **新增 `scripts/package_project.sh`**：排除 `__pycache__`、`temp/*.pdf`、`data/backups/`、`__MACOSX/`

### v3 — 2026-05-06
- **fix: 基础依赖隔离**：`__init__.py` 不再 eager import parser/core/report 等重模块，`import ipo_analyzer` 不再触发 PyPDF2
- **fix: peer_comps.py lazy import yaml**：`import yaml` 移入 `_load_peer_data()` 内部，pyyaml 缺失时只 warning 不崩溃
- **新模块: `ipo_analyzer/peer_data.py`**：PeerDataStore（YAML 读写+自动备份）、YahooFinanceProvider（yfinance 行情获取）、PeerMetricsUpdater（批量更新入口）
- **新脚本: `scripts/update_peer_comps.py`**：支持 `--all --dry-run`、`--stale-only --write`、`--ticker XXXX.HK` 等命令
- **新页面: `ui/pages/peer_admin_page.py`**：Streamlit 同行库管理页，含 meta 展示、筛选表格、刷新按钮
- **app.py 导航增加**："🧩 同行库管理" 页面，通过侧边栏切换
- **全局 sector fallback**：当 sector 不匹配时，在所有 sector 搜索 subsector，避免漏匹配
- **unmatched_peer_candidates**：招股书文本中提取疑似同行名，不在本地库中的放入候选列表供人工审核
- **修复 YAML 路径问题**：英矽智能 ticker 更新为 03696.HK，更新脚本支持港股/A 股/美股 ticker 转换
- **新增 `.gitignore`**：排除 `__pycache__`、`temp/*.pdf`、`data/backups/` 等

### v2 — 2026-05-05
- **新增 `data/peer_comps.yaml`**：同行对比数据库，支持 hardtech（机器人/AI芯片）和 healthcare（AI制药/创新药/医疗器械/CXO）共6个细分赛道
- **新增 `ipo_analyzer/peer_comps.py`**：`PeerComparableAnalyzer` — 赛道匹配 → 同行识别 → 相对估值计算 → 稀缺性评分 → 估值定位判断
- **重构 `ValuationAnalyzer`**：支持绝对估值 + 相对估值 + 稀缺性的综合估值标签，对收入极小的科技/生物科技公司给出"PS辅助"提示
- **重构 `AdvancedIPOFrameworkAnalyzer._analyze_valuation_framework`**：满分20分拆为 绝对估值8分 + 同行相对估值8分 + 稀缺性4分
- **重构 `ScoringSystem.calculate`**：新增 `peer_valuation_adjustment`（±6分），对稀缺赛道高估值给予容忍度加分
- **修改 `core.py._calculate_final_score`**：pipeline 中插入 `PeerComparableAnalyzer`（在估值分析前调用）
- **修改 `app.py`**：详情页新增同行对比卡片（细分赛道、估值对比、同行列表）
- **修改 `report.py`**：PDF 报告新增同行对比表格
- **新增 `scripts/test_peer_comps.py`**：4 个测试用例覆盖乐动机器人、剂泰科技、无同行回退、完整 pipeline
- **全量 print→logger 迁移**：downloader(17处)、analyzers(8处)、parser(6处) 的 `print()` 全部替换为 `logger`

### v1 — 初始版本
- Streamlit dashboard + 手动上传分析
- AiPO 孖展数据 + HKEX 招股书下载
- 8 个分析器 + 3 层评分系统
- PDF/JSON 报告导出
- 结果缓存 + 历史归档

## 维护说明

- **同行数据库**：`data/peer_comps.yaml` 需手动维护同行估值数据。`source_date` 和 `data_quality` 字段标记数据时效性
- **新增细分赛道**：在对应 sector 下添加新条目，并确保 `keywords` 能匹配招股书文本
- **Private 公司**：不参与 PS/PE 中位数计算，仅做定性参考
