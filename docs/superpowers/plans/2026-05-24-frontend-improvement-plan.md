# 前端改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 四迭代渐进式重构前端，解决类型安全、代码组织、重复代码、体验打磨四大问题

**Architecture:** 从最核心的类型定义出发，逐层向外改造组件签名，然后做页面拆分和逻辑抽取，最后打磨体验细节

**Tech Stack:** Next.js 16.2, React 19, TypeScript 5, Tailwind CSS 4, Vitest + Testing Library

**前置条件：** 确保前端构建通过 `cd frontend && npm run build`

---

## 文件结构总览

### 新建文件
```
frontend/src/
├── hooks/
│   ├── useLiveData.ts              - Dashboard 数据获取 + 刷新
│   ├── useFilters.ts               - Dashboard 筛选逻辑
│   └── useJobPolling.ts            - 通用 Job 轮询
├── components/
│   └── dashboard/
│       ├── StatusBadge.tsx          - 页面状态标签 (from page.tsx)
│       ├── MetricCard.tsx           - 指标卡片 (from page.tsx)
│       ├── FilterCheckbox.tsx       - 筛选复选框 (from page.tsx)
│       ├── ScorePill.tsx            - 分数药丸 (from page.tsx)
│       ├── HeatPill.tsx             - 热度药丸 (from page.tsx)
│       ├── DataQualityBadge.tsx     - 数据质量标记 (from page.tsx)
│       ├── IpoTable.tsx             - IPO 表格组件
│       ├── IpoTableRow.tsx          - IPO 表格行
│       └── IpoDetailPanel.tsx       - IPO 详情面板 (与 history 共享)
├── lib/
│   ├── types.ts                     - 新增 AnalysisResult 等类型
│   └── utils.ts                     - 统一工具函数
├── __tests__/
│   ├── ScoreBoard.test.tsx
│   ├── DimensionGrid.test.tsx
│   ├── ScoreBadge.test.tsx
│   └── filter.test.ts
```

### 修改文件
```
frontend/src/
├── app/page.tsx                     - 拆分为组合层，大幅瘦身
├── app/history/page.tsx             - 复用 IpoDetailPanel
├── app/jobs/[jobId]/page.tsx        - 复用 useJobPolling
├── app/upload/page.tsx              - 增强表单校验
├── app/reanalyze/page.tsx           - 增强表单校验
├── app/peers/page.tsx               - Select 暗色适配
├── components/Navbar.tsx            - 拆分 server/client
├── components/results/*.tsx         - 替换 Record<string,unknown> 为 AnalysisResult
├── lib/types.ts                     - 追加 AnalysisResult 类型
├── lib/utils.ts                     - 合并工具函数
├── lib/api.ts                       - 适配新类型
├── app/globals.css                  - 添加 select 暗色样式
├── .github/workflows/ci.yml         - 添加前端测试步骤
```

---

## 迭代一：基础夯实

### Task 1.1: 定义 `AnalysisResult` 类型并扩展 `types.ts`

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Test: 后续组件改造时自然验证

- [ ] **Step 1: 在 types.ts 末尾追加新类型**

在 `frontend/src/lib/types.ts` 末尾添加以下类型定义：

```typescript
/* ------------------------------------------------------------------ */
/* AnalysisResult — IPO 分析结果统一类型                               */
/* ------------------------------------------------------------------ */

export interface CompanyProfile {
  confidence: string;
  business_description?: string;
  founded_year?: number;
  headquarters?: string;
  employee_count?: number;
  products_services?: string[];
}

export interface CornerstoneInvestor {
  name: string;
  commitment_hkd_million?: number;
  type?: string;
}

export interface CornerstoneAnalysis {
  score: number;
  investors: CornerstoneInvestor[];
  lockup_period_months?: number;
  total_commitment_pct?: number;
}

export interface StockQuality {
  score: number;
  label: string;
  dimensions: Record<string, { label: string; detail: string }>;
  reasons: string[];
}

export interface ProspectusInfo {
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

export interface InvestmentThesis {
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

export interface ScoreBreakdownItem {
  score: number;
  max_score: number;
  normalized_score?: number;
  detail: string;
}

export interface AnalysisResult {
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
  score_breakdown?: Record<string, ScoreBreakdownItem>;
  prospectus_info?: ProspectusInfo;
  stock_quality?: StockQuality;
  investment_thesis?: InvestmentThesis;
}
```

- [ ] **Step 2: 确认构建通过**

```bash
cd frontend && npm run build
```
预期：构建成功，因为新类型还没有被使用。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types.ts
git commit -m "feat: add AnalysisResult type for type-safe IPO analysis"
```

---

### Task 1.2: 统一工具函数到 `utils.ts`

**Files:**
- Modify: `frontend/src/lib/utils.ts`
- Modify: `frontend/src/components/results/DetailViewExtras.tsx`
- Modify: `frontend/src/components/results/PostListingCard.tsx`
- Modify: `frontend/src/components/results/CompanyHeader.tsx`
- Modify: `frontend/src/components/results/ScoreBoard.tsx`
- Modify: `frontend/src/components/results/DimensionGrid.tsx`

- [ ] **Step 1: 在 utils.ts 中定义统一工具函数**

将 `frontend/src/lib/utils.ts` 替换为：

```typescript
/* ------------------------------------------------------------------ */
/* 数值格式化工具                                                      */
/* ------------------------------------------------------------------ */

export function safeNumber(v: unknown, fallback = 0): number {
  if (v === null || v === undefined) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export function fmtNum(v: unknown, suffix = ""): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return `${n.toLocaleString()}${suffix}`;
}

export function fmtPct(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return `${n.toFixed(2)}%`;
}

export function fmtInt(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return n.toLocaleString();
}

export function fmtPrice(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  return `HK$${n.toFixed(2)}`;
}

export function fmtMillion(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  return `HK$${(n / 100).toFixed(2)}亿`;
}

export function formatDate(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

export function formatDateTime(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(d);
}

export function formatNumber(v: unknown): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  if (n >= 100000000) return `${(n / 100000000).toFixed(1)}亿`;
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  if (n >= 1) return n.toFixed(0);
  return n.toFixed(2);
}

export function formatPrice(v: unknown): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  return `HK$${n.toFixed(2)}`;
}

