# 港股 IPO 打新分析 (hkipo_analyzer)

**当前版本：0.5.3-alpha；状态：开发中，仅供研究参考**

> 🤖 本项目由 AI（Claude Code + deepseek）全流程驱动完成，从需求分析、架构设计、代码实现到测试和部署，均为 AI 自主生成。

自动获取港股招股 IPO 列表，下载招股书 PDF，解析财务数据，运行多维度评分，并通过 FastAPI 后端 + Next.js 前端展示分析结果、历史记录与 PDF/JSON 报告。

## 快速开始

### 方式一：本地开发（前后端分离启动）

适合日常开发和调试，前后端热重载。

```bash
# 1. 安装依赖
cd hkipo_analyzer
python3 -m pip install -e ".[dev]"

# 2. 配置环境变量
cp .env.example .env
# 如需接入外部服务，可按需填写 .env；本地分析无需 API Token

# 3. 启动 FastAPI 后端（终端 1）
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# 访问 http://127.0.0.1:8000/docs 查看 API 文档

# 4. 启动 Next.js 前端（终端 2）
cd frontend
npm install
npm run dev
# 访问 http://localhost:3000
```

### 方式二：Docker Compose 部署（推荐生产环境）

适合一次性启动完整服务栈，无需本地安装 Python/Node。

```bash
# 1. 配置环境变量
cp .env.example .env
# 如需接入外部服务，可按需填写 .env；本地分析无需 API Token

# 2. 仅启动 API + nginx（最小部署，无前端界面，仅提供 API）
docker compose up -d fastapi nginx
# 访问 http://localhost/api/health

# 3. 启动完整栈（API + nginx + Next.js 前端）
NGINX_TEMPLATE=full docker compose --profile frontend up -d
# 访问 http://localhost（前端）→ nginx 自动代理 /api/ 到 FastAPI
```

> **部署拓扑说明**：
> - `nginx.conf`（默认）：`/` 返回提示文本，仅 `/api/` 代理到 FastAPI
> - `nginx.full.conf`（完整栈）：`/` 代理到 Next.js，`/api/` 代理到 FastAPI
> - 切换模板：`NGINX_TEMPLATE=full docker compose up -d nginx`

## 项目结构

```
hkipo_analyzer/
├── pyproject.toml                  # 依赖与构建配置
├── data/
│   ├── peer_comps.yaml             # 同行对比数据库（半动态：可手动更新或通过行情刷新）
│   └── backups/                    # 更新前自动备份（自动生成）
├── api/                            # FastAPI 后端：REST API、任务队列、历史与报告接口
├── frontend/                       # Next.js 前端：上传、历史、详情、同行库、重新分析
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
├── tests/                          # pytest 回归测试
└── storage/                        # 本地运行数据：历史库、招股书样本、上传目录
```

## 评分体系（0.4.0-alpha 已重构）

最终评分 = trade_score × trade_weight + fundamental_score × fundamental_weight + valuation_score × valuation_weight + theme_score × theme_weight + data_quality_score × data_quality_weight − risk_penalty

### 动态权重切换

权重根据数据阶段自动切换：

**1. 有孖展/超购/预测热度数据（live_heat，2026 严格口径）**：
| 维度 | 权重 |
|------|------|
| **trade_score** | 25% |
| **fundamental_score** | 35% |
| **valuation_score** | 25% |
| **theme_score** | 10% |
| **data_quality_score** | 5% |

**2. 无热度数据/仅招股书阶段（prospectus_only，2026 严格口径）**：
| 维度 | 权重 |
|------|------|
| **trade_score** | 15% |
| **fundamental_score** | 40% |
| **valuation_score** | 25% |
| **theme_score** | 15% |
| **data_quality_score** | 5% |

### 维度说明

| 维度 | 说明 |
|------|------|
| **trade_score** | 孖展、超购、集资规模、筹码结构（含 real_money + float_structure） |
| **fundamental_score** | 收入、毛利率、盈利、现金流、客户集中度、研发/管线 |
| **valuation_score** | PE/PS/PB、同行估值、未盈利专项估值（市值/R&D、现金runway） |
| **theme_score** | 主线候选、赛道稀缺性、港股通路径（标准化为 0-100 分） |
| **data_quality_score** | 解析置信度；同时作为 confidence_gate，数据差时限制总分上限 |

