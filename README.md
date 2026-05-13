# 港股 IPO 打新分析 (hkipo_analyzer)

**当前版本：0.5.0-alpha；状态：开发中，仅供研究参考**

> 🤖 本项目由 AI（Claude Code + deepseek）全流程驱动完成，从需求分析、架构设计、代码实现到测试和部署，均为 AI 自主生成。

自动获取港股招股IPO列表，下载招股书PDF，解析财务数据，运行多维度评分，通过Streamlit Web UI 展示或导出 PDF/JSON 报告。

## 快速开始

```bash
cd hkipo_analyzer
python3 -m pip install -e ".[dev]"

# 启动 Web UI
streamlit run app.py

# 或使用 CLI 模式
python3 -c "from ipo_analyzer.core import main; main()"
```

## 项目结构

```
hkipo_analyzer/
├── app.py                          # Streamlit Web UI 入口
├── style.css                       # 前端样式
├── pyproject.toml                  # 依赖与构建配置
├── data/
│   ├── peer_comps.yaml             # 同行对比数据库（半动态：可手动更新或通过行情刷新）
│   └── backups/                    # 更新前自动备份（自动生成）
├── ui/
│   ├── __init__.py
│   ├── constants.py                # UI 常量（免责声明等）
│   ├── renderers/                  # HTML / 数据格式化渲染器
│   ├── components/                 # Streamlit 展示组件
│   ├── pages/                      # Streamlit 页面
│   └── utils/                      # UI 工具函数
├── ipo_analyzer/
│   ├── __init__.py                 # 包初始化（含 __version__，不 eager import 重依赖）
│   ├── models.py                   # 核心数据模型（dataclass + dict 兼容层）
│   ├── settings.py                 # 配置与阈值集中管理
│   ├── core.py                     # 核心编排（数据流 + 评分 pipeline）
│   ├── peer_comps.py               # 同行对比与相对估值分析（懒加载 pyyaml）
│   ├── peer_data.py                # 同行库数据服务层（YAML 读写/备份/行情更新）
│   ├── downloader.py               # AiPO 孖展数据 + HKEX 招股书下载
│   ├── parser.py                   # PDF 招股书解析（PyMuPDF / PyPDF2）
│   ├── text_extractor.py           # 文本提取与预处理
│   ├── identity_validator.py       # PDF 身份校验（公司名/股票代码匹配）
│   ├── prospectus_basic_extractor.py # 招股书基础信息提取
│   ├── analyzers/                  # 8 个分析器（估值/业务/地理/客户/现金流/产能/研发/风险）
│   ├── scoring.py                  # 评分系统（基本面/进阶框架/综合评分）
│   ├── cornerstone.py              # 基石投资者分析
│   ├── cache.py                    # 结果缓存（7天 TTL）
│   ├── history.py                  # 历史数据持久化
│   ├── report.py                   # PDF 报告生成（ReportLab）
│   ├── table_extraction.py         # 财务表格提取
│   ├── blogger_monitor/            # 博主观点监控（搜索/过滤/LLM分析/共识汇总）
│   │   ├── models.py               # 统一 Pydantic 模型
│   │   ├── config.py               # 配置加载
│   │   ├── db.py                   # SQLite 存储层
│   │   ├── searcher.py              # Tavily 搜索封装
│   │   ├── relevance_filter.py     # 相关性过滤
│   │   ├── analyzer.py             # LLM 观点提取
│   │   ├── consensus.py            # 共识汇总
│   │   ├── service.py              # Service 层编排
│   │   └── __main__.py             # CLI 入口
│   └── utils.py                    # 共用工具函数
├── scripts/
│   ├── test_peer_comps.py          # 同行对比单元测试
│   └── update_peer_comps.py        # 同行库更新 CLI 工具
├── tests/                          # pytest 回归与 UI 测试
└── temp/                           # 临时文件 / 缓存 / 输出
```

## 评分体系（0.4.0-alpha 已重构）

最终评分 = trade_score × trade_weight + fundamental_score × fundamental_weight + valuation_score × valuation_weight + theme_score × theme_weight + data_quality_score × data_quality_weight − risk_penalty

### 动态权重切换

权重根据数据阶段自动切换：

**1. 有孖展/超购/预测热度数据（live_heat）**：
| 维度 | 权重 |
|------|------|
| **trade_score** | 35% |
| **fundamental_score** | 30% |
| **valuation_score** | 20% |
| **theme_score** | 10% |
| **data_quality_score** | 5% |