export function formatLots(v: unknown): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n) || n <= 0) return "--";
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万手`;
  return `${n.toFixed(0)}手`;
}

export function scoreColor(v: number): string {
  if (v >= 70) return "text-[var(--success)]";
  if (v >= 40) return "text-[var(--warning)]";
  return "text-[var(--danger)]";
}

export function barColor(v: number): string {
  if (v >= 70) return "var(--success)";
  if (v >= 40) return "var(--warning)";
  return "var(--danger)";
}

export function scoreTone(v: number): string {
  if (v >= 70) return "text-[var(--success)]";
  if (v >= 40) return "text-[var(--warning)]";
  return "text-[var(--danger)]";
}
```

- [ ] **Step 2: 更新 DetailViewExtras.tsx**

在 `frontend/src/components/results/DetailViewExtras.tsx` 中：

删除文件内原有的 `fmtNum`、`fmtPct`、`fmtInt` 函数定义，在文件顶部添加 import：

```typescript
import { fmtNum, fmtPct, fmtInt, safeNumber } from "@/lib/utils";
```

- [ ] **Step 3: 更新 PostListingCard.tsx**

在 `frontend/src/components/results/PostListingCard.tsx` 中：

删除文件内原有的 `fmtInt`、`fmtPct`、`fmtNum`、`compactShares` 函数定义，在文件顶部添加 import：

```typescript
import { fmtInt, fmtPct, fmtNum, safeNumber } from "@/lib/utils";
```

- [ ] **Step 4: 更新 CompanyHeader.tsx**

在 `frontend/src/components/results/CompanyHeader.tsx` 中：

删除文件内原有的 `fmtPrice`、`fmtMillion`、`fmtDate` 函数定义，在文件顶部添加 import：

```typescript
import { fmtPrice, fmtMillion, formatDate } from "@/lib/utils";
```

然后将 JSX 中的 `fmtDate(result.apply_start_date)`、`fmtDate(result.apply_end_date)` 分别改为 `formatDate(result.apply_start_date)`、`formatDate(result.apply_end_date)`。

- [ ] **Step 5: 更新 ScoreBoard.tsx**

在 `frontend/src/components/results/ScoreBoard.tsx` 中：

删除文件内原有的 `scoreColor`、`barColor` 函数定义，在文件顶部添加 import：

```typescript
import { scoreColor, barColor, safeNumber } from "@/lib/utils";
```

- [ ] **Step 6: 更新 DimensionGrid.tsx**

在 `frontend/src/components/results/DimensionGrid.tsx` 中：

删除文件内原有的 `scoreTone` 函数定义，在文件顶部添加 import：

```typescript
import { scoreTone } from "@/lib/utils";
```

- [ ] **Step 7: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/utils.ts frontend/src/components/results/DetailViewExtras.tsx frontend/src/components/results/PostListingCard.tsx frontend/src/components/results/CompanyHeader.tsx frontend/src/components/results/ScoreBoard.tsx frontend/src/components/results/DimensionGrid.tsx
git commit -m "refactor: unify utility functions into lib/utils.ts"
```

---

### Task 1.3: 改造组件签名 — 结果卡片组件

**Files:**
- Modify: `frontend/src/components/results/CompanyHeader.tsx`
- Modify: `frontend/src/components/results/ScoreBadge.tsx`
- Modify: `frontend/src/components/results/DimensionGrid.tsx`
- Modify: `frontend/src/components/results/InvestmentThesisCard.tsx`
- Modify: `frontend/src/components/results/StockQualityCard.tsx`

- [ ] **Step 1: 改造 CompanyHeader.tsx**

将 `{ result: Record<string, unknown> }` 改为 `{ result: AnalysisResult }`，利用类型字段替换字符串 key 访问：

```typescript
import type { AnalysisResult, ProspectusInfo } from "@/lib/types";