> **2026 严格打新口径**：`ipo_trade_score` 现在代表严格打新分，不再等同于纯交易热度；它由原始交易信号、长期投资分、估值分综合生成，并对高估值、弱赛道、弱基本面公司设置封顶。原始热度保留在 `raw_trade_signal_score`。
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

### 0.5.4-alpha — 2026-05-22

- **refactor: 评分系统管道化重构**：将 `ScoringSystem` (~1200行) 拆分为类型安全、职责清晰的评分管道
  - 新建 `ipo_analyzer/scoring/` 子包，含 6 个独立组件：
    - `AnalyzerOutputAdapter`：分析器 dict → 强类型 `ScoringInput`
    - `DimensionScorer`：五维原始分计算（trade/fundamental/valuation/theme/data_quality）
    - `AdjustmentEngine`：集中管理 peer/valuation/pricing_gap/risk/cornerstone 调整项
    - `StrategyScorer`：long_term_score / strict_ipo_score 策略评分
    - `Recommender`：推荐/原因/等级评定（与分数计算解耦）
    - `ScoringPipeline`：串联所有组件，每步自动记录 `ScoreTrace`
  - 新增核心类型契约：`ScoringInput`、`DimensionScores`、`Adjustments`、`StrategyScores`、`ScoringResult`、`ScoreTrace`、`WeightProfile`
  - 保留 `scoring.py` 作为兼容薄层，现有调用方零改动
  - `settings.py` 新增 `DimensionThresholds` 和 `AdjustmentThresholds`
  - `is_biotech()` 统一提取至 `_utils.py`，替代散落在 valuation/scoring/quality/signal 四处的重复判断
  - 新增 7 个测试文件、46 个测试用例全部通过（含 8 个原有回归测试）

### 0.5.3-alpha — 2026-05-19
- **change: 2026 严格打新评分**：降低热度权重，提高基本面与估值权重；`ipo_trade_score` 改为严格打新分，新增 `raw_trade_signal_score`、`strict_ipo_score`、`strict_scoring_profile`
- **risk: 高估值封顶**：高估值叠加弱赛道/弱基本面时，推荐降为谨慎区间，避免单靠超购倍数给出积极结论
- **ui: 前端筛选同步收紧**：首页“打新高分”从 ≥60 调整为 ≥65，详情页展示严格打新分、原始热度信号、估值压力

### 0.5.2-alpha — 2026-05-19
- **change: 移除项目内 API Token 认证**：上传、重新分析、实时刷新、历史导出、报告下载、同行库刷新、博主观点搜索均可直接使用，不再需要 `Authorization` 请求头或前端 Token 输入框
- **docs: 开箱即用说明更新**：`.env.example`、本地启动、Docker 启动和架构迁移记录均移除 Token 配置要求
- **tests: API 测试同步调整**：删除旧 Token 认证断言，改为验证无 Token 情况下核心接口可正常创建任务或返回业务状态

### 0.5.1-alpha — 2026-05-15
- **security: API 端点认证加固**：曾为敏感 GET 端点添加 Token 认证；已在 0.5.2-alpha 按开箱即用目标移除
- **security: FileResponse 路径遍历防护**：`StorageService` 新增 `validate_path` 方法，校验文件路径在 `storage_base_path` 目录内，路径遍历攻击返回 403
- **security: 上传文件大小限制**：`APIConfig` 新增 `max_upload_size_mb`（默认 50MB），超限返回 HTTP 413
- **security: Nginx 安全响应头**：`nginx.conf` 和 `nginx.full.conf` 添加 `X-Content-Type-Options`、`X-Frame-Options`、`X-XSS-Protection`、`Content-Security-Policy`
- **fix: SQLite 连接泄漏**：`BloggerMonitorDB` 改为 FastAPI 依赖注入（`get_blogger_db`），请求结束后自动关闭连接
- **fix: blogger_monitor 硬编码路径**：`service.py` 中 `temp/ipo_history.json` 改为读取 `STORAGE_BASE_PATH` 环境变量
- **fix: HistoryService SQL 安全**：`update_job_status` 中 f-string 动态 SQL 改为 `COALESCE` 静态 SQL
- **fix: .gitignore 遗漏**：添加 `storage/blogger_monitor.db*`、`storage/ipo_history.json`、`storage/results_cache.json`、`.env.local`、`.env.production`、`.venv/`、`venv/`
- **fix: 前端下载链接认证**：`downloadJobJson`/`downloadJobPdf` 曾添加 `token` 参数；已在 0.5.2-alpha 移除
- **fix: 代码规范清理**：`live.py`/`blogger.py`/`history.py`/`peers.py`/`reports.py` 重复导入修复；`analyze_worker.py` 中 `asyncio.get_event_loop()` → `asyncio.get_running_loop()`
- **fix: 前端 ESLint 修复**：4 个 `react-hooks/set-state-in-effect` error 和 8 个 warning 全部修复
  - `history/page.tsx`、`page.tsx`、`peers/page.tsx`、`BloggerConsensusCard.tsx`：useEffect 中 `load()` 调用改为内联 `async function fetchData()` + `cancelled` flag 模式
  - `DetailViewExtras.tsx`：移除未使用的 `useMemo`、`scoreHex`；`[_, data]` → `[, data]`
  - `page.tsx`：移除未使用的 `job` 变量