**2. 无热度数据/仅招股书阶段（prospectus_only）**：
| 维度 | 权重 |
|------|------|
| **trade_score** | 20% |
| **fundamental_score** | 35% |
| **valuation_score** | 20% |
| **theme_score** | 15% |
| **data_quality_score** | 10% |

### 维度说明

| 维度 | 说明 |
|------|------|
| **trade_score** | 孖展、超购、集资规模、筹码结构（含 real_money + float_structure） |
| **fundamental_score** | 收入、毛利率、盈利、现金流、客户集中度、研发/管线 |
| **valuation_score** | PE/PS/PB、同行估值、未盈利专项估值（市值/R&D、现金runway） |
| **theme_score** | 主线候选、赛道稀缺性、港股通路径（标准化为 0-100 分） |
| **data_quality_score** | 解析置信度；同时作为 confidence_gate，数据差时限制总分上限 |
| **risk_penalty** | 仅用于重大红旗风险（现金runway < 12个月、重大诉讼、持续经营不确定性、审计保留意见、核心产品监管/临床失败、客户极端集中、财务数据异常、基石红旗） |

> **注意**：旧版「进阶框架 100分」独立卡片已废弃（`advanced_framework_score` 仍保留兼容输出，但不再作为独立主指标）。7 个维度拆分为「交易信号拆解」展示，每项显示 强/中/弱/缺失。

> **风险惩罚说明**：`risk_penalty` 只针对重大红旗风险，避免与 `fundamental_score` 重复扣分。普通风险（如一般客户集中度、普通集采提及、未盈利状态）已在基本面评分中体现，不再重复扣减。

## 估值逻辑（0.4 当前）

### 旧逻辑（0.1）
简单 PS/PE 绝对阈值判断：
- PS > 15 -> "很贵"（扣5分）
- PS > 8 -> "偏贵"（扣2分）

### 新逻辑（0.4）
三层次综合判断：
1. **绝对估值**（保留原始阈值）
2. **同行相对估值**：公司 PS vs 同行 PS 中位数（仅使用 quantitative peers）
3. **稀缺性评分**（0-10）：上市同行数量、技术壁垒、赛道类型、基石质量、增长速度

综合结论覆盖"偏贵但可解释"、"赛道合理"、"PS辅助"等场景，避免成长型/稀缺赛道公司被简单阈值误判。

## 更新日志

### 0.5.0-alpha — 2026-05-13
- **feat: 新增 `blogger_monitor` 子包**：自动搜索和分析港股新股打新博主观点，提供市场情绪参考
  - `models.py`：SearchResultModel、RelevanceResultModel、BloggerOpinionModel、ConsensusResultModel（统一 Pydantic v2）
  - `config.py`：从 `.env` 和 `sources.yaml` 加载配置
  - `db.py`：SQLite 存储层，含 blogger_posts、blogger_analysis、ipo_blogger_consensus 三张表（含 UNIQUE 索引和调试字段）
  - `searcher.py`：Tavily Search API 封装，支持关键词生成、canonical URL 规范化、API key 缺失优雅降级
  - `relevance_filter.py`：同名公司过滤、纯公告检测、时效性检查、相关性评分
  - `analyzer.py`：OpenAI 兼容 LLM API 调用，JSON repair + Pydantic 校验，失败容错
  - `consensus.py`：加权共识评分（source_weight × recency_weight × relevance_weight × content_quality_weight），coverage_score，data_quality_warning
  - `service.py`：编排搜索->过滤->分析->共识完整流程
  - `__main__.py`：CLI 入口，支持 `run`/`search`/`consensus` 子命令
- **feat: 前端博主观点卡片**：`detail_view.py` 新增 `_render_blogger_consensus`，展示综合情绪、共识分、观点分布、主要理由/风险、代表性文章、调试摘要
- **feat: 历史页面搜索按钮**：`history_page.py` 新增"🔍 搜索博主观点"按钮，支持手动触发
- **fix: post_listing.py 中签复盘解析增强**：支持 3 种英文 POOL 表格格式（全额中签/部分中签+N Shares/甲乙组标准格式）
- **fix: detail_view.py 表格对齐与基础信息**：所有 `<td>` 添加 `padding:8px;text-align:right;`；无 POOL 数据时显示公配信息（公开发售、有效申请、整体中签率）
- **fix: history.py 评分重算与数据保护**：`prospectus text` 为空时回退到 PDF；重分析 `parse_success=false` 时保留原分数；保护 `post_listing_actual` 数据不被覆盖
- **fix: Python 3.9 兼容性**：所有 blogger_monitor 模块使用 `Optional[X]`/`Union[X, Y]` 替代 `X | Y` 语法
- **tests: 新增 7 个测试文件**：`test_blogger_models`、`test_blogger_db`、`test_blogger_searcher`、`test_blogger_relevance_filter`、`test_blogger_analyzer`、`test_blogger_consensus`、`test_blogger_service`，共 92 个测试用例