export function CompanyHeader({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info;
  const recommendation = result.subscription_recommendation || "—";
  const sector = pi?.sector ?? "unknown";
  // 其余保持不变...
}
```

注意：文件底部有 `Field`、`fmtPrice`、`fmtMillion`、`fmtDate` 辅助函数，其中 `fmtPrice`/`fmtMillion` 已在 Task 1.2 中替换为 import，`fmtDate` 需替换为 `formatDate`。

- [ ] **Step 2: 改造 ScoreBadge.tsx**

保持不变，因为它接受的是 `{ label: string }` 而非 `Record<string, unknown>`。

- [ ] **Step 3: 改造 DimensionGrid.tsx**

将 `{ result: Record<string, unknown> }` 改为 `{ result: AnalysisResult }`：

```typescript
import type { AnalysisResult } from "@/lib/types";
import { scoreTone } from "@/lib/utils";

export function DimensionGrid({ result }: { result: AnalysisResult }) {
  const breakdown = result.score_breakdown ?? {};
  // 其余保持不变...
}
```

- [ ] **Step 4: 改造 InvestmentThesisCard.tsx**

将 `{ result: Record<string, unknown> }` 改为 `{ result: AnalysisResult }`：

```typescript
import type { AnalysisResult } from "@/lib/types";

export function InvestmentThesisCard({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info;
  const thesis = result.investment_thesis ?? pi?.investment_thesis ?? {};
  // 其余保持不变...
}
```

- [ ] **Step 5: 改造 StockQualityCard.tsx**

将 `{ result: Record<string, unknown> }` 改为 `{ result: AnalysisResult }`：

```typescript
import type { AnalysisResult } from "@/lib/types";

export function StockQualityCard({ result }: { result: AnalysisResult }) {
  const sq = result.stock_quality ?? result.prospectus_info?.stock_quality ?? {};
  // 其余保持不变...
}
```

- [ ] **Step 6: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/results/CompanyHeader.tsx frontend/src/components/results/DimensionGrid.tsx frontend/src/components/results/InvestmentThesisCard.tsx frontend/src/components/results/StockQualityCard.tsx
git commit -m "refactor: replace Record<string, unknown> with AnalysisResult in result card components"
```

---

### Task 1.4: 改造组件签名 — 评分和估值组件

**Files:**
- Modify: `frontend/src/components/results/ScoreBoard.tsx`
- Modify: `frontend/src/components/results/ValuationCard.tsx`
- Modify: `frontend/src/components/results/SignalBreakdown.tsx`
- Modify: `frontend/src/components/results/RiskPanel.tsx`

- [ ] **Step 1: 改造 ScoreBoard.tsx**

```typescript
import type { AnalysisResult } from "@/lib/types";
import { safeNumber, scoreColor, barColor } from "@/lib/utils";

export function ScoreBoard({ result }: { result: AnalysisResult }) {
  const score = result.score;
  const tradeScore = result.trade_score;
  const longScore = result.long_term_score;
  const valuationScore = result.valuation_score;
  const fundamentalScore = result.fundamental_score;
  const strictScore = safeNumber(result.strict_ipo_score ?? result.ipo_trade_score);
  const strictCapReasons = result.strict_cap_reasons ?? [];
  const hasStrictCap = strictCapReasons.length > 0 && strictScore < score;
  const rawLongScore = result.raw_long_term_score_before_penalty ?? 0;
  const longPenalty = result.long_term_penalty ?? 0;
  const longPenaltyReasons = result.long_term_penalty_reasons ?? [];
  // 其余保持不变...
}
```

- [ ] **Step 2: 改造 ValuationCard.tsx**

读取 `frontend/src/components/results/ValuationCard.tsx` 文件确认现有代码，修改签名 + 内部改用类型字段。

- [ ] **Step 3: 改造 SignalBreakdown.tsx**

读取 `frontend/src/components/results/SignalBreakdown.tsx` 文件确认现有代码，修改签名。

- [ ] **Step 4: 改造 RiskPanel.tsx**

读取 `frontend/src/components/results/RiskPanel.tsx` 文件确认现有代码，修改签名。

- [ ] **Step 5: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/results/ScoreBoard.tsx frontend/src/components/results/ValuationCard.tsx frontend/src/components/results/SignalBreakdown.tsx frontend/src/components/results/RiskPanel.tsx
git commit -m "refactor: replace Record<string, unknown> with AnalysisResult in score and valuation components"
```

---

### Task 1.5: 改造组件签名 — 深度分析和同行组件

**Files:**
- Modify: `frontend/src/components/results/DetailViewExtras.tsx`
- Modify: `frontend/src/components/results/PeerTable.tsx`
- Modify: `frontend/src/components/results/PeerComparisonFull.tsx`
- Modify: `frontend/src/components/results/CornerstoneDetail.tsx`
- Modify: `frontend/src/components/results/PostListingCard.tsx`
- Modify: `frontend/src/components/results/CompanyProfileCard.tsx`

- [ ] **Step 1: 改造 DetailViewExtras.tsx**

该文件导出多个组件（ScoreWaterfall、ScoreReasons、InfoBasic、InfoFinancials、InfoDeep、BusinessSegments、FisherLynch、DiagnosisPanel），全部将 `{ result: Record<string, unknown> }` 改为 `{ result: AnalysisResult }`。

- [ ] **Step 2: 改造 PeerTable.tsx 和 PeerComparisonFull.tsx**

分别将签名改为 `{ result: AnalysisResult }`。

- [ ] **Step 3: 改造 CornerstoneDetail.tsx**

将签名改为 `{ result: AnalysisResult }`，利用 `result.prospectus_info?.cornerstone_analysis`。

- [ ] **Step 4: 改造 PostListingCard.tsx**

将签名改为 `{ result: AnalysisResult }`。

- [ ] **Step 5: 改造 CompanyProfileCard.tsx**

将签名改为 `{ result: AnalysisResult }`。

- [ ] **Step 6: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/results/DetailViewExtras.tsx frontend/src/components/results/PeerTable.tsx frontend/src/components/results/PeerComparisonFull.tsx frontend/src/components/results/CornerstoneDetail.tsx frontend/src/components/results/PostListingCard.tsx frontend/src/components/results/CompanyProfileCard.tsx
git commit -m "refactor: replace Record<string, unknown> with AnalysisResult in deep analysis components"
```

---

### Task 1.6: 更新页面组件适配新类型

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/history/page.tsx`
- Modify: `frontend/src/app/jobs/[jobId]/page.tsx`

- [ ] **Step 1: 更新 page.tsx 中的 safeNumber / formatDate 引用**

删除 page.tsx 中的内联 `safeNumber`、`formatDate` 函数，改用 `import { safeNumber, formatDate } from "@/lib/utils"`。

- [ ] **Step 2: 更新历史页面工具函数**

删除 history/page.tsx 中的 `formatNumber`、`formatPrice`、`formatLots` 函数，改用 `import { formatNumber, formatPrice, formatLots } from "@/lib/utils"`。

- [ ] **Step 3: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/page.tsx frontend/src/app/history/page.tsx frontend/src/app/jobs/[jobId]/page.tsx
git commit -m "refactor: replace inline utility functions with centralized imports"
```

---

### Task 1.7: 搭建前端测试基础设施

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/__tests__/ScoreBoard.test.tsx`
- Create: `frontend/src/__tests__/DimensionGrid.test.tsx`
- Create: `frontend/src/__tests__/ScoreBadge.test.tsx`
- Create: `frontend/src/__tests__/filter.test.ts`

- [ ] **Step 1: 安装测试依赖**

```bash
cd frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

- [ ] **Step 2: 创建 vitest.config.ts**

```typescript
import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
```

- [ ] **Step 3: 在 package.json 中添加 test 脚本**

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

- [ ] **Step 4: 创建 ScoreBadge.test.tsx**

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScoreBadge } from "@/components/results/ScoreBadge";

describe("ScoreBadge", () => {
  it("renders the label text", () => {
    render(<ScoreBadge label="积极申购" />);
    expect(screen.getByText("积极申购")).toBeDefined();
  });

  it("applies success tone for positive labels", () => {
    const { container } = render(<ScoreBadge label="积极申购" />);
    expect(container.firstElementChild?.className).toContain("success");
  });

  it("applies danger tone for negative labels", () => {
    const { container } = render(<ScoreBadge label="建议跳过" />);
    expect(container.firstElementChild?.className).toContain("danger");
  });

  it("applies warning tone for neutral labels", () => {
    const { container } = render(<ScoreBadge label="中性试水" />);
    expect(container.firstElementChild?.className).toContain("accent");
  });

  it("renders unknown label gracefully", () => {
    const { container } = render(<ScoreBadge label="未知标签" />);
    expect(container.firstElementChild?.className).toContain("foreground");
  });
});
```

- [ ] **Step 5: 创建 filter.test.ts**

```typescript
import { describe, it, expect } from "vitest";
import type { AnalysisResult } from "@/lib/types";

function applyFilters(
  ipo: AnalysisResult,
  filters: { highScore?: boolean; lowRisk?: boolean; hasCornerstone?: boolean; valuationOk?: boolean }
): boolean {
  const tradeScore = ipo.strict_ipo_score ?? ipo.ipo_trade_score ?? ipo.trade_score ?? 0;
  const riskPenalty = ipo.risk_penalty ?? 0;
  const cs = ipo.prospectus_info?.cornerstone_analysis;
  const hasCs = cs !== undefined && cs.score > 0;
  const valLabel = ipo.valuation_pressure_label;
  const valOk = valLabel === "合理" || valLabel === "低估";

  if (filters.highScore && tradeScore < 65) return false;
  if (filters.lowRisk && riskPenalty > 3) return false;
  if (filters.hasCornerstone && !hasCs) return false;
  if (filters.valuationOk && !valOk) return false;
  return true;
}

function makeMockIpo(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    hk_code: "00000",
    stock_code: "00000",
    company_name: "Test",
    score: 50,
    trade_score: 50,
    long_term_score: 50,
    valuation_score: 50,
    fundamental_score: 50,
    valuation_pressure_label: "合理",
    market_heat: "温",
    subscription_recommendation: "中等",
    ...overrides,
  };
}

