# 前端可访问性与交互优化实施计划

> **For agentic workers:** 按任务逐步执行，每个步骤使用 checkbox (`- [ ]`) 跟踪。

**Goal:** 修复前端界面的可访问性（a11y）缺陷和交互体验问题，使其符合 Web Interface Guidelines。

**Architecture:** 通过最小化改动修复现有组件，不引入新依赖。核心策略：补充 ARIA 属性、修复语义化 HTML、添加 focus-visible 样式、优化键盘交互。

**Tech Stack:** Next.js 15 + React 19 + Tailwind CSS v4 + TypeScript

---

## 任务清单概览

| 任务 | 范围 | 影响文件数 |
|------|------|-----------|
| Task 1 | 修复 HTML lang 属性 | 1 |
| Task 2 | 补充 Icon-only 按钮 aria-label | 3 |
| Task 3 | 修复表格行键盘交互 | 2 |
| Task 4 | 添加全局 focus-visible 样式 | 1 |
| Task 5 | 修复表单 label 关联与 autocomplete | 2 |
| Task 6 | 添加 aria-live 区域用于异步通知 | 2 |
| Task 7 | 优化 Loading 文本与减少动画偏好 | 2 |
| Task 8 | 修复历史页面表格响应式显示 | 1 |
| Task 9 | 统一日期/数字格式使用 Intl | 3 |
| Task 10 | 运行 lint 与类型检查 | 1 |

---

## Task 1: 修复 HTML lang 属性

**问题:** `<html lang="en">` 但页面内容主要是中文，影响屏幕阅读器发音和搜索引擎语言识别。

**Files:**
- Modify: `frontend/src/app/layout.tsx:28`

- [ ] **Step 1: 修改 lang 属性**

```tsx
// 修改前
<html
  lang="en"
  className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
>

// 修改后
<html
  lang="zh-CN"
  className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/layout.tsx
git commit -m "fix(a11y): set html lang to zh-CN for Chinese content"
```

---

## Task 2: 补充 Icon-only 按钮 aria-label

**问题:** 多个按钮使用 emoji 作为视觉标识，但没有 `aria-label`，屏幕阅读器无法识别按钮用途。

**Files:**
- Modify: `frontend/src/app/page.tsx` (4 处)
- Modify: `frontend/src/app/history/page.tsx` (3 处)
- Modify: `frontend/src/app/peers/page.tsx` (2 处)

- [ ] **Step 1: 修复 Dashboard 页面按钮**

在 `frontend/src/app/page.tsx` 中修改以下按钮：

```tsx
// 第 281-294 行：更新IPO按钮
<button
  onClick={() => handleRefresh(false)}
  disabled={refreshing}
  aria-label="更新IPO（使用缓存）"
  className="..."
>

// 第 295-301 行：强制刷新按钮
<button
  onClick={() => handleRefresh(true)}
  disabled={refreshing}
  aria-label="强制刷新（重新下载）"
  className="..."
>

// 第 417-422 行：收起按钮
<button
  onClick={() => setSelectedCode(null)}
  aria-label="收起详情"
  className="..."
>
```

- [ ] **Step 2: 修复 History 页面按钮**

在 `frontend/src/app/history/page.tsx` 中修改：

```tsx
// 第 247-265 行：跟踪全部按钮
<button
  onClick={...}
  disabled={trackAllLoading}
  aria-label="跟踪全部已结束待更新的IPO"
  className="..."
>

// 第 421-446 行：跟踪选中IPO按钮
<button
  onClick={...}
  disabled={trackLoading === r.stock_code}
  aria-label={`跟踪 ${r.stock_code} IPO`}
  className="..."
>

// 第 447-469 行：上传配发公告按钮（label 内的 input）
// 已为 label，无需修改，但确保 label 文本清晰
```

- [ ] **Step 3: 修复 Peers 页面按钮**

在 `frontend/src/app/peers/page.tsx` 中修改：

```tsx
// 第 166-172 行：预览过期同行按钮
<button
  onClick={() => handleRefresh(true)}
  disabled={refreshing}
  aria-label="预览过期同行数据"
  className="..."
>

// 第 173-179 行：写入过期同行按钮
<button
  onClick={() => handleRefresh(false)}
  disabled={refreshing}
  aria-label="写入过期同行数据"
  className="..."
>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/page.tsx frontend/src/app/history/page.tsx frontend/src/app/peers/page.tsx
git commit -m "fix(a11y): add aria-label to icon-only buttons"
```