### 0.4.1-alpha — 2026-05-09
- **fix: peer_comps.py _split_peer_samples 修正 fallback 逻辑**：hk_quant >= 2 时只用港股；hk_quant < 2 且 all listed quant >= 2 时 fallback 到 hk + non-HK；仅 1 个样本时标记 `quantitative_basis=single_reference`，避免有 non-HK 数据却误判"样本不足"
- **fix: scoring.py 估值调整去重与 biotech 保护**：valuation_framework 已含 relative valuation 时不再重复扣 PS/同行偏贵；仅 quant_count >= 2 且 premium > 100% 才允许 severe penalty；低收入 biotech（revenue_too_small_for_ps=True）PS 只提示不硬扣；license_upfront_driven biotech 不用 PS 溢价直接扣分
- **feat: scoring.py 输出完整 score_trace**：`raw_weighted_score`、`peer_adj`、`val_penalty`、`cap_reason`、`final_score_before_cap`、`final_score_after_cap`，解释最终分数来源
- **fix: industry_router.py 强化 -B 识别**：删除 `-w ` biotech 关键词误触发；`listing_suffix=B` 或名称含 `-B` 时强制 `is_biotech=True`、`sector=healthcare`；`-W` 不作为 biotech 依据；支持从 `company_name_aliases` / `extracted_english_name` / `extracted_company_name` 中识别 `-B`
- **fix: parser.py 币种与单位分离**：增强 `financial_currency` 识别（HKD million / HK$'000 / RMB'000 / US$ million 等）；新增 `financial_currency_unit` 与 `financial_currency_source`；输出 `listing_suffix`；确保 thousand 单位自动转为 million
- **fix: analyzers.py 统一币种口径与临床阶段枚举**：收入增长率统一使用 `revenue_latest_hkd` vs `revenue_previous_hkd`；`latest_clinical_stage` 统一为 `approved/nda/phase_iii/phase_ii/early_stage`；低收入 biotech 禁止 valuation_label 为"很贵/明显偏贵"；新增 `biotech_valuation_framework`（pipeline_based / ps_reference / market_cap_rd）
- **fix: core.py 避免重复扣分与 parse_success 提示**：`final_score` 输出 `score_trace`；`parse_success=False` 时 `analysis_mode="market_only"` 并提示"仅热度参考"；`_calculate_risk_penalty` 检查 quality reasons 避免同一风险重复扣分
- **feat: 新增 8 个回归测试**：`test_peer_fallback_when_only_one_hk_peer`、`test_biotech_b_suffix_forces_special_valuation`、`test_w_suffix_not_biotech_keyword`、`test_low_revenue_biotech_ps_not_hard_penalty`、`test_currency_growth_uses_same_fx_basis`、`test_score_trace_contains_all_adjustments`、`test_no_prospectus_market_only_mode`、`test_no_double_count_peer_overvaluation_penalty`

### 0.4.0-alpha — 2026-05-07
- **refactor: 进阶框架拆分为交易信号拆解**：`AdvancedIPOFrameworkAnalyzer` 重命名为 `SignalComponentAnalyzer`，不再输出独立 100 分主指标；新增 `signal_breakdown` 字段供 UI 展示（资金热度/筹码弹性/基石质量/估值解释/主题催化/港股通路径/数据置信度）
- **refactor: ScoringSystem.calculate 新五维权重**：`trade_score×0.35 + fundamental_score×0.30 + valuation_score×0.20 + theme_score×0.10 + data_quality_score×0.05 − risk_penalty`；`advanced_score_adjustment` 已废弃（固定为 0）
- **feat: 未盈利 biotech 特殊处理**：PE 显示"PE不适用"；估值框架显示"PS辅助/管线估值/市值-R&D/现金runway"；收入极小时禁止 PS 单独拉高/拉低分；同行样本不足时仅显示"定性参考"
- **fix: dataclass 字段同步**：ValuationResult 新增 `net_profit_hkd_million`、`adjusted_profit_hkd_million`、`financial_currency`；PeerComparisonResult 新增 `quantitative_peers`、`qualitative_peers`、`quantitative_peer_count`、`qualitative_peer_count`、`peer_sample_warning`
- **fix: peer_comps.py quantitative/qualitative 分层**：`_split_peer_samples` 提取为独立函数，median 和 premium 仅使用 quantitative peers；少于 2 家时不输出强相对估值结论
- **fix: 未盈利公司估值展示**：detail_view.py 中亏损公司 PE 显示"PE不适用"，增加估值框架、市值/R&D、现金runway、临床阶段展示
- **fix: 统一 dry-run/write 统计**：peer_data.py、update_peer_comps.py、peer_admin_page.py 统一返回 `total/processed/previewed/updated/skipped/failed/details`
- **feat: 新增 tests/test_regression_cases.py**：8 个回归测试覆盖 alias 过滤、quantitative 分层、样本不足、未盈利标签、字段持久化、信号拆解、新权重、进阶框架废弃