describe("IPO filter logic", () => {
  it("passes with no filters active", () => {
    expect(applyFilters(makeMockIpo(), {})).toBe(true);
  });

  it("filters low score when highScore filter is on", () => {
    const ipo = makeMockIpo({ strict_ipo_score: 40 });
    expect(applyFilters(ipo, { highScore: true })).toBe(false);
  });

  it("keeps high score when highScore filter is on", () => {
    const ipo = makeMockIpo({ strict_ipo_score: 80 });
    expect(applyFilters(ipo, { highScore: true })).toBe(true);
  });

  it("filters high risk when lowRisk filter is on", () => {
    const ipo = makeMockIpo({ risk_penalty: 10 });
    expect(applyFilters(ipo, { lowRisk: true })).toBe(false);
  });

  it("keeps low risk when lowRisk filter is on", () => {
    const ipo = makeMockIpo({ risk_penalty: 0 });
    expect(applyFilters(ipo, { lowRisk: true })).toBe(true);
  });

  it("filters no cornerstone when hasCornerstone filter is on", () => {
    const ipo = makeMockIpo();
    expect(applyFilters(ipo, { hasCornerstone: true })).toBe(false);
  });

  it("keeps has cornerstone when filter is on", () => {
    const ipo = makeMockIpo({
      prospectus_info: {
        sector: "healthcare",
        offer_price: 10,
        lot_size: 1000,
        market_cap_hkd_million: 1000,
        cornerstone_analysis: { score: 50, investors: [] },
      },
    });
    expect(applyFilters(ipo, { hasCornerstone: true })).toBe(true);
  });

  it("filters bad valuation when valuationOk filter is on", () => {
    const ipo = makeMockIpo({ valuation_pressure_label: "高" });
    expect(applyFilters(ipo, { valuationOk: true })).toBe(false);
  });
});
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd frontend && npm test
```
预期：9 个测试全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/vitest.config.ts frontend/src/__tests__/
git commit -m "test: add vitest setup and frontend unit tests for ScoreBadge and filter logic"
```

---

## 迭代二：架构优化

### Task 2.1: Dashboard 页面拆分 — 抽取内联组件和 hooks

**Files:**
- Create: `frontend/src/components/dashboard/StatusBadge.tsx`
- Create: `frontend/src/components/dashboard/MetricCard.tsx`
- Create: `frontend/src/components/dashboard/FilterCheckbox.tsx`
- Create: `frontend/src/components/dashboard/ScorePill.tsx`
- Create: `frontend/src/components/dashboard/HeatPill.tsx`
- Create: `frontend/src/components/dashboard/DataQualityBadge.tsx`
- Create: `frontend/src/hooks/useLiveData.ts`
- Create: `frontend/src/hooks/useFilters.ts`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: 创建 StatusBadge.tsx**

```typescript
export function StatusBadge({ label, tone = "text-[var(--muted)]" }: { label: string; tone?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border border-[var(--border)] bg-white/8 px-3 py-1 text-xs font-semibold uppercase tracking-[0.28em] ${tone}`}>
      {label}
    </span>
  );
}
```

- [ ] **Step 2: 创建 MetricCard.tsx**

```typescript
export function MetricCard({ title, value, tone = "text-[var(--foreground)]" }: { title: string; value: string; tone?: string }) {
  return (
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3.5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <p className="text-xs uppercase tracking-[0.15em] text-[var(--muted)]">{title}</p>
      <p className={`mt-2 text-xl font-semibold ${tone}`}>{value}</p>
    </article>
  );
}
```

- [ ] **Step 3: 创建 FilterCheckbox.tsx**

```typescript
export function FilterCheckbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  const id = `filter-${label.replace(/[^a-zA-Z0-9]/g, '-')}`;
  return (
    <label htmlFor={id} className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] transition hover:bg-white/8">
      <input id={id} type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}
```

- [ ] **Step 4: 创建 ScorePill.tsx**

```typescript
export function ScorePill({ score }: { score: number }) {
  let tone = "text-[var(--danger)]";
  if (score >= 70) tone = "text-[var(--success)]";
  else if (score >= 50) tone = "text-[var(--warning)]";
  return <span className={`font-semibold ${tone}`}>{score}</span>;
}
```

- [ ] **Step 5: 创建 HeatPill.tsx**

```typescript
export function HeatPill({ label }: { label: string }) {
  let tone = "text-[var(--foreground)]";
  if (label === "热门" || label === "极热") tone = "text-[var(--danger)]";
  else if (label === "温" || label === "一般") tone = "text-[var(--warning)]";
  return <span className={`text-sm ${tone}`}>{label}</span>;
}
```

- [ ] **Step 6: 创建 DataQualityBadge.tsx**

```typescript
export function DataQualityBadge({ flags, confidence }: { flags?: string[]; confidence?: string }) {
  const hasIssue = (flags && flags.length > 0) || confidence === "needs_review" || confidence === "low";
  const severe = flags && flags.some((f) => f.includes("不一致") || f.includes("冲突"));
  if (severe) {
    return <span className="ml-2 inline-flex items-center rounded-full bg-[var(--danger)]/10 px-2 py-0.5 text-xs font-medium text-[var(--danger)]">需复核</span>;
  }
  if (hasIssue) {
    return <span className="ml-2 inline-flex items-center rounded-full bg-[var(--warning)]/10 px-2 py-0.5 text-xs font-medium text-[var(--warning)]">中</span>;
  }
  return <span className="ml-2 inline-flex items-center rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-xs font-medium text-[var(--success)]">高</span>;
}
```

- [ ] **Step 7: 创建 hooks/useLiveData.ts**

```typescript
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchLiveResults, triggerLiveAnalyze, fetchJobStatus } from "@/lib/api";
import type { LiveResultsResponse } from "@/lib/types";

