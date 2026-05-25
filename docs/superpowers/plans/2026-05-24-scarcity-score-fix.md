# 赛道稀缺性评分 (Scarcity Score) 修复计划

> **For agentic workers:** 按任务逐步执行，每个步骤使用 checkbox (`- [ ]`) 跟踪。

**Goal:** 修复 `_calc_scarcity_score` 的逻辑缺陷，使稀缺性评分能真实反映公司的赛道地位，避免非龙头公司获得满分。

**Architecture:** 在现有评分维度基础上增加**市场份额排名**维度，同时降低单一维度的权重上限，使满分条件更严格。保留现有维度，新增 `market_share_rank` 字段作为评分因子。

**Tech Stack:** Python (ipo_analyzer) + 前端展示组件

---

## 问题诊断

### 联网搜索验证结果

根据多个来源（星岛新闻、36氪、中国工业报等）确认：

| 排名 | 公司 | 消费级3D打印市占率 |
|------|------|-------------------|
| 1 | 拓竹科技 | 35.5% |
| **2** | **创想三维** | **11.2%** |
| 3+ | 纵维立方、智能派等 | 其余 |

### 当前评分逻辑 (peer_comps.py:882-921)

```
scarcity_score = 同行数量≤2(+3) + 技术壁垒≥7(+3) + S级基石(+2) + 营收增长>100%(+2) = 10/10
```

**缺陷**：
1. ❌ 完全没有考虑公司在行业中的市场份额排名
2. ❌ 满分条件过于宽松（4个维度全满足即可满分）
3. ❌ "赛道稀缺" 和 "公司行业地位" 混为一谈——前者是赛道本身的属性，后者是公司在赛道中的地位，两者都应影响稀缺性判断

---

## 任务清单

### Task 1: 在 `_calc_scarcity_score` 中增加市场份额排名维度

**Files:**
- Modify: `ipo_analyzer/peer_comps.py:882-921` (`_calc_scarcity_score`)
- Modify: `ipo_analyzer/peer_comps.py` (需要查看 `matched_peers` 数据结构)

- [ ] **Step 1: 确认 market_share_data 数据可用**

检查 `matched_peers` 是否包含市场份额/排名数据，以及 `prospectus_info` 是否有 `market_share_data`、`market_size_data`、`dominant_share_pct`、`dominant_segment` 等字段。

- [ ] **Step 2: 修改 `_calc_scarcity_score` 函数**

```python
def _calc_scarcity_score(prospectus_info, matched_peers, sector):
    """稀缺性评分：衡量市场上同类公司的稀缺程度（与 _calc_peer_score 的行业加分互补）

    _calc_peer_score 的行业加分反映行业投资吸引力，
    此处的行业加分仅反映该行业在港股上市公司数量稀少的程度。
    """
    score = 0
    rnd = prospectus_info.get("rnd_pipeline", {}) or {}
    ca = prospectus_info.get("cornerstone_analysis", {}) or {}
    
    # --- 维度1: 港股同行数量（最高+2，原+3）---
    listed = [p for p in matched_peers if p.get("type") == "listed"]
    if len(listed) <= 2:
        score += 2
    elif len(listed) <= 4:
        score += 1

    # --- 维度2: 技术壁垒（最高+2，原+3）---
    moat = rnd.get("technology_moat_score", 0)
    if moat >= 7:
        score += 2
    elif moat >= 5:
        score += 1

    # --- 维度3: 基石投资者质量（最高+2，不变）---
    cornerstone_rows = ca.get("cornerstone_investors") or []
    tiers = {row.get("tier", "") for row in cornerstone_rows if row.get("tier")}
    if not tiers:
        matched_inv = ca.get("matched_investors", [])
        tiers = {m.get("tier", "") for m in matched_inv if m.get("tier")}
    if "S" in tiers:
        score += 2
    elif "A" in tiers:
        score += 1

    # --- 维度4: 营收增长（最高+1，原+2）---
    rev = prospectus_info.get("revenue")
    rev_y1 = prospectus_info.get("revenue_y1")
    if _is_num(rev) and _is_num(rev_y1) and rev_y1 > 0:
        g = (rev - rev_y1) / rev_y1
        if g > 1.0:
            score += 1
        elif g > 0.5:
            score += 0.5

    # --- 新增维度5: 市场份额/行业地位（最高+3）---
    # 如果招股书解析出了市场份额数据，根据排名给分
    market_share = prospectus_info.get("market_share_data") or []
    dominant_pct = prospectus_info.get("dominant_share_pct")
    
    if market_share and len(market_share) > 0:
        # market_share 是按份额排序的公司列表
        top_company = market_share[0] if market_share else {}
        company_name = prospectus_info.get("company_name", "")
        top_name = top_company.get("name", "") or top_company.get("company", "")
        
        # 判断该公司是否位列第一
        is_rank1 = (company_name and top_name and 
                    (company_name in top_name or top_name in company_name))
        
        if is_rank1:
            score += 3  # 赛道龙头
        elif len(market_share) <= 3:
            score += 2  # 前三
        else:
            score += 1  # 前五或更后
    elif _is_num(dominant_pct) and dominant_pct > 20:
        # 如果主导份额 >20%，至少加分
        score += 2
    
    # 医疗赛道港股上市公司较少，适度加分
    if sector == "healthcare":
        score += 1

    return min(10, score)
```