---

## Task 3: 修复表格行键盘交互

**问题:** `<tr onClick={...}>` 不是可聚焦元素，键盘用户无法通过 Tab 键选中行，也无法通过 Enter/Space 键触发点击。

**Files:**
- Modify: `frontend/src/app/page.tsx:374-378`
- Modify: `frontend/src/app/history/page.tsx:368-374`

- [ ] **Step 1: 在 Dashboard 页面添加键盘支持**

修改 `frontend/src/app/page.tsx` 中的表格行：

```tsx
// 修改前
<tr
  key={ipoCode}
  onClick={() => setSelectedCode(selectedCode === ipoCode ? null : ipoCode)}
  className="cursor-pointer border-b border-[var(--border)]/50 transition hover:bg-white/[0.03]"
>

// 修改后
<tr
  key={ipoCode}
  onClick={() => setSelectedCode(selectedCode === ipoCode ? null : ipoCode)}
  onKeyDown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setSelectedCode(selectedCode === ipoCode ? null : ipoCode);
    }
  }}
  tabIndex={0}
  role="button"
  aria-expanded={selectedCode === ipoCode}
  aria-label={`查看 ${String(ipo["company_name"] ?? ipoCode)} 详情`}
  className="cursor-pointer border-b border-[var(--border)]/50 transition hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/50"
>
```

- [ ] **Step 2: 在 History 页面添加键盘支持**

修改 `frontend/src/app/history/page.tsx` 中的表格行：

```tsx
// 修改前
<tr
  key={idx}
  className={`border-b border-[var(--border)]/50 transition cursor-pointer ${
    isExpanded ? "bg-[var(--accent)]/5" : "hover:bg-white/[0.03]"
  }`}
  onClick={() => setExpandedCode(isExpanded ? null : r.stock_code)}
>

// 修改后
<tr
  key={idx}
  className={`border-b border-[var(--border)]/50 transition cursor-pointer ${
    isExpanded ? "bg-[var(--accent)]/5" : "hover:bg-white/[0.03]"
  } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/50`}
  onClick={() => setExpandedCode(isExpanded ? null : r.stock_code)}
  onKeyDown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setExpandedCode(isExpanded ? null : r.stock_code);
    }
  }}
  tabIndex={0}
  role="button"
  aria-expanded={isExpanded}
  aria-label={`查看 ${r.company_name} (${r.stock_code}) 详情`}
>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/page.tsx frontend/src/app/history/page.tsx
git commit -m "fix(a11y): add keyboard support to clickable table rows"
```

---

## Task 4: 添加全局 focus-visible 样式

**问题:** 所有交互元素缺少可见的 focus 状态，键盘导航时无法知道当前焦点位置。

**Files:**
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: 添加全局 focus-visible 样式**

在 `frontend/src/app/globals.css` 末尾添加：

```css
/* Focus-visible styles for keyboard navigation */
button:focus-visible,
a:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
[tabindex]:not([tabindex="-1"]):focus-visible {
  outline: none;
  ring: 2px;
  ring-color: var(--accent);
  ring-opacity: 0.5;
  border-radius: 0.5rem;
}

/* Respect prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "feat(a11y): add global focus-visible styles and respect reduced-motion"
```

---

## Task 5: 修复表单 label 关联与 autocomplete

**问题:** 
1. `FilterCheckbox` 组件的 checkbox 没有独立 `id`，依赖 label 包裹但不够明确
2. 文本输入框缺少 `autocomplete` 和 `name` 属性
3. 文件输入框缺少 `aria-describedby` 用于已选文件信息

**Files:**
- Modify: `frontend/src/app/page.tsx:51-58`
- Modify: `frontend/src/app/upload/page.tsx`
- Modify: `frontend/src/app/reanalyze/page.tsx`

- [ ] **Step 1: 修复 FilterCheckbox 组件**

修改 `frontend/src/app/page.tsx` 中的 `FilterCheckbox`：

```tsx
// 修改前
function FilterCheckbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] transition hover:bg-white/8">
      <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

// 修改后
function FilterCheckbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  const id = `filter-${label.replace(/[^a-zA-Z0-9]/g, '-')}`;
  return (
    <label htmlFor={id} className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] transition hover:bg-white/8">
      <input id={id} type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}
```

- [ ] **Step 2: 修复 Upload 页面表单**

修改 `frontend/src/app/upload/page.tsx`：