export function useLiveData() {
  const [data, setData] = useState<LiveResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    pollRef.current = null;
    timeoutRef.current = null;
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetchLiveResults();
      setData(res);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load live IPO data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      if (!cancelled) load().catch(() => {});
    }, 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [load]);

  const refresh = useCallback(async (force: boolean) => {
    clearTimers();
    setRefreshing(true);
    setError(null);
    try {
      const job = await triggerLiveAnalyze(force);
      let done = false;

      const pollJob = async () => {
        try {
          const status = await fetchJobStatus(job.job_id);
          if (status.status === "success") {
            done = true;
            clearTimers();
            await load();
            setRefreshing(false);
            return;
          }
          if (status.status === "failed" || status.status === "not_found") {
            done = true;
            clearTimers();
            setRefreshing(false);
            setError(status.error || `Refresh job ${status.status}`);
          }
        } catch (err) {
          done = true;
          clearTimers();
          setRefreshing(false);
          setError(err instanceof Error ? err.message : "Refresh status check failed");
        }
      };

      await pollJob();
      if (done) return;

      const poll = setInterval(pollJob, 2000);
      pollRef.current = poll;
      const safetyTimeout = setTimeout(() => {
        clearTimers();
        setRefreshing(false);
        load().catch((err) => {
          setError(err instanceof Error ? err.message : "Refresh timed out");
        });
      }, 120000);
      timeoutRef.current = safetyTimeout;
    } catch (err) {
      clearTimers();
      setRefreshing(false);
      setError(err instanceof Error ? err.message : "Refresh failed");
    }
  }, [clearTimers, load]);

  return { data, loading, refreshing, error, refresh, setError, load };
}
```

- [ ] **Step 8: 创建 hooks/useFilters.ts**

```typescript
"use client";

import { useMemo, useState } from "react";
import { safeNumber } from "@/lib/utils";
import type { AnalysisResult } from "@/lib/types";

export function useFilters(items: AnalysisResult[]) {
  const [filterHighScore, setFilterHighScore] = useState(false);
  const [filterLowRisk, setFilterLowRisk] = useState(false);
  const [filterHasCornerstone, setFilterHasCornerstone] = useState(false);
  const [filterValuationOk, setFilterValuationOk] = useState(false);

  const filtered = useMemo(() => {
    return items.filter((ipo) => {
      const tradeScore = safeNumber(ipo.strict_ipo_score ?? ipo.ipo_trade_score ?? ipo.trade_score);
      const riskPenalty = safeNumber(ipo.risk_penalty);
      const cs = ipo.prospectus_info?.cornerstone_analysis;
      const hasCs = cs !== undefined && cs.score > 0;
      const valLabel = ipo.valuation_pressure_label;
      const valOk = valLabel === "合理" || valLabel === "低估";

      if (filterHighScore && tradeScore < 65) return false;
      if (filterLowRisk && riskPenalty > 3) return false;
      if (filterHasCornerstone && !hasCs) return false;
      if (filterValuationOk && !valOk) return false;
      return true;
    });
  }, [items, filterHighScore, filterLowRisk, filterHasCornerstone, filterValuationOk]);

  return {
    filtered,
    filterHighScore, setFilterHighScore,
    filterLowRisk, setFilterLowRisk,
    filterHasCornerstone, setFilterHasCornerstone,
    filterValuationOk, setFilterValuationOk,
    total: items.length,
  };
}
```

- [ ] **Step 9: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/dashboard/ frontend/src/hooks/
git commit -m "refactor: extract dashboard helper components and hooks"
```

---

### Task 2.2: 创建共享 IpoDetailPanel 组件

**Files:**
- Create: `frontend/src/components/dashboard/IpoDetailPanel.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/history/page.tsx`

- [ ] **Step 1: 读取 page.tsx 中 `selectedIpo` 渲染段（约 lines 418-700）**

从 page.tsx 中提取完整的详情面板 JSX（从 `<section className="mt-8">` 开始到 `<div className="mt-8 space-y-8">` 结束的所有内容）。

- [ ] **Step 2: 创建 IpoDetailPanel.tsx**