- **tests: API 测试扩充**：新增 4 个测试文件（test_live.py、test_history.py、test_peers.py、test_blogger.py），共 17 个新测试用例，总计 45 个测试全部通过

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
- **refactor: ScoringSystem.calculate 新五维权重**：曾采用 `trade_score×0.35 + fundamental_score×0.30 + valuation_score×0.20 + theme_score×0.10 + data_quality_score×0.05 − risk_penalty`；已在 2026 严格口径中调整为更重基本面和估值
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

## 架构迁移记录（FastAPI + Next.js）

> **状态：迁移已完成 ✅ + 安全审计通过 ✅（2026-05-15 审计）**

### 迁移背景

原架构为 **Streamlit 单体应用**（`app.py` + `ui/`），所有前后端逻辑耦合在 Python 进程中。新架构拆分为：

- **Backend**：`api/` — FastAPI 异步服务，提供 REST API + 异步任务队列
- **Frontend**：`frontend/` — Next.js 16 + React 19 + Tailwind CSS 4，独立部署
- **Gateway**：`nginx.conf` / `nginx.full.conf` — 反向代理统一入口

### 新架构目录

```
# Backend (FastAPI)
api/
├── main.py                 # FastAPI 入口，lifespan、CORS、路由挂载
├── config.py               # 环境配置（CORS、并发数、存储路径）
├── routers/
│   ├── health.py           # /api/health, /api/version
│   ├── analyze.py          # /api/analyze/upload, reanalyze, jobs, result
│   ├── live.py             # /api/live/results, analyze, status
│   ├── history.py          # /api/history/records, export
│   ├── reports.py          # /api/reports/jobs/{id}/json, pdf
│   ├── peers.py            # /api/peers, peers/refresh
│   └── blogger.py          # /api/blogger/{code}, blogger/{code}/search
├── schemas/                # Pydantic v2 模型
├── services/
│   ├── storage_service.py  # 上传/结果文件存储
│   └── history_service.py  # SQLite + WAL 任务与历史管理
├── workers/
│   └── analyze_worker.py   # 信号量控制的异步分析执行器
└── tests/                  # 45 个 API 测试（全量通过）

# Frontend (Next.js)
frontend/
├── src/app/
│   ├── page.tsx            # 首页：系统状态控制台（SSR）
│   ├── upload/page.tsx     # PDF 上传
│   ├── history/page.tsx    # 任务历史列表
│   ├── jobs/[jobId]/page.tsx  # 任务详情与结果展示
│   └── reanalyze/page.tsx  # 按股票代码重新分析
├── src/components/results/ # 结果卡片：评分、估值、同行、基石、风险等
├── src/lib/api.ts          # 同构 API 客户端（服务端 fetch + 客户端 upload）
└── src/lib/types.ts        # TypeScript 类型定义
```

### 部署方式

```bash
# 仅启动 API + nginx（默认）
docker compose up -d fastapi nginx

# 启动完整栈（含 Next.js 前端）
NGINX_TEMPLATE=full docker compose --profile frontend up -d
```

- 默认 `nginx.conf` 仅暴露 API，根路径返回提示文本
- `nginx.full.conf` 将 `/` 代理到 Next.js，同时保留 `/api/` 到 FastAPI