### 0.3.0-alpha — 2026-05-06
- **fix: 基础依赖隔离**：`__init__.py` 不再 eager import parser/core/report 等重模块，`import ipo_analyzer` 不再触发 PyPDF2
- **fix: peer_comps.py lazy import yaml**：`import yaml` 移入 `_load_peer_data()` 内部，pyyaml 缺失时只 warning 不崩溃
- **新模块: `ipo_analyzer/peer_data.py`**：PeerDataStore（YAML 读写+自动备份）、YahooFinanceProvider（yfinance 行情获取）、PeerMetricsUpdater（批量更新入口）
- **新脚本: `scripts/update_peer_comps.py`**：支持 `--all --dry-run`、`--stale-only --write`、`--ticker XXXX.HK` 等命令
- **新页面: `ui/pages/peer_admin_page.py`**：Streamlit 同行库管理页，含 meta 展示、筛选表格、刷新按钮
- **app.py 导航增加**："同行库管理"页面，通过侧边栏切换
- **全局 sector fallback**：当 sector 不匹配时，在所有 sector 搜索 subsector，避免漏匹配
- **unmatched_peer_candidates**：招股书文本中提取疑似同行名，不在本地库中的放入候选列表供人工审核
- **修复 YAML 路径问题**：英矽智能 ticker 更新为 03696.HK，更新脚本支持港股/A 股/美股 ticker 转换
- **新增 `.gitignore`**：排除 `__pycache__`、`temp/*.pdf`、`data/backups/` 等

### 0.2.0-alpha — 2026-05-05
- **新增 `data/peer_comps.yaml`**：同行对比数据库，支持 hardtech（机器人/AI芯片）和 healthcare（AI制药/创新药/医疗器械/CXO）共6个细分赛道
- **新增 `ipo_analyzer/peer_comps.py`**：`PeerComparableAnalyzer` — 赛道匹配 -> 同行识别 -> 相对估值计算 -> 稀缺性评分 -> 估值定位判断
- **重构 `ValuationAnalyzer`**：支持绝对估值 + 相对估值 + 稀缺性的综合估值标签，对收入极小的科技/生物科技公司给出"PS辅助"提示
- **重构 `AdvancedIPOFrameworkAnalyzer._analyze_valuation_framework`**：满分20分拆为 绝对估值8分 + 同行相对估值8分 + 稀缺性4分
- **重构 `ScoringSystem.calculate`**：新增 `peer_valuation_adjustment`（+-6分），对稀缺赛道高估值给予容忍度加分
- **修改 `core.py._calculate_final_score`**：pipeline 中插入 `PeerComparableAnalyzer`（在估值分析前调用）
- **修改 `app.py`**：详情页新增同行对比卡片（细分赛道、估值对比、同行列表）
- **修改 `report.py`**：PDF 报告新增同行对比表格
- **新增 `scripts/test_peer_comps.py`**：4 个测试用例覆盖乐动机器人、剂泰科技、无同行回退、完整 pipeline
- **全量 print->logger 迁移**：downloader(17处)、analyzers(8处)、parser(6处) 的 `print()` 全部替换为 `logger`

### 0.1.0-alpha — 初始版本
- Streamlit dashboard + 手动上传分析
- AiPO 孖展数据 + HKEX 招股书下载
- 8 个分析器 + 3 层评分系统
- PDF/JSON 报告导出
- 结果缓存 + 历史归档

## 维护说明

- **同行数据库**：`data/peer_comps.yaml` 需手动维护同行估值数据。`source_date` 和 `data_quality` 字段标记数据时效性
- **新增细分赛道**：在对应 sector 下添加新条目，并确保 `keywords` 能匹配招股书文本
- **Private 公司**：不参与 PS/PE 中位数计算，仅做定性参考