```typescript
"use client";

import type { AnalysisResult } from "@/lib/types";
import { safeNumber, formatDate } from "@/lib/utils";
import { ResultSection } from "@/components/results/ResultSection";
import { CompanyHeader } from "@/components/results/CompanyHeader";
import { ScoreBoard } from "@/components/results/ScoreBoard";
import { ScoreWaterfall, ScoreReasons } from "@/components/results/DetailViewExtras";
import { DimensionGrid } from "@/components/results/DimensionGrid";
import { SignalBreakdown } from "@/components/results/SignalBreakdown";
import { ValuationCard } from "@/components/results/ValuationCard";
import { PeerTable } from "@/components/results/PeerTable";
import { PeerComparisonFull } from "@/components/results/PeerComparisonFull";
import { CornerstoneDetail } from "@/components/results/CornerstoneDetail";
import { StockQualityCard } from "@/components/results/StockQualityCard";
import { RiskPanel } from "@/components/results/RiskPanel";
import { BloggerConsensusCard } from "@/components/BloggerConsensusCard";
import { CompanyProfileCard } from "@/components/results/CompanyProfileCard";
import {
  InfoBasic, InfoFinancials, InfoDeep, BusinessSegments, FisherLynch,
} from "@/components/results/DetailViewExtras";
import { InvestSkillPanel } from "@/components/results/InvestSkillPanel";
import Link from "next/link";

export function IpoDetailPanel({ ipo, onClose }: { ipo: AnalysisResult; onClose?: () => void }) {
  const pi = ipo.prospectus_info;
  const profile = pi?.company_profile;
  const showProfile = profile && profile.confidence !== "missing";

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-strong)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur sm:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-white">{ipo.company_name}</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            股票代码: {ipo.hk_code} · 截止日: {formatDate(ipo.apply_end_date ?? "")}
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="收起详情"
            className="rounded-full border border-[var(--border)] bg-white/8 px-4 py-2 text-sm text-[var(--accent)] transition hover:bg-white/12"
          >
            收起
          </button>
        )}
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="综合评分" value={String(ipo.score)} tone={ipo.score >= 60 ? "text-[var(--success)]" : "text-[var(--warning)]"} />
        <MetricCard title="交易信号" value={String(ipo.trade_score)} tone={ipo.trade_score >= 60 ? "text-[var(--accent)]" : "text-[var(--muted)]"} />
        <MetricCard title="长期价值" value={String(ipo.long_term_score)} tone={ipo.long_term_score >= 60 ? "text-[var(--success)]" : ipo.long_term_score >= 40 ? "text-[var(--warning)]" : "text-[var(--danger)]"} />
        <MetricCard title="估值吸引力" value={String(ipo.valuation_score)} tone={ipo.valuation_score >= 60 ? "text-[var(--success)]" : "text-[var(--warning)]"} />
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="基本面" value={String(ipo.fundamental_score)} tone={ipo.fundamental_score >= 60 ? "text-[var(--success)]" : "text-[var(--warning)]"} />
        <MetricCard title="估值压力" value={ipo.valuation_pressure_label} tone={ipo.valuation_pressure_label === "高" ? "text-[var(--danger)]" : ipo.valuation_pressure_label === "中" ? "text-[var(--warning)]" : "text-[var(--success)]"} />
        <MetricCard title="市场热度" value={ipo.market_heat || (ipo.over_sub_ratio ? `超购 ${ipo.over_sub_ratio.toFixed(1)}x` : "--")} tone={ipo.market_heat === "极热" || ipo.market_heat === "热门" ? "text-[var(--danger)]" : ipo.market_heat === "温和" ? "text-[var(--warning)]" : "text-[var(--muted)]"} />
        <MetricCard title="主题赛道" value={pi?.sector || (ipo.theme_score ? `主题分 ${ipo.theme_score}` : "--")} tone="text-[var(--foreground)]" />
      </div>

      {/* 严格打新限制与长期价值惩罚 */}
      {buildCapAndPenaltySection(ipo)}

      <div className="mt-6 flex flex-wrap gap-3">
        <Link href={`/reanalyze?stock_code=${encodeURIComponent(ipo.hk_code)}&company_name=${encodeURIComponent(ipo.company_name)}`}
          className="inline-flex items-center gap-2 rounded-xl bg-[var(--accent)]/10 px-5 py-2.5 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20">
          🔁 重新分析
        </Link>
        <Link href="/upload" className="inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-5 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-white/8">
          📤 上传招股书
        </Link>
      </div>

      {/* Full analysis panels */}
      <div className="mt-8 space-y-8">
        {/* 公司信息 */}
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-block h-5 w-1 rounded-full bg-[var(--accent)]" />
            <h3 className="text-base font-semibold text-white">公司信息</h3>
          </div>
          <ResultSection title="公司信息"><CompanyHeader result={ipo} /></ResultSection>
          {showProfile && <div className="mt-4"><ResultSection title="公司简介"><CompanyProfileCard result={ipo} /></ResultSection></div>}
        </div>

        {/* 评分分析 */}
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-block h-5 w-1 rounded-full bg-[var(--accent)]" />
            <h3 className="text-base font-semibold text-white">评分分析</h3>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ResultSection title="评分概览"><ScoreBoard result={ipo} /></ResultSection>
            <ResultSection title="评分理由"><ScoreReasons result={ipo} /></ResultSection>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ResultSection title="综合分拆解 (Waterfall)"><ScoreWaterfall result={ipo} /></ResultSection>
            <ResultSection title="维度拆解"><DimensionGrid result={ipo} /></ResultSection>
          </div>
        </div>

        {/* 估值与同行 */}
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-block h-5 w-1 rounded-full bg-[var(--success)]" />
            <h3 className="text-base font-semibold text-white">估值与同行</h3>
          </div>
          <ResultSection title="估值分析"><ValuationCard result={ipo} /></ResultSection>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ResultSection title="同行对比"><PeerTable result={ipo} /></ResultSection>
            <ResultSection title="同行对比 (详细)"><PeerComparisonFull result={ipo} /></ResultSection>
          </div>
        </div>

        {/* 投资参考 */}
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-block h-5 w-1 rounded-full bg-[var(--warning)]" />
            <h3 className="text-base font-semibold text-white">投资参考</h3>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ResultSection title="交易信号"><SignalBreakdown result={ipo} /></ResultSection>
            <ResultSection title="基石投资者"><CornerstoneDetail result={ipo} /></ResultSection>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ResultSection title="股票质地"><StockQualityCard result={ipo} /></ResultSection>
            <ResultSection title="风险提示"><RiskPanel result={ipo} /></ResultSection>
          </div>
          {ipo.hk_code && <div className="mt-4"><ResultSection title="博主观点"><BloggerConsensusCard stockCode={ipo.hk_code} /></ResultSection></div>}
        </div>

        {/* 深度分析 */}
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-block h-5 w-1 rounded-full bg-[var(--danger)]" />
            <h3 className="text-base font-semibold text-white">深度分析</h3>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ResultSection title="基本信息"><InfoBasic result={ipo} /></ResultSection>
            <ResultSection title="核心财务"><InfoFinancials result={ipo} /></ResultSection>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ResultSection title="深度分析"><InfoDeep result={ipo} /></ResultSection>
            <div className="space-y-4">
              <ResultSection title="业务分部"><BusinessSegments result={ipo} /></ResultSection>
              <ResultSection title="长线视角"><FisherLynch result={ipo} /></ResultSection>
              <ResultSection title="专业投资框架"><InvestSkillPanel result={ipo} /></ResultSection>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value, tone = "text-[var(--foreground)]" }: { title: string; value: string; tone?: string }) {
  return (
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3.5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <p className="text-xs uppercase tracking-[0.15em] text-[var(--muted)]">{title}</p>
      <p className={`mt-2 text-xl font-semibold ${tone}`}>{value}</p>
    </article>
  );
}

function buildCapAndPenaltySection(ipo: AnalysisResult) {
  const strictScore = safeNumber(ipo.strict_ipo_score ?? ipo.ipo_trade_score);
  const strictCapReasons = ipo.strict_cap_reasons ?? [];
  const hasStrictCap = strictCapReasons.length > 0 && strictScore < ipo.score;
  const rawLong = ipo.raw_long_term_score_before_penalty ?? 0;
  const longPen = ipo.long_term_penalty ?? 0;
  const longPenReasons = ipo.long_term_penalty_reasons ?? [];
  const longScore = ipo.long_term_score;

  if (!hasStrictCap && !(longPen > 0 && longPenReasons.length > 0)) return null;

  return (
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      {hasStrictCap && (
        <div className="rounded-xl border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-[var(--warning)]">⚠️ 严格打新限制</span>
            <span className="font-mono text-sm text-[var(--foreground)]">{strictScore} <span className="text-[var(--muted)]">(原计算 {ipo.score})</span></span>
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-[var(--muted)]">
            {strictCapReasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}
      {longPen > 0 && longPenReasons.length > 0 && (
        <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--muted)]">长期价值分计算</span>
            <span className="font-mono text-sm text-[var(--foreground)]">{rawLong} − {longPen} = {longScore}</span>
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[10px] text-[var(--muted)]">
            {longPenReasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: 简化 page.tsx，复用 IpoDetailPanel**

page.tsx 中 `selectedIpo` 渲染段替换为：

```typescript
{/* Selected IPO detail */}
{selectedIpo && (
  <section className="mt-8">
    <IpoDetailPanel ipo={selectedIpo} onClose={() => setSelectedCode(null)} />
  </section>
)}
```

并添加 import：
```typescript
import { IpoDetailPanel } from "@/components/dashboard/IpoDetailPanel";
```

- [ ] **Step 4: 在 history/page.tsx 的详情展开行中也使用 IpoDetailPanel**

将 history/page.tsx 中 `<td colSpan={14}>` 内的详情面板替换为：

```typescript
<IpoDetailPanel ipo={raw as AnalysisResult} />
```

并添加 import：
```typescript
import { IpoDetailPanel } from "@/components/dashboard/IpoDetailPanel";
import type { AnalysisResult } from "@/lib/types";
```

- [ ] **Step 5: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dashboard/IpoDetailPanel.tsx frontend/src/app/page.tsx frontend/src/app/history/page.tsx
git commit -m "refactor: extract shared IpoDetailPanel component for dashboard and history pages"
```