### 迁移审计结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| FastAPI 服务启动 | ✅ | `api/main.py` lifespan 初始化数据库与目录 |
| 健康/版本端点 | ✅ | `/api/health`、`/api/version` 正常 |
| 上传分析流程 | ✅ | 上传 PDF → 创建任务 → 异步分析 → 存储结果 |
| 重新分析流程 | ✅ | 按股票代码触发重新分析 |
| 任务状态查询 | ✅ | 支持轮询 `jobs/{id}` 和列表 `jobs` |
| 结果获取与展示 | ✅ | 前端 Job 详情页完整展示 9 个结果卡片 |
| API Token 门槛 | 已移除 | 上传、重新分析、刷新、下载均可直接使用 |
| Next.js 构建 | ✅ | `output: "standalone"` 构建成功 |
| Docker 镜像 | ✅ | FastAPI、Next.js 均含 Dockerfile |
| docker-compose | ✅ | 支持 fastapi / nginx / nextjs；旧 Streamlit profile 已移除 |
| API 测试 | ✅ | 45 个测试全部通过 |
| 原有回归测试 | ✅ | 255 个测试全部通过 |
| 前端 ESLint | ✅ | 零 error、零 warning |
| 前端构建 | ✅ | Next.js 16 standalone 构建成功 |

### 待完善项

1. ~~**`pyproject.toml` 依赖缺失**~~ ✅ **已修复**
2. ~~**`.env.example` 过时**~~ ✅ **已修复**
3. ~~**CI 未覆盖 API 测试**~~ ✅ **已修复**
4. ~~**前端无 API Proxy**~~ ✅ **已修复**：生产环境通过 nginx 统一代理，`/` → Next.js，`/api/` → FastAPI。
5. ~~**Streamlit 过渡期**~~ ✅ **已下线**：新前端已完整实现原核心功能，旧 `app.py`/`ui/`/`style.css` 已删除。

### 瘦身记录（2026-05-18）

本次清理后，项目从约 **1.3G** 降至约 **158M**。保留形态为 **FastAPI 后端 + Next.js 前端**。

- 删除旧 Streamlit 单体入口：`app.py`、`ui/`、`style.css`、`.streamlit/`、`Dockerfile.streamlit`
- 移除 Python 依赖中的 `streamlit`，并删除 `docker-compose.yml` 的 `transition/streamlit` 服务
- 后端 `api/routers/history.py` 不再依赖旧 `ui.renderers.data_formatter`
- 删除可再生成的大目录：`frontend/node_modules`、`frontend/.next`、测试截图、dogfood 输出、临时 PDF/重分析缓存
- 保留业务运行数据：`storage/` 中的历史库、招股书样本和上传目录

### 功能迁移完成记录（2026-05-15）

| 原 Streamlit 功能 | 新前端页面 | 后端 API | 状态 |
|---|---|---|---|
| 首页 Dashboard（实时IPO列表、筛选、刷新） | `/` | `GET /api/live/results`, `POST /api/live/analyze` | ✅ 已完成 |
| 手动上传分析 | `/upload` | `POST /api/analyze/upload` | ✅ 已完成 |
| 历史归档（搜索、筛选、排序） | `/history` | `GET /api/history/records` | ✅ 已完成 |
| 任务详情与结果展示 | `/jobs/[jobId]` | `GET /api/analyze/jobs/{id}/result` | ✅ 已完成 |
| 重新分析 | `/reanalyze` | `POST /api/analyze/reanalyze` | ✅ 已完成 |
| 同行库管理 | `/peers` | `GET /api/peers`, `POST /api/peers/refresh` | ✅ 已完成 |
| 博主观点搜索与展示 | Job 详情页卡片 | `GET /api/blogger/{code}`, `POST /api/blogger/{code}/search` | ✅ 已完成 |
| 报告导出（PDF/JSON） | Job 详情页下载按钮 | `GET /api/reports/jobs/{id}/pdf`, `/json` | ✅ 已完成 |

---

## 维护说明

- **同行数据库**：`data/peer_comps.yaml` 需手动维护同行估值数据。`source_date` 和 `data_quality` 字段标记数据时效性
- **新增细分赛道**：在对应 sector 下添加新条目，并确保 `keywords` 能匹配招股书文本
- **Private 公司**：不参与 PS/PE 中位数计算，仅做定性参考