- [ ] **Step 3: 验证语法**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python3 -m py_compile ipo_analyzer/peer_comps.py
```

---

### Task 2: 前端展示优化 — 稀缺性评分增加明细

**Files:**
- Modify: `frontend/src/components/results/PeerComparisonFull.tsx`

- [ ] **Step 1: 前端展示优化**

当前前端只显示 `{scarcity}/10`，增加 hover 提示显示各项明细：

```tsx
// 修改前
<p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{scarcity}/10</p>

// 修改后
<div className="group relative">
  <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{scarcity}/10</p>
  <div className="absolute bottom-full left-0 mb-2 hidden rounded-lg border border-[var(--border)] bg-[var(--surface-strong)] p-3 text-xs text-[var(--muted)] shadow-lg group-hover:block min-w-[200px]">
    <p className="text-[var(--foreground)] font-semibold mb-1">稀缺性评分明细</p>
    <ul className="space-y-0.5">
      <li>• 同行数量: {scarcity_peer_count}</li>
      <li>• 技术壁垒: {scarcity_moat}</li>
      <li>• 基石质量: {scarcity_cornerstone}</li>
      <li>• 营收增长: {scarcity_growth}</li>
      <li>• 行业地位: {scarcity_market_share}</li>
    </ul>
  </div>
</div>
```

---

### Task 3: 更新相关引用

**Files:**
- Check: `ipo_analyzer/scoring.py:62-67` (moat_score 中使用 scarcity 阈值)
- Check: `ipo_analer/scoring.py:491` (估值调整中使用 scarcity)
- Check: `ipo_analyzer/report.py:1062` (PDF报告中使用 scarcity)

- [ ] **Step 1: 检查阈值配置**

确认 `SETTINGS.prospectus_quality.scarcity_moat_strong` 和 `scarcity_moat_moderate` 的值是否仍合理。如果旧系统满分是10，7分就是"高度稀缺"，新系统满分仍然是10，阈值不变。

- [ ] **Step 2: 验证语法**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python3 -m py_compile ipo_analyzer/scoring.py ipo_analyzer/report.py
```

---

### Task 4: 运行 lint 与类型检查

**Files:**
- 所有已修改文件

- [ ] **Step 1: 运行 ESLint**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/frontend && npx eslint . --ext .ts,.tsx
```

- [ ] **Step 2: 运行 TypeScript 类型检查**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/frontend && npx tsc --noEmit
```

---

## 修复效果预期

### 修复前（创想三维 10/10）

| 维度 | 得分 |
|------|------|
| 同行≤2 | +3 |
| 技术壁垒≥7 | +3 |
| S级基石 | +2 |
| 营收增长>100% | +2 |
| **行业排名** | **❌ 未考虑** |
| **总分** | **10/10** |

### 修复后（创想三维预期 ~7-8/10）

| 维度 | 得分 | 说明 |
|------|------|------|
| 同行≤2 | +2 | 降低权重 |
| 技术壁垒≥7 | +2 | 降低权重 |
| S级基石 | +2 | 不变 |
| 营收增长>100% | +1 | 降低权重 |
| 行业排名 #2 | +2 | **新增**，排名第二得2分 |
| **总分** | **~9/10**（仍高但合理） | 反映赛道本身稀缺+非龙头 |

> 注：如果公司不是第一名，行业地位加分只有 2分（前三）而非 3分（第一），总分会下降 1-3 分，避免了非龙头公司拿满分。

---

## 自检查清单

- [ ] scarcity_score 现在考虑市场份额排名
- [ ] 非第一名公司无法获得满分
- [ ] 赛道龙头仍然可以获得高分
- [ ] Python 语法检查通过
- [ ] ESLint 无错误
- [ ] TypeScript 无类型错误