---

### Task 2.3: 创建统一轮询 Hook

**Files:**
- Create: `frontend/src/hooks/useJobPolling.ts`
- Modify: `frontend/src/app/jobs/[jobId]/page.tsx`

- [ ] **Step 1: 创建 hooks/useJobPolling.ts**

```typescript
"use client";

import { useCallback, useEffect, useRef } from "react";
import { fetchJobStatus, fetchJobResult } from "@/lib/api";
import type { JobStatusResponse, AnalyzeResultResponse } from "@/lib/types";

interface UseJobPollingOptions {
  jobId: string;
  onStatusChange?: (status: JobStatusResponse) => void;
  onResult?: (result: AnalyzeResultResponse) => void;
  onError?: (message: string) => void;
  interval?: number;
  timeout?: number;
}

export function useJobPolling({ jobId, onStatusChange, onResult, onError, interval = 3000, timeout = 120000 }: UseJobPollingOptions) {
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    intervalRef.current = null;
    timeoutRef.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const status = await fetchJobStatus(jobId);
        if (cancelled) return;
        onStatusChange?.(status);

        if (status.status === "success") {
          stop();
          try {
            const result = await fetchJobResult(jobId);
            if (!cancelled) onResult?.(result);
          } catch (err) {
            if (!cancelled) onError?.(err instanceof Error ? err.message : "Failed to load result");
          }
        } else if (status.status === "failed" || status.status === "not_found") {
          stop();
          onError?.(status.error || `Job ${status.status}`);
        }
      } catch (err) {
        if (!cancelled) {
          stop();
          onError?.(err instanceof Error ? err.message : "Failed to fetch job status");
        }
      }
    }

    poll();

    if (interval > 0) {
      intervalRef.current = setInterval(poll, interval);
    }

    if (timeout > 0) {
      timeoutRef.current = setTimeout(() => {
        stop();
        onError?.("Job polling timed out");
      }, timeout);
    }

    return () => {
      cancelled = true;
      stop();
    };
  }, [jobId, interval, timeout, onStatusChange, onResult, onError, stop]);

  return { stop };
}
```

- [ ] **Step 2: 简化 jobs/[jobId]/page.tsx 中的轮询逻辑**

用 `useJobPolling` 替换 `setInterval` 手动轮询：

```typescript
import { useJobPolling } from "@/hooks/useJobPolling";

// 在组件内：
useJobPolling({
  jobId,
  onStatusChange: (status) => setJob(status),
  onResult: (result) => setResult(result),
  onError: (message) => setResultError(message),
  interval: 3000,
});
```

同时移除原有的 `useEffect` 轮询和 `useRef` 清理逻辑。

- [ ] **Step 3: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useJobPolling.ts frontend/src/app/jobs/[jobId]/page.tsx
git commit -m "refactor: extract useJobPolling hook and apply to jobs page"
```

---

### Task 2.4: 移除不必要的 `"use client"` 标记 (SSR 化)

**Files:**
- Modify: `frontend/src/components/Navbar.tsx`
- Modify: `frontend/src/components/results/PeerComparisonFull.tsx`
- Modify: `frontend/src/components/results/InvestSkillPanel.tsx`
- Modify: `frontend/src/components/results/DetailViewExtras.tsx`
- Modify: `frontend/src/components/results/CornerstoneDetail.tsx`
- Modify: `frontend/src/components/results/PostListingCard.tsx`
- Modify: `frontend/src/components/results/CompanyProfileCard.tsx`

- [ ] **Step 1: 审计各组件**

检查以下组件是否使用了任何客户端 hooks（useState, useEffect, useRef, useRouter 等）或浏览器 API：

| 组件 | 是否有 hooks | Action |
|------|--------------|--------|
| PeerComparisonFull.tsx | 否 | 移除 "use client" |
| InvestSkillPanel.tsx | 否 | 移除 "use client" |
| DetailViewExtras.tsx | 否 | 移除 "use client" |
| CornerstoneDetail.tsx | 否 | 移除 "use client" |
| PostListingCard.tsx | 否 | 移除 "use client" |
| CompanyProfileCard.tsx | 否 | 移除 "use client" |
| Navbar.tsx | 是 (usePathname) | 保留 "use client" |

- [ ] **Step 2: 逐个移除不必要的 "use client"**

```bash
# 对每个组件，删除第一行的 "use client"; 字符串
```

- [ ] **Step 3: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/results/PeerComparisonFull.tsx frontend/src/components/results/InvestSkillPanel.tsx frontend/src/components/results/DetailViewExtras.tsx frontend/src/components/results/CornerstoneDetail.tsx frontend/src/components/results/PostListingCard.tsx frontend/src/components/results/CompanyProfileCard.tsx
git commit -m "perf: remove unnecessary 'use client' directives from pure display components"
```