```tsx
// 第 79-91 行：文件输入添加 aria-describedby
<div>
  <Label htmlFor="pdf">PDF 文件</Label>
  <input
    id="pdf"
    type="file"
    accept=".pdf,application/pdf"
    name="prospectus_pdf"
    aria-describedby={file ? "file-selected" : undefined}
    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
    className="..."
  />
  {file && (
    <p id="file-selected" className="mt-2 text-xs text-[var(--muted)]">
      已选择：{file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
    </p>
  )}
</div>

// 第 94-102 行：股票代码输入添加 autocomplete
<Input
  id="stock_code"
  name="stock_code"
  placeholder="例如：01234"
  value={stockCode}
  onChange={(e) => setStockCode(e.target.value)}
  autoComplete="off"
  spellCheck={false}
/>

// 第 104-112 行：公司名称输入
<Input
  id="company_name"
  name="company_name"
  placeholder="例如：某某控股有限公司"
  value={companyName}
  onChange={(e) => setCompanyName(e.target.value)}
  autoComplete="off"
  spellCheck={false}
/>
```

- [ ] **Step 3: 修复 Reanalyze 页面表单**

修改 `frontend/src/app/reanalyze/page.tsx`：

```tsx
// 股票代码输入添加 autocomplete
<Input
  id="stock_code"
  name="stock_code"
  placeholder="例如：09995"
  value={stockCode}
  onChange={(e) => setStockCode(e.target.value)}
  required
  autoComplete="off"
  spellCheck={false}
/>

// 公司名称输入
<Input
  id="company_name"
  name="company_name"
  placeholder="例如：某某控股有限公司"
  value={companyName}
  onChange={(e) => setCompanyName(e.target.value)}
  autoComplete="off"
  spellCheck={false}
/>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/page.tsx frontend/src/app/upload/page.tsx frontend/src/app/reanalyze/page.tsx
git commit -m "fix(a11y): fix form label associations and add autocomplete attributes"
```

---

## Task 6: 添加 aria-live 区域用于异步通知

**问题:** 异步操作（刷新、跟踪、搜索）完成后，成功/错误消息通过视觉显示，但屏幕阅读器用户无法感知状态变化。

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/history/page.tsx`

- [ ] **Step 1: 在 Dashboard 页面添加 aria-live 区域**

修改 `frontend/src/app/page.tsx`，在错误显示区域添加 `aria-live`：

```tsx
// 第 331-335 行
{error && (
  <section className="mt-6" aria-live="polite" aria-atomic="true">
    <ErrorDisplay message={error} onRetry={load} />
  </section>
)}
```

同时，在刷新按钮状态变化时添加状态文本：

```tsx
// 在刷新按钮附近添加状态指示器（第 304-314 行之后）
{refreshing && (
  <span className="sr-only" aria-live="polite">正在刷新 IPO 数据...</span>
)}
```

- [ ] **Step 2: 在 History 页面添加 aria-live 区域**

修改 `frontend/src/app/history/page.tsx`：

```tsx
// 第 329-333 行
{error && (
  <section className="mt-6" aria-live="polite" aria-atomic="true">
    <ErrorDisplay message={error} onRetry={handleRetry} />
  </section>
)}

// 第 275-277 行：跟踪结果添加 aria-live
{trackAllResult && (
  <span className="text-sm text-[var(--muted)]" aria-live="polite" aria-atomic="true">
    {trackAllResult}
  </span>
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/page.tsx frontend/src/app/history/page.tsx
git commit -m "fix(a11y): add aria-live regions for async status updates"
```

---

## Task 7: 优化 Loading 文本与减少动画偏好

**问题:** 
1. Loading 组件使用 `animate-spin`，没有考虑 `prefers-reduced-motion`
2. 部分 loading 文本使用 `...` 而非 `…`

**Files:**
- Modify: `frontend/src/components/Loading.tsx`
- Modify: `frontend/src/app/page.tsx` (loading 文本)

- [ ] **Step 1: 优化 Loading 组件**

修改 `frontend/src/components/Loading.tsx`：

```tsx
export function Loading({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-12">
      <div 
        className="h-8 w-8 rounded-full border-2 border-[var(--border)] border-t-[var(--accent)] motion-safe:animate-spin"
        aria-hidden="true"
      />
      <p className="text-sm tracking-wide text-[var(--muted)]">{message}</p>
    </div>
  );
}
```

- [ ] **Step 2: 统一 loading 文本中的省略号**

检查并修正 `frontend/src/app/page.tsx` 中的 loading 文本：

```tsx
// 第 254 行
<Loading message="Loading live IPO data…" />

// 第 289 行
<>刷新中…</>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Loading.tsx frontend/src/app/page.tsx
git commit -m "fix(a11y): respect reduced-motion in Loading and fix ellipsis"
```

---

## Task 8: 修复历史页面表格响应式显示

**问题:** History 页面表格中，部分列设置了 `hidden sm:table-cell` 或 `hidden md:table-cell`，但表头 `<th>` 没有对应的 hidden 类，导致表头与数据列不对齐。

**Files:**
- Modify: `frontend/src/app/history/page.tsx:343-360`

- [ ] **Step 1: 修复表头与数据列对齐**

修改 `frontend/src/app/history/page.tsx` 表头部分：

```tsx
<thead>
  <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
    <th className="px-5 py-4 font-medium"></th>
    <th className="px-5 py-4 font-medium">状态</th>
    <th className="px-5 py-4 font-medium">股票代码</th>
    <th className="px-5 py-4 font-medium">公司名称</th>
    <th className="px-5 py-4 font-medium text-right">发行价</th>
    <th className="px-5 py-4 font-medium text-right">市值</th>
    <th className="px-5 py-4 font-medium text-right">公开发售手数</th>
    <th className="px-5 py-4 font-medium text-right">每手股数</th>
    <th className="px-5 py-4 font-medium text-right">综合评分</th>
    <th className="hidden px-5 py-4 font-medium text-right sm:table-cell">交易信号</th>
    <th className="hidden px-5 py-4 font-medium text-right md:table-cell">长期价值</th>
    <th className="px-5 py-4 font-medium">估值压力</th>
    <th className="px-5 py-4 font-medium">市场热度</th>
    <th className="px-5 py-4 font-medium">截止日</th>
    <th className="px-5 py-4 font-medium"></th>
  </tr>
</thead>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/history/page.tsx
git commit -m "fix(ui): align history table header with responsive columns"
```

---

## Task 9: 统一日期/数字格式使用 Intl

**问题:** 日期和数字格式使用硬编码格式（如 `toLocaleString()`），未使用 `Intl` API，在多语言环境下可能不一致。

**Files:**
- Modify: `frontend/src/app/jobs/[jobId]/page.tsx`
- Modify: `frontend/src/app/history/page.tsx`
- Modify: `frontend/src/app/peers/page.tsx`

- [ ] **Step 1: 创建日期格式化工具函数**

在 `frontend/src/lib/utils.ts` 中创建（如果不存在）：

```typescript
export function formatDateTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(d);
}

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d);
}
```

- [ ] **Step 2: 替换 jobs 页面硬编码日期**

修改 `frontend/src/app/jobs/[jobId]/page.tsx`：

```tsx
// 第 172 行
import { formatDateTime } from '@/lib/utils';

// 替换所有 new Date(...).toLocaleString()
<Field label="Created" value={formatDateTime(job.created_at)} />
<Field label="Updated" value={formatDateTime(job.updated_at)} />
<Field label="Started" value={job.started_at ? formatDateTime(job.started_at) : "—"} />
<Field label="Finished" value={job.finished_at ? formatDateTime(job.finished_at) : "—"} />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/utils.ts frontend/src/app/jobs/[jobId]/page.tsx
git commit -m "refactor: use Intl.DateTimeFormat for consistent date formatting"
```

---

## Task 10: 运行 lint 与类型检查

**Files:**
- 所有已修改文件

- [ ] **Step 1: 运行 ESLint**

```bash
cd frontend
npx eslint . --ext .ts,.tsx
```

预期：无错误（或仅与本次修改无关的既有警告）

- [ ] **Step 2: 运行 TypeScript 类型检查**

```bash
cd frontend
npx tsc --noEmit
```

预期：无类型错误

- [ ] **Step 3: 最终 Commit（如需要修复）**

```bash
git add -A
git commit -m "chore: fix lint and type errors from a11y improvements"
```

---

## 自检查清单

- [ ] 所有按钮都有可访问的文本或 `aria-label`
- [ ] 所有表格行可通过键盘访问（Tab + Enter/Space）
- [ ] 所有交互元素有可见的 focus 状态
- [ ] 表单控件有正确的 `label` 关联
- [ ] 异步更新区域有 `aria-live`
- [ ] 动画尊重 `prefers-reduced-motion`
- [ ] 日期/数字格式使用 `Intl` API
- [ ] 无 TypeScript 类型错误
- [ ] 无 ESLint 错误
