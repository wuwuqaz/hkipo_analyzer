# 港股IPO分析系统 - 前端改进设计

**日期：** 2026-05-24
**类型：** 重构 + 优化
**审核来源：** 前端代码全面审核（2026-05-24）

---

## 一、审核发现摘要

| 方面 | 评价 | 主要发现 |
|------|------|---------|
| 设计系统 | ✅ 优秀 | CSS 变量体系完整，暗色主题视觉统一 |
| 组件拆分 | ✅ 良好 | results/ 目录下各模块单一职责 |
| 无障碍 | ✅ 良好 | ARIA 属性、键盘导航、prefers-reduced-motion |
| 类型安全 | ❌ 不足 | 大量 `Record<string, unknown>`，强类型形同虚设 |
| 代码组织 | ❌ 不足 | page.tsx 704行，内联组件和逻辑过多 |
| 代码重复 | ❌ 不足 | 工具函数5处重复，详情面板2处重复，轮询逻辑2处重复 |
| SSR 利用 | ⚠️ 可改进 | 过多 `"use client"` 标记，未使用 Suspense |
| 前端测试 | ❌ 缺失 | 0个前端测试文件 |
| 表单体验 | ⚠️ 可改进 | 无字段级校验，JSON输入无实时反馈 |
| 暗色适配 | ⚠️ 可改进 | 原生 select 选项白底 |

---

## 二、改进方案：四迭代渐进式重构

### 迭代一：基础夯实（高优先级）

**目标：** 解决架构层面最根本的类型安全和代码重复问题

#### 1.1 定义统一分析结果类型

在 `lib/types.ts` 中新增 `AnalysisResult` 及相关嵌套类型：

```typescript
// 基本面信息
interface CompanyProfile {
  confidence: string;
  business_description?: string;
  founded_year?: number;
  headquarters?: string;
  employee_count?: number;
  products_services?: string[];
}

// 基石分析
interface CornerstoneAnalysis {
  score: number;
  investors: CornerstoneInvestor[];
  lockup_period_months?: number;
  total_commitment_pct?: number;
}

interface CornerstoneInvestor {
  name: string;
  commitment_hkd_million?: number;
  type?: string;
}

// 股票质地
interface StockQuality {
  score: number;
  label: string;
  dimensions: Record<string, { label: string; detail: string }>;
  reasons: string[];
}

// 估值信息
interface ProspectusInfo {
  sector: string;
  offer_price: number;
  lot_size: number;
  market_cap_hkd_million: number;
  apply_end_date?: string;
  company_profile?: CompanyProfile;
  cornerstone_analysis?: CornerstoneAnalysis;
  stock_quality?: StockQuality;
  investment_thesis?: Record<string, unknown>;
}

// 投研结论
interface InvestmentThesis {
  overall_tone: string;
  one_line_conclusion: string;
  conclusion?: string;
  fundamental_diagnosis: unknown[];
  business_model_takeaways: unknown[];
  valuation_takeaways: unknown[];
  catalysts: unknown[];
  invalidation_signals: unknown[];
  missing_angles: unknown[];
  short_seller_case?: Record<string, unknown>;
}

// 核心分析结果
interface AnalysisResult {
  hk_code: string;
  stock_code: string;
  company_name: string;
  score: number;
  trade_score: number;
  strict_ipo_score?: number;
  ipo_trade_score?: number;
  long_term_score: number;
  raw_long_term_score_before_penalty?: number;
  long_term_penalty?: number;
  long_term_penalty_reasons?: string[];
  strict_cap_reasons?: string[];
  valuation_score: number;
  fundamental_score: number;
  theme_score?: number;
  valuation_pressure_label: string;
  market_heat: string;
  over_sub_ratio?: number;
  subscription_recommendation: string;
  ipo_trade_label?: string;
  long_term_label?: string;
  apply_start_date?: string;
  apply_end_date?: string;
  margin_total_hkd_billion?: number;
  margin_total?: number;
  margin_detail?: Record<string, unknown>;
  risk_penalty?: number;
  financial_data_quality_flags?: string[];
  financial_extract_confidence?: string;
  score_breakdown?: Record<string, { score: number; max_score: number; normalized_score?: number; detail: string }>;
  prospectus_info?: ProspectusInfo;
  stock_quality?: StockQuality;
  investment_thesis?: InvestmentThesis;
}
```

#### 1.2 改造所有组件签名

将以下组件的 `Record<string, unknown>` 替换为 `AnalysisResult`：

- `CompanyHeader.tsx`
- `CompanyProfileCard.tsx`
- `CornerstoneCard.tsx` / `CornerstoneDetail.tsx`
- `DimensionGrid.tsx`
- `InvestmentThesisCard.tsx`
- `PostListingCard.tsx`
- `RiskPanel.tsx`
- `ScoreBadge.tsx` / `ScoreBoard.tsx`
- `SignalBreakdown.tsx`
- `StockQualityCard.tsx`
- `ValuationCard.tsx`
- `PeerTable.tsx` / `PeerComparisonFull.tsx`
- `DetailViewExtras.tsx`

#### 1.3 工具函数去重

将以下散布在多个文件中的工具函数统一归入 `lib/utils.ts`：

| 函数 | 散落位置 | 保留行为 |
|------|---------|---------|
| `safeNumber` | page.tsx | 统一版本 |
| `fmtNum` | DetailViewExtras.tsx, PostListingCard.tsx | 合并 |
| `fmtPct` | DetailViewExtras.tsx, PostListingCard.tsx | 合并 |
| `fmtInt` | DetailViewExtras.tsx | 保留 |
| `fmtPrice` / `fmtMillion` | CompanyHeader.tsx | 提取 |
| `formatNumber` / `formatPrice` / `formatLots` | history/page.tsx | 合并至统一版本 |
| `scoreColor` / `scoreTone` | ScoreBoard.tsx, DimensionGrid.tsx | 提取共用 |