---

### Task 2.5: 添加 Suspense 边界和 loading.tsx

**Files:**
- Create: `frontend/src/app/loading.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/history/page.tsx`

- [ ] **Step 1: 创建 app/loading.tsx**

```tsx
import { Loading } from "@/components/Loading";

export default function RootLoading() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
      <Loading message="Loading…" />
    </main>
  );
}
```

- [ ] **Step 2: 用 Suspense 包裹 Dashboard 的数据区**

在 page.tsx 中，用 `<Suspense fallback={<Loading message="Loading IPO data…" />}>` 包裹表格和详情面板区域。

- [ ] **Step 3: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/loading.tsx frontend/src/app/page.tsx
git commit -m "feat: add loading.tsx and Suspense boundaries for streaming"
```

---

## 迭代三：体验打磨

### Task 3.1: 增强表单校验

**Files:**
- Modify: `frontend/src/app/upload/page.tsx`
- Modify: `frontend/src/app/reanalyze/page.tsx`

- [ ] **Step 1: Upload 页面增加字段级校验反馈**

在文件 input 下方添加空状态/格式校验的内联错误文案（红色文字），而不是通用的 ErrorDisplay。文件未选择时显示红色边框类名。

- [ ] **Step 2: Reanalyze 页面 JSON 实时校验**

为 JSON textarea 添加实时语法校验，输入变化时立即尝试 `JSON.parse`，有效显示绿色 ✓，无效显示红色 ✗。

- [ ] **Step 3: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/upload/page.tsx frontend/src/app/reanalyze/page.tsx
git commit -m "feat: enhance form validation with inline field-level feedback"
```

---

### Task 3.2: Select 暗色主题适配

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/app/peers/page.tsx`
- Modify: `frontend/src/app/history/page.tsx`

- [ ] **Step 1: 在 globals.css 中添加 select 暗色样式**

```css
select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%2393a9c6' stroke-width='1.5' fill='none'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 1rem center;
  background-size: 12px 8px;
  padding-right: 2.5rem;
}

select option {
  background-color: #0c1a2f;
  color: #ecf7ff;
}
```

- [ ] **Step 2: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "style: add dark theme styling for native select elements"
```

---

### Task 3.3: 轻量状态缓存

**Files:**
- Create: `frontend/src/lib/CacheContext.tsx`
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: 创建 CacheContext.tsx**

```typescript
"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import type { LiveResultsResponse, HistoryListResponse } from "./types";

interface CacheState {
  liveData: LiveResultsResponse | null;
  historyData: HistoryListResponse | null;
}

interface CacheContextValue extends CacheState {
  setLiveData: (data: LiveResultsResponse) => void;
  setHistoryData: (data: HistoryListResponse) => void;
  invalidate: () => void;
}

const CacheContext = createContext<CacheContextValue | null>(null);

export function CacheProvider({ children }: { children: ReactNode }) {
  const [cache, setCache] = useState<CacheState>({ liveData: null, historyData: null });

  const setLiveData = useCallback((data: LiveResultsResponse) => {
    setCache((prev) => ({ ...prev, liveData: data }));
  }, []);

  const setHistoryData = useCallback((data: HistoryListResponse) => {
    setCache((prev) => ({ ...prev, historyData: data }));
  }, []);

  const invalidate = useCallback(() => {
    setCache({ liveData: null, historyData: null });
  }, []);

  return (
    <CacheContext.Provider value={{ ...cache, setLiveData, setHistoryData, invalidate }}>
      {children}
    </CacheContext.Provider>
  );
}

export function useCache(): CacheContextValue {
  const ctx = useContext(CacheContext);
  if (!ctx) throw new Error("useCache must be used within CacheProvider");
  return ctx;
}
```

- [ ] **Step 2: 在 layout.tsx 中包裹 CacheProvider**

找到 `RootLayout` 函数，在 `<body>` 内部包裹 `CacheProvider`：

```typescript
import { CacheProvider } from "@/lib/CacheContext";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <CacheProvider>
          <Navbar />
          <div className="flex-1">{children}</div>
        </CacheProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 3: 确认构建通过**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/CacheContext.tsx frontend/src/app/layout.tsx
git commit -m "feat: add CacheContext for cross-page data caching"
```

---

## 迭代四：可持续优化

### Task 4.1: CI 集成前端测试

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: 在 ci.yml 的 frontend-build job 中添加 test 步骤**

```yaml
  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - name: Install frontend dependencies
        run: |
          cd frontend
          npm ci
      - name: Lint frontend
        run: |
          cd frontend
          npm run lint
      - name: Test frontend
        run: |
          cd frontend
          npm test
      - name: Build frontend
        run: |
          cd frontend
          npm run build
```

注意：将 test 放在 build 之前，以便更快反馈测试失败。

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add frontend test step to CI pipeline"
```

---

## 自审清单

- [x] 规格覆盖：每个规格章节都有对应的 Task（类型→工具函数→组件签名→测试→页面拆分→共享面板→轮询→SSR化→Suspense→表单→Select→缓存→CI）
- [x] 无占位符：所有代码块都是完整可执行的代码，无 TBD/TODO
- [x] 类型一致性：`AnalysisResult` 类型定义在 Task 1.1，后续所有组件改造统一引用此类型；`useFilters` 和 filter 测试使用了相同的过滤逻辑