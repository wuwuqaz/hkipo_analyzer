# HK IPO Analyzer — Streamlit → React + FastAPI 迁移设计

**日期**: 2026-05-14
**版本**: 1.1
**决策**: 方案 A→C 渐进式迁移，最终下线 Streamlit

---

## v1.1 变更摘要

| # | 变更 | 章节 |
|---|------|------|
| 1 | 分析接口改为异步任务模型 (job_id) | §4.1, §4.7, §9 |
| 2 | "零修改"改为"核心逻辑不重写，边界层最小适配" | §1, §5, §9 |
| 3 | 补充数据一致性设计 (storage 布局 + 唯一事实源) | §11 (新增) |
| 4 | 补充最低权限保护 (Basic Auth / API Token) | §12 (新增) |
| 5 | 补充 Next.js 选型理由 | §8.1 (新增) |
| 6 | 补充 Tailwind CSS 4.x 兼容性说明 | §8.2 (新增) |
| 7 | 补充 FastAPI 并发限制 (最多 1-2 个分析任务) | §13 (新增) |
| 8 | 增加基础接口 (health, version) | §4.7 (新增) |
| 9 | 增加 P0.5 阶段 (API skeleton + 核心服务) | §7 |

---

## 1. 背景与目标

### 当前状态
- **框架**: Streamlit (Python)
- **代码量**: ipo_analyzer/ 19,668 行 (纯业务逻辑，零 Streamlit 依赖) + ui/ 3,274 行 (Streamlit UI) + app.py 77 行
- **部署**: 本地运行
- **主题**: 已完成赛博朋克暗黑终端视觉改造

### 迁移目标
- 将前端从 Streamlit 迁移到 **Next.js + shadcn/ui**，实现"暗黑赛博朋克金融终端"风格
- 将后端封装为 **FastAPI** REST API
- 部署方式：**私有部署**（投研团队内部使用）
- 迁移策略：**渐进式**，逐页迁移，Streamlit 过渡期保留