#### 1.4 前端测试基础设施

- 安装 `vitest`、`@testing-library/react`、`@testing-library/jest-dom`
- 为核心组件编写 15-20 个测试：
  - `ScoreBoard`：验证评分渲染、颜色映射、惩罚信息展示
  - `DimensionGrid`：验证维度分解展示、归一化计算
  - `ScoreBadge`：验证标签映射
  - `filter` 逻辑：验证 Dashboard 筛选条件

**产出：** 类型安全的组件树、单一来源的工具函数、15-20 个前端测试

---

### 迭代二：架构优化（中优先级）

#### 2.1 Dashboard 页面拆分

将 `src/app/page.tsx`（704行）拆分为：

```
src/
├── app/
│   └── page.tsx                    (~150行，仅组合)
├── components/
│   └── dashboard/
│       ├── StatusBadge.tsx         (从 page.tsx 提取)
│       ├── MetricCard.tsx          (从 page.tsx 提取)
│       ├── FilterCheckbox.tsx      (从 page.tsx 提取)
│       ├── ScorePill.tsx           (从 page.tsx 提取)
│       ├── HeatPill.tsx            (从 page.tsx 提取)
│       ├── DataQualityBadge.tsx    (从 page.tsx 提取)
│       ├── IpoTable.tsx            (表格部分)
│       ├── IpoTableRow.tsx         (单行)
│       └── IpoDetailPanel.tsx      (详情面板，与 history 共享)
├── hooks/
│   ├── useLiveData.ts              (load + refresh + polling)
│   └── useFilters.ts               (筛选状态 + 过滤逻辑)
```

#### 2.2 共享详情面板

抽取 `<IpoDetailPanel>`，Dashboard 的 `selectedIpo` 展开区和 History 的展开行复用同一组件。

#### 2.3 统一轮询 Hook

抽取 `hooks/useJobPolling.ts`：

```typescript
function useJobPolling(
  jobId: string,
  onSuccess: () => void,
  onError: (message: string) => void,
  interval?: number
): { isPolling: boolean; stop: () => void }
```

Dashboard 的 `handleRefresh` 轮询和 Jobs 页的 `setInterval` 轮询统一使用此 hook。

#### 2.4 Server Component 化

审计并移除不必要的 `"use client"`：

| 组件 | 当前 | 改为 | 原因 |
|------|------|------|------|
| ScoreBoard | client | server | 纯展示，无 hooks |
| DimensionGrid | client | server | 纯展示，无 hooks |
| ValuationCard | client | server | 纯展示 |
| StockQualityCard | client | server | 纯展示 |
| RiskPanel | client | server | 纯展示 |
| ScoreBadge | client | server | 纯展示 |
| CompanyHeader | client | server | 纯展示 |
| ResultSection | client | server | 纯展示 |
| PeerTable | client | server | 纯展示 |
| PeerComparisonFull | client | server | 纯展示 |
| CornerstoneDetail | client | server | 纯展示 |
| SignalBreakdown | client | server | 纯展示 |
| DetailViewExtras 组件 | client | server | 纯展示 |
| Navbar | client → 拆分 | 链接渲染 server + 高亮逻辑 client |

#### 2.5 Suspense 流式加载

- Dashboard / History / Jobs 页面使用 `<Suspense fallback={<Loading />}>` 包裹数据区域
- 各页面添加 `loading.tsx` 文件
- 移除手动的 `loading` 状态管理

---

### 迭代三：体验打磨（低优先级）

#### 3.1 表单校验增强

Upload 页面：
- 文件未选择时，file input 添加红色边框 + "请选择招股书 PDF 文件" 内联提示
- 文件类型错误时，file input 添加红色边框 + 即时错误文案
- 不使用通用 ErrorDisplay 展示校验错误

Reanalyze 页面：
- JSON 输入框增加实时语法校验状态指示
- 有效时显示绿色 ✓，无效时显示红色 ✗ + 行号

#### 3.2 Select 暗色主题适配

- 为 `<select>` 添加 `appearance: none` + 背景色深色 + 自定义下拉箭头 SVG
- 下拉选项使用暗色背景

#### 3.3 轻量状态缓存

- 使用 React Context（`CacheContext`）跨页面缓存：
  - live data（Dashboard 页面数据）
  - history records（History 页面数据）
- 缓存在页面切换期间保持，避免重复请求
- 提供 `invalidateCache()` 方法用于手动刷新

---

### 迭代四：可持续优化

#### 4.1 前端 CI 集成

在 `.github/workflows/ci.yml` 中添加：

```yaml
- name: Frontend build
  run: |
    cd frontend
    npm ci
    npm run build
- name: Frontend lint
  run: |
    cd frontend
    npm run lint
- name: Frontend test
  run: |
    cd frontend
    npm test -- --run
```

#### 4.2 组件文档（可选）

- 为 `components/results/` 下组件搭建 Storybook
- 方便独立开发、演示和回归测试

---

## 三、执行顺序

```
迭代一 (3-4天) → 迭代二 (2-3天) → 迭代三 (1-2天) → 迭代四 (1天)
```

每轮迭代独立可交付，不阻塞其他工作。

---

## 四、风险与约束

- **API 兼容性：** 类型定义需与后端返回结构对齐，建议先写集成测试验证类型与 API 响应一致
- **SSR 改造：** 去掉 `"use client"` 后需确保无隐式 DOM/BOM API 调用
- **工具函数合并：** 注意各版本的行为差异（如数值精度、空值处理），以最包容的版本为准