### 核心逻辑保留原则
- `ipo_analyzer/` 核心业务逻辑**不重写**，尽量零修改
- 允许 `report.py`、`history.py`、`models.py` 做边界层最小适配（如返回值结构调整、存储路径参数化）
- 如果必须改核心模块（core.py, scoring.py, parser.py 等），**必须添加 regression test** 才能合入
- 所有适配通过 `api/services/` 薄适配层完成，不在核心模块中引入 FastAPI 依赖

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────┐
│                    Nginx (反向代理)                    │
│  / → Next.js (3000)    /api → FastAPI (8000)         │
│  /admin → Streamlit (8501) [过渡期只读，最终移除]      │
│  Basic Auth / API Token 保护写入接口                   │
└──────────────┬───────────────┬───────────────────────┘
               │               │
    ┌──────────▼───────┐  ┌───▼──────────────┐
    │  Next.js + shadcn │  │  FastAPI          │
    │  (React 前端)     │  │  (Python API)     │
    │  - Dashboard      │  │  - /api/ipo/*     │
    │  - IPO 详情       │  │  - /api/analyze   │
    │  - 上传/历史      │  │  - /api/peer/*    │
    │  - 同行管理       │  │  - /api/blogger   │
    └──────────────────┘  └───┬──────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  ipo_analyzer/       │
                    │  (纯 Python 逻辑)    │
                    │  核心逻辑不重写       │
                    └─────────────────────┘
```

---

## 3. 目录结构

```
hkipo_analyzer/
├── api/                              # FastAPI 后端 (新增)
│   ├── __init__.py
│   ├── main.py                       # FastAPI app 入口, CORS, 中间件, 认证
│   ├── config.py                     # API 配置
│   ├── deps.py                       # 依赖注入 (DB session, settings, auth)
│   ├── auth.py                       # Basic Auth / API Token 验证
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── health.py                 # /api/health, /api/version
│   │   ├── ipo.py                    # IPO 列表与详情
│   │   ├── analyze.py                # 上传分析、重新分析 (任务模型)
│   │   ├── peer.py                   # 同行对比数据
│   │   ├── blogger.py                # 博主观点
│   │   ├── history.py                # 历史记录
│   │   └── report.py                 # PDF 报告下载
│   ├── schemas/                      # Pydantic 请求/响应模型
│   │   ├── __init__.py
│   │   ├── ipo.py
│   │   ├── analyze.py                # JobCreate, JobStatus, AnalyzeResult
│   │   ├── peer.py
│   │   ├── blogger.py
│   │   └── common.py
│   ├── services/                     # 薄适配层，调用 ipo_analyzer/
│   │   ├── __init__.py
│   │   ├── ipo_service.py
│   │   ├── analyze_service.py        # 任务调度、并发控制
│   │   ├── peer_service.py
│   │   ├── blogger_service.py
│   │   ├── history_service.py
│   │   └── storage_service.py        # storage/ 目录管理
│   └── workers/                      # 后台任务执行
│       ├── __init__.py
│       └── analyze_worker.py         # PDF 分析 worker
│
├── frontend/                         # Next.js 前端 (新增)
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── components.json               # shadcn/ui 配置
│   ├── src/
│   │   ├── app/                      # App Router 页面
│   │   │   ├── layout.tsx            # 全局 layout
│   │   │   ├── page.tsx              # Dashboard
│   │   │   ├── ipo/[stockCode]/page.tsx
│   │   │   ├── upload/page.tsx
│   │   │   ├── history/page.tsx
│   │   │   └── peers/page.tsx
│   │   ├── components/
│   │   │   ├── ui/                   # shadcn/ui (暗黑主题)
│   │   │   ├── layout/              # Sidebar, Header
│   │   │   ├── dashboard/           # DashboardCard, IPOTable
│   │   │   ├── ipo/                 # ScoreCard, RiskPanel, PeerTable
│   │   │   └── charts/              # Recharts 组件
│   │   ├── lib/
│   │   │   ├── api.ts               # API client (含 job 轮询)
│   │   │   ├── utils.ts
│   │   │   └── constants.ts
│   │   └── styles/
│   │       └── globals.css           # 暗黑终端 CSS 变量
│   └── public/
│
├── storage/                          # 统一数据存储 (新增)
│   ├── uploads/                      # 上传的 PDF 招股书
│   ├── results/                      # 分析结果 JSON
│   ├── tmp/                          # 临时文件 (分析中间产物)
│   └── history.db                    # SQLite 历史记录 (唯一事实源)
│
├── ipo_analyzer/                     # 纯 Python 业务逻辑 (核心不重写)
├── ui/                               # Streamlit UI (过渡期保留，降级为只读)
├── app.py                            # Streamlit 入口 (过渡期保留)
├── style.css                         # Streamlit 样式 (过渡期保留)
├── docker-compose.yml                # 新增
├── nginx.conf                        # 新增 (含 Basic Auth 配置)
└── requirements.txt                  # 新增 fastapi, uvicorn, aiosqlite
```

---

## 4. FastAPI 接口设计

### 4.1 分析接口（异步任务模型）

PDF 分析是 CPU/内存密集型操作（解析 + LLM 调用），耗时 30s-5min，不适合同步返回。采用任务模型：

| 方法 | 路径 | 说明 | 认证 | 请求体 | 响应 |
|------|------|------|------|--------|------|
| POST | `/api/analyze/upload` | 提交上传分析任务 | ✅ | multipart/form-data (pdf + stock_code + company_name) | `JobResponse{job_id, status}` |
| POST | `/api/analyze/reanalyze` | 提交重新分析任务 | ✅ | JSON (stock_code, company_name, historical_market_data) | `JobResponse{job_id, status}` |
| GET | `/api/analyze/jobs/{job_id}` | 查询任务状态 | - | - | `JobStatusResponse{job_id, status, progress?, error?}` |
| GET | `/api/analyze/jobs/{job_id}/result` | 获取任务结果 | - | - | `AnalyzeResponse` (仅 status=success 时可用) |

**任务状态机**:

```
queued → running → success
                 → failed
```

- `queued`: 任务已入队，等待 worker 拾取
- `running`: worker 正在执行分析
- `success`: 分析完成，可通过 `/result` 获取结果
- `failed`: 分析失败，`error` 字段包含错误信息

**前端轮询策略**: 提交后每 2s 轮询 `/jobs/{job_id}`，status=success 时拉取结果，status=failed 时显示错误。后续可升级为 WebSocket/SSE。

**第一阶段实现**: SQLite `analyze_jobs` 表 + FastAPI BackgroundTasks + asyncio Semaphore 并发控制。后续可升级 Celery/RQ。

### 4.2 IPO 数据接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/ipo/list` | 当前招股列表 (支持 ?status=, &sort_by=, &min_score=) | - |
| GET | `/api/ipo/{stock_code}` | IPO 完整详情 | - |
| GET | `/api/ipo/{stock_code}/score` | 评分拆解 | - |
| GET | `/api/ipo/{stock_code}/risks` | 风险明细 | - |

### 4.3 同行接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/peer/comps/{stock_code}` | 同行对比数据 | - |
| GET | `/api/peer/data` | 同行库列表 | - |
| PUT | `/api/peer/data/{stock_code}` | 更新同行数据 | ✅ |

### 4.4 博主接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/blogger/consensus/{stock_code}` | 博主观点共识 | - |
| POST | `/api/blogger/refresh/{stock_code}` | 刷新博主数据 | ✅ |

### 4.5 历史接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/history` | 历史分析列表 | - |
| GET | `/api/history/{stock_code}` | 历史详情 | - |
| DELETE | `/api/history/{stock_code}` | 删除历史记录 | ✅ |

### 4.6 报告接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/report/{stock_code}/pdf` | 下载 PDF 报告 | - |

### 4.7 基础接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/health` | 健康检查 (返回 DB 连接状态、worker 状态) | - |
| GET | `/api/version` | 版本信息 (app version, ipo_analyzer version, python version) | - |

---

## 5. Python 逻辑保留策略

### 5.1 核心模块 (不重写，尽量零修改)

| 模块 | 行数 | 核心函数 |
|------|------|----------|
| core.py | 1217 | `analyze_uploaded_pdf()`, `reanalyze_ipo()` |
| scoring.py | 784 | `_run_scoring_pipeline()` |
| parser.py | 892 | `ProspectusParser.parse_pdf_file()` |
| downloader.py | 431 | `ProspectusDownloader.download_from_hkex()` |
| peer_comps.py | 1409 | 同行对比逻辑 |
| cornerstone.py | 1786 | 基石投资者分析 |
| signal_analyzer.py | 1064 | 交易信号分析 |
| post_listing.py | 983 | 上市后跟踪 |
| quality_analyzer.py | 346 | 质量分析 |
| market_heat.py | 492 | 市场热度 |
| board_heat.py | 231 | 董事会热度 |
| analyzers/* | ~3000 | 各领域分析器 |
| blogger_monitor/* | ~1800 | 博主监控全模块 |
| settings.py | 471 | SETTINGS 单例 |
| utils.py | 244 | 工具函数 |
| validators.py | 208 | 数据验证 |
| identity_validator.py | 169 | 身份校验 |
| industry_router.py | 255 | 行业路由 |
| cache.py | 64 | 缓存 |

**规则**: 如果必须修改上述模块，必须添加 regression test 才能合入。

### 5.2 边界层适配 (最小改动)

| 模块 | 行数 | 适配内容 |
|------|------|----------|
| report.py | 1228 | PDF 生成改为返回文件流 (StreamingResponse)；输出路径参数化，指向 `storage/results/` |
| models.py | 778 | Pydantic 模型复用；API schemas 继承或引用现有模型；如有字段缺失则在 API schemas 中补充而非改原模型 |
| history.py | 616 | JSON 存储迁移到 SQLite (`storage/history.db`)；写入逻辑封装到 `history_service.py`，原模块保留读取兼容 |

### 5.3 不保留 (Streamlit 特有)

| 模块 | 行数 | 处理 |
|------|------|------|
| ui/ 全部 | 3274 | React 重写，最终删除 |
| app.py | 77 | 最终删除 |
| style.css | ~700 | 迁移到 Tailwind CSS |

---

## 6. 前端页面映射

| Streamlit 页面 | Next.js 页面 | 迁移优先级 |
|----------------|-------------|-----------|
| DashboardPage | `/` (page.tsx) | P1 |
| DetailView | `/ipo/[stockCode]` | P2 |
| UploadPage | `/upload` | P3 |
| ReanalyzePage | `/ipo/[stockCode]?reanalyze=true` | P3 |
| HistoryPage | `/history` | P4 |
| PeerAdminPage | `/peers` | P5 |

---

## 7. 迁移阶段

### P0: 基础设施搭建
- 初始化 Next.js + shadcn/ui 项目 (`frontend/`)
- 初始化 FastAPI 项目 (`api/`)
- 配置暗黑终端主题 (Tailwind CSS 变量)
- 配置 docker-compose.yml + nginx.conf (含 Basic Auth)
- 配置 CORS、API client
- 创建 `storage/` 目录结构 (uploads/, results/, tmp/, history.db)

### P0.5: API 骨架 + 核心服务
- 实现 `GET /api/health`, `GET /api/version`
- 实现 `storage_service.py` — storage/ 目录管理、路径生成、文件清理
- 实现 `history_service.py` — SQLite 历史记录 CRUD
- 实现任务模型 — `analyze_jobs` 表、`JobStatus` schema、`analyze_service.py`
- 实现 `analyze_worker.py` — BackgroundTasks worker、Semaphore 并发控制
- 实现认证中间件 — Basic Auth / API Token
- 端到端验证: 上传 PDF → 获得 job_id → 轮询状态 → 获取结果
- **此阶段不实现前端页面，仅验证 API 链路**

### P1: Dashboard 首页
- FastAPI: `GET /api/ipo/list`
- Next.js: Dashboard 页面 (IPO 列表 + 筛选 + 排序)
- 组件: IPOTable, FilterBar, DashboardCard

### P2: IPO 详情页 (最大工作量)
- FastAPI: `GET /api/ipo/{stock_code}`
- Next.js: IPO 详情页
- 组件: ScoreCard, ScoreWaterfall, SignalBreakdown, RiskPanel, CornerstoneTable, PeerCompTable, DiagnosisGrid, KPIRow
- 图表: 评分瀑布图、认购趋势图 (Recharts)

### P3: 上传分析 + 重新分析
- FastAPI: `POST /api/analyze/upload`, `POST /api/analyze/reanalyze` (已在 P0.5 实现)
- Next.js: 上传页面、重新分析对话框、任务状态轮询 UI
- 文件上传: react-dropzone

### P4: 历史页 + 博主观点
- FastAPI: `GET /api/history`, `GET /api/blogger/consensus/{stock_code}`
- Next.js: 历史列表页、博主观点组件

### P5: 同行库管理 + 报告下载
- FastAPI: `GET/PUT /api/peer/*`, `GET /api/report/*/pdf`
- Next.js: 同行管理页、PDF 下载按钮

### P6: 下线 Streamlit
- 移除 `ui/` 目录
- 移除 `app.py`, `style.css`
- 移除 `requirements.txt` 中的 streamlit 依赖
- 更新 nginx.conf 移除 /admin 路由
- 更新 README

---

## 8. 技术选型

| 层 | 技术 | 版本 |
|----|------|------|
| 前端框架 | Next.js (App Router) | 15.x |
| UI 组件库 | shadcn/ui | latest |
| CSS | Tailwind CSS | 4.x |
| 图表 | Recharts | 2.x |
| 动效 | motion (framer-motion) | 11.x |
| 后端框架 | FastAPI | 0.115+ |
| ASGI 服务器 | Uvicorn | 0.30+ |
| 数据库 | SQLite (via aiosqlite) | - |
| 反向代理 | Nginx | 1.25+ |
| 容器 | Docker + docker-compose | - |

### 8.1 Next.js 选型理由

选择 Next.js **不是为了 SEO**（IPO 分析工具无需搜索引擎优化），而是基于以下理由：

1. **App Router 页面组织**: 嵌套 layout、loading 状态、error boundary 原生支持，适合多页面投研工具
2. **Layout 复用**: 全局 Sidebar + Header 在 root layout 定义一次，所有页面自动继承
3. **Server Components**: IPO 列表等数据密集页面可在服务端渲染，减少客户端 bundle 和首屏数据请求
4. **未来扩展**: 如果后续需要用户登录/权限控制，Next.js Middleware 原生支持；Vite React 需要自行实现
5. **部署扩展**: Next.js 支持 standalone 输出模式，Docker 部署体积小；未来如需 Vercel 部署也零成本迁移

**为什么暂不选 Vite React**: Vite React 适合纯 SPA，但本项目需要多页面路由、共享 layout、服务端数据预取。Vite React 需要手动配置 react-router、layout 系统、数据预取策略，而 Next.js App Router 开箱即用。如果项目规模缩小为单页工具，可降级到 Vite React。

### 8.2 Tailwind CSS 4.x 兼容性说明

Tailwind CSS 4.x 使用了 CSS 原生特性（如 `@layer`, CSS custom properties, `color-mix()`），浏览器兼容性要求：

| 浏览器 | 最低版本 |
|--------|----------|
| Chrome | 111+ |
| Safari | 16.4+ |
| Edge | 111+ |
| Firefox | 128+ |

私有部署场景下，投研团队通常使用现代浏览器，Tailwind 4.x 兼容性不成问题。

**降级方案**: 如果需要支持旧浏览器（如企业内网 Chrome < 111），降级到 Tailwind CSS 3.4.x，功能基本一致，仅 CSS 变量语法和配置方式略有不同。

---

## 9. 关键决策记录

1. **渐进式迁移**: 逐页迁移，Streamlit 过渡期保留，降低风险
2. **核心逻辑不重写**: ipo_analyzer/ 核心模块尽量零修改；边界层 (report/history/models) 最小适配；改核心必须加 regression test
3. **薄适配层**: `api/services/` 仅做类型转换和接口适配，不重复业务逻辑
4. **异步任务模型**: PDF 分析采用 job_id 模式，避免 HTTP 超时；第一阶段 SQLite + BackgroundTasks，后续可升级 Celery/RQ
5. **私有部署 + 最低权限**: Nginx Basic Auth 或 API Token 保护写入接口
6. **Next.js App Router**: 选择 Next.js 是为了页面组织、layout 复用、Server Components、未来权限扩展，不是为了 SEO
7. **shadcn/ui**: 可完全定制的暗黑终端主题，不引入重度依赖
8. **Nginx 统一入口**: 过渡期同时服务 Next.js、FastAPI、Streamlit
9. **SQLite 唯一事实源**: 历史记录以 SQLite 为唯一事实源，所有写入经过 service 层

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| FastAPI 异步与 ipo_analyzer 同步代码冲突 | 中 | FastAPI 路由使用 `def` 而非 `async def`，自动在线程池执行 |
| PDF 上传大文件超时 | 中 | 异步任务模型：POST 立即返回 job_id，分析在后台执行 |
| Streamlit 与 Next.js 数据不一致 | 中 | SQLite 为唯一事实源；Streamlit 过渡期降级为只读；所有写入经过 service 层 |
| React 前端工作量大 | 高 | P2 详情页分批实现，先核心后细节 |
| 多个分析任务并发导致内存暴涨 | 高 | Semaphore 限制最多 1-2 个并发分析任务，超出排队 |
| 核心模块修改引入回归 | 高 | 改核心模块必须添加 regression test |

---

## 11. 数据一致性设计 (新增)

### 11.1 存储布局

```
storage/
├── uploads/          # 用户上传的 PDF 招股书
│   └── {uuid}.pdf    # UUID 文件名，避免冲突和路径遍历
├── results/          # 分析结果 JSON
│   └── {stock_code}_{timestamp}.json
├── tmp/              # 临时文件 (分析中间产物)
│   └── ...           # TTL 自动清理
└── history.db        # SQLite 数据库 (唯一事实源)
```

### 11.2 SQLite — 唯一事实源

- `history.db` 是历史记录的**唯一事实源**
- 包含表: `analyze_jobs`, `ipo_history`, `blogger_posts` (迁移自 blogger_monitor/db.py)
- 所有写入操作必须经过 `api/services/` 层，不直接操作数据库文件
- Streamlit 过渡期尽量**只读**访问 history.db，不再作为主要写入入口

### 11.3 写入规则

1. **所有写入经过 service 层**: 不允许 router 直接操作文件系统或数据库
2. **上传文件**: `storage_service.py` 管理 UUID 命名、路径生成、文件清理
3. **分析结果**: worker 完成后写入 `storage/results/` + `history.db`
4. **临时文件**: 分析完成后立即清理，不依赖 TTL（TTL 仅作为兜底）
5. **Streamlit 过渡期**: Streamlit 可以读取 history.db 展示数据，但不再写入新记录

---

## 12. 最低权限保护 (新增)

私有部署也需要基本的访问控制，防止未授权用户触发分析或修改数据。

### 12.1 认证方案

| 方案 | 优点 | 缺点 | 推荐场景 |
|------|------|------|----------|
| Nginx Basic Auth | 配置简单，无需代码改动 | 每次请求都传密码，用户体验一般 | 快速上线 |
| API Token (Header) | 灵活，支持多 token | 需要代码实现验证逻辑 | 正式使用 |

**推荐**: 第一阶段用 Nginx Basic Auth 快速上线，后续升级 API Token。

### 12.2 需要保护的接口

| 接口 | 方法 | 保护级别 |
|------|------|----------|
| `/api/analyze/upload` | POST | ✅ 必须认证 |
| `/api/analyze/reanalyze` | POST | ✅ 必须认证 |
| `/api/peer/data/{stock_code}` | PUT | ✅ 必须认证 |
| `/api/blogger/refresh/{stock_code}` | POST | ✅ 必须认证 |
| `/api/history/{stock_code}` | DELETE | ✅ 必须认证 |
| 其他 GET 接口 | GET | - 暂不认证 (内网环境) |

### 12.3 Nginx Basic Auth 配置示例

```nginx
location /api/ {
    # 写入接口需要认证
    if ($request_method !~ ^(GET|HEAD)$) {
        auth_basic "HK IPO Analyzer";
        auth_basic_user_file /etc/nginx/.htpasswd;
    }
    proxy_pass http://fastapi:8000;
}
```

---

## 13. FastAPI 并发限制 (新增)

PDF 分析是 CPU/内存密集型操作（PyPDF2/pymupdf 解析 + LLM API 调用），同时运行多个任务可能导致内存暴涨和 OOM。

### 13.1 并发控制策略

- 使用 `asyncio.Semaphore` 限制同时运行的分析任务数
- **默认上限: 2 个并发分析任务**
- 超出上限的任务进入 `queued` 状态，等待 worker 拾取
- 可通过环境变量 `MAX_CONCURRENT_ANALYSES` 调整

### 13.2 实现方式

```python
# api/services/analyze_service.py
_semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_ANALYSES", "2")))

async def run_analysis(job_id: str, ...):
    async with _semaphore:
        update_job_status(job_id, "running")
        result = analyze_uploaded_pdf(...)  # 同步调用，在线程池执行
        update_job_status(job_id, "success", result)
```

### 13.3 内存估算

| 操作 | 预估内存 |
|------|----------|
| PDF 解析 (200 页招股书) | ~200-400 MB |
| LLM API 调用 (多次) | ~50 MB |
| 评分计算 | ~30 MB |
| **单个分析任务合计** | **~300-500 MB** |
| **2 个并发** | **~600 MB - 1 GB** |

建议部署机器至少 2 GB 可用内存。
