import { fmtNum, fmtPct, fmtInt, safeNumber, scoreColor } from "@/lib/utils";
import type { AvailabilityMeta } from "@/lib/utils";
import type { AnalysisResult } from "@/lib/types";

/* ------------------------------------------------------------------ */
/* 理由情感分析 — 判断正面/负面/中性                                  */
/* ------------------------------------------------------------------ */
const POSITIVE_KEYWORDS = [
  "强", "健康", "支撑", "亮点", "热门", "盈利", "增长强劲", "高", "好", "优",
  "可打新", "信号强", "突出", "有", "充足", "合理", "匹配", "背书",
];
const NEGATIVE_KEYWORDS = [
  "弱", "偏弱", "隐忧", "不足", "压力", "风险", "红旗", "降权", "贵", "偏高",
  "异常", "缺失", "未见", "未", "低", "差", "负面", "警示", "警惕",
];
const NEGATIVE_PREFIXES = [
  "不宜", "仅部分", "仍需", "存在", "需关注", "需核对", "疑似",
];

function analyzeReasonSentiment(reason: string): "positive" | "negative" | "neutral" {
  const text = reason.toLowerCase();
  let posCount = 0;
  let negCount = 0;

  for (const kw of POSITIVE_KEYWORDS) {
    if (text.includes(kw)) posCount++;
  }
  for (const kw of NEGATIVE_KEYWORDS) {
    if (text.includes(kw)) negCount++;
  }
  for (const prefix of NEGATIVE_PREFIXES) {
    if (text.includes(prefix)) negCount += 2;
  }

  // 特殊规则
  if (text.includes("基石亮点")) return "positive";
  if (text.includes("基石隐忧")) return "negative";
  if (text.includes("申购建议")) {
    if (text.includes("不宜") || text.includes("谨慎")) return "negative";
    return "positive";
  }
  // "偏贵" / "高于" 等明确负面描述
  if (text.includes("偏贵") || text.includes("高于同行")) return "negative";

  if (posCount > negCount) return "positive";
  if (negCount > posCount) return "negative";
  return "neutral";
}

function reasonStyle(sentiment: "positive" | "negative" | "neutral"): string {
  if (sentiment === "positive") {
    return "border-[var(--success)]/30 bg-[var(--success)]/10 text-[var(--success)]";
  }
  if (sentiment === "negative") {
    return "border-[var(--danger)]/30 bg-[var(--danger)]/10 text-[var(--danger)]";
  }
  return "border-[var(--border)] bg-white/5 text-[var(--foreground)]";
}

type KpiItem = [string, React.ReactNode] | [string, React.ReactNode, AvailabilityMeta | undefined];

function KpiGrid({ items }: { items: KpiItem[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      {items.map(([label, value, avail]) => {
        const status = avail?.status;
        const isDimmed = status === "not_applicable" || status === "not_found";
        const statusLabel = status === "not_applicable" ? "不适用" : status === "not_found" ? "未披露" : null;
        return (
          <div
            key={label}
            className={`rounded-xl border p-3 transition ${
              isDimmed
                ? "border-[var(--border)]/40 bg-white/[0.01] opacity-50"
                : "border-[var(--border)] bg-white/[0.03]"
            }`}
            title={avail?.reason}
          >
            <p className="text-xs text-[var(--muted)] flex items-center gap-1">
              {label}
              {statusLabel && (
                <span className="rounded px-1 py-0.5 text-[10px] bg-white/5 text-[var(--muted)]">
                  {statusLabel}
                </span>
              )}
            </p>
            <p className={`mt-1 text-sm font-medium ${
              isDimmed ? "text-[var(--muted)]" : "text-[var(--foreground)]"
            }`}>{value}</p>
          </div>
        );
      })}
    </div>
  );
}

function SectionTitle({ title }: { title: string }) {
  return <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--foreground)]">{title}</p>;
}

/* ------------------------------------------------------------------ */
/* 1. Score Waterfall                                                 */
/* ------------------------------------------------------------------ */
export function ScoreWaterfall({ result }: { result: AnalysisResult }) {
  const raw = result as unknown as Record<string, unknown>;
  const wp = (raw.weight_profile as Record<string, unknown> | undefined) || {};
  const weights = (wp.weights as Record<string, number> | undefined) || {};
  if (!weights || Object.keys(weights).length === 0) return null;

  const dimensions = [
    { label: "交易面", score: Number(result.trade_score ?? 0), weight: weights.trade ?? 0 },
    { label: "基本面", score: Number(result.fundamental_score ?? 0), weight: weights.fundamental ?? 0 },
    { label: "估值面", score: Number(result.valuation_score ?? 0), weight: weights.valuation ?? 0 },
    { label: "主题面", score: Number(result.theme_score ?? 0), weight: weights.theme ?? 0 },
  ];

  let rawTotal = 0;
  const rows = dimensions.map((d) => {
    const contribution = Math.round(d.score * d.weight);
    rawTotal += contribution;
    return { ...d, contribution };
  });

  const penalty = Number(result.risk_penalty ?? 0);
  const final = Number(result.score ?? 0);
  const capReason = ((raw.debug_info as Record<string, unknown> | undefined)?.cap_reason as string) || "";

  return (
    <div className="flex flex-col gap-2">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between border-b border-[var(--border)]/30 py-2">
          <div className="flex items-center gap-3">
            <div className="h-6 w-1 rounded bg-[var(--accent)]/30" />
            <div>
              <div className="text-sm text-[var(--foreground)]">
                {r.label} <span className="text-[var(--muted)]">({Math.round(r.weight * 100)}%)</span>
              </div>
              <div className="text-xs text-[var(--muted)]">贡献 {r.contribution} 分</div>
            </div>
          </div>
          <div className="font-mono text-sm text-[var(--foreground)]">
            {r.score} × {Math.round(r.weight * 100)}% = {r.contribution}
          </div>
        </div>
      ))}
      {penalty > 0 && (
        <div className="flex items-center justify-between border-b border-[var(--border)]/30 py-2">
          <span className="text-sm text-[var(--danger)]">风险惩罚</span>
          <span className="font-mono text-sm text-[var(--danger)]">−{penalty}</span>
        </div>
      )}
      <div className="flex items-center justify-between py-2">
        <span className="text-sm font-bold text-[var(--muted)]">加权原始分</span>
        <span className="font-mono text-sm font-bold text-[var(--muted)]">{rawTotal}</span>
      </div>
      <div className="flex items-center justify-between border-t-2 border-[var(--accent)]/20 py-2">
        <span className="text-base font-extrabold text-[var(--foreground)]">综合分</span>
        <span className={`font-mono text-base font-extrabold ${scoreColor(final)}`}>{final}/100</span>
      </div>
      {capReason && <p className="text-xs text-[var(--muted)]">{capReason}</p>}
      {/* long_term_score 拆解 */}
      {(() => {
        const lts = Number(result.long_term_score ?? 0);
        const raw = Number(result.raw_long_term_score_before_penalty ?? 0);
        const pen = Number(result.long_term_penalty ?? 0);
        const penReasons = (result.long_term_penalty_reasons as string[] | undefined) ?? [];
        if (!lts) return null;
        return (
          <div className="mt-3 rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--muted)]">长期投资分</span>
              <span className="font-mono text-sm text-[var(--foreground)]">{lts}</span>
            </div>
            {raw > 0 && (
              <div className="mt-1 flex items-center justify-between text-xs text-[var(--muted)]">
                <span>原分 {raw} − 惩罚 {pen} = 最终 {lts}</span>
              </div>
            )}
            {penReasons.length > 0 && (
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[10px] text-[var(--muted)]">
                {penReasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })()}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 2. Score Reasons                                                   */
/* ------------------------------------------------------------------ */
export function ScoreReasons({ result }: { result: AnalysisResult }) {
  const reasons: string[] = [];
  const rec = result.subscription_recommendation || "";
  if (rec) reasons.push(`申购建议: ${rec}`);
  const raw = result as unknown as Record<string, unknown>;
  const recReasons = (raw.recommendation_reasons as string[] | undefined) || [];
  const scoreReasons = (raw.score_reasons as string[] | undefined) || [];
  reasons.push(...recReasons, ...scoreReasons);

  if (reasons.length === 0) return null;

  // 按情感分类排序：正面 -> 中性 -> 负面
  const grouped = {
    positive: reasons.filter((r) => analyzeReasonSentiment(r) === "positive"),
    neutral: reasons.filter((r) => analyzeReasonSentiment(r) === "neutral"),
    negative: reasons.filter((r) => analyzeReasonSentiment(r) === "negative"),
  };

  const groupLabels: Record<string, string> = {
    positive: "利好",
    neutral: "中性",
    negative: "风险",
  };

  const groupIconColors: Record<string, string> = {
    positive: "bg-[var(--success)]",
    neutral: "bg-[var(--muted)]",
    negative: "bg-[var(--danger)]",
  };

  return (
    <div className="space-y-3">
      {(Object.keys(grouped) as Array<keyof typeof grouped>).map((group) => {
        const items = grouped[group];
        if (items.length === 0) return null;
        return (
          <div key={group}>
            <div className="mb-1.5 flex items-center gap-2">
              <span className={`inline-block h-2 w-2 rounded-full ${groupIconColors[group]}`} />
              <span className="text-xs font-medium text-[var(--muted)]">
                {groupLabels[group]} ({items.length})
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {items.map((r, i) => (
                <span
                  key={`${group}-${i}`}
                  className={`inline-flex items-center rounded-full border px-3 py-1 text-xs transition hover:opacity-80 ${reasonStyle(group)}`}
                >
                  {r}
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 3. Diagnosis Panel                                                 */
/* ------------------------------------------------------------------ */
export function DiagnosisPanel({ result }: { result: AnalysisResult }) {
  const raw = result as unknown as Record<string, unknown>;
  const identityConf = String(raw.pdf_identity_confidence || "low");
  const finConf = String(result.financial_extract_confidence || "--");

  const items: [string, React.ReactNode][] = [
    ["PDF下载", raw.pdf_downloaded ? "✅ 成功" : "❌ 未下载"],
    ["PDF大小", `${fmtNum(raw.pdf_file_size_mb)} MB`],
    ["文本长度", `${fmtInt(raw.prospectus_text_length)} 字符`],
    [
      "身份确认",
      identityConf === "high" ? (
        <span className="text-[var(--success)]">✅ 高</span>
      ) : identityConf === "medium" ? (
        <span className="text-[var(--warning)]">⚠️ 中</span>
      ) : (
        <span className="text-[var(--danger)]">❌ 低</span>
      ),
    ],
    ["股票代码", raw.pdf_stock_code_match ? "✅ 匹配" : "❌ 未匹配"],
    [
      "财务置信度",
      finConf === "consolidated_statement" ? (
        <span className="text-[var(--success)]">🟢 财务主表已识别</span>
      ) : (
        <span className="text-[var(--muted)]">{finConf}</span>
      ),
    ],
  ];

  const extractedCn = String(raw.extracted_company_name || "");
  const extractedEn = String(raw.extracted_english_name || "");
  if (extractedCn) items.push(["PDF公司名", extractedCn]);
  if (extractedEn && extractedEn.length < 80) items.push(["PDF英文名", extractedEn]);

  return <KpiGrid items={items} />;
}

/* ------------------------------------------------------------------ */
/* 4. Info & Financials & Deep Analysis                               */
/* ------------------------------------------------------------------ */
export function InfoBasic({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info as Record<string, unknown> | undefined;
  const is18C = (pi?.is_chapter_18c ?? undefined) as boolean | undefined;
  const clawbackMax = (pi?.public_offer_clawback_max_pct ?? undefined) as number | undefined;

  const infoItems: [string, React.ReactNode][] = [
    ["招股期", `${String(pi?.apply_start_date || "--")} ~ ${String(pi?.apply_end_date || "--")}`],
    ["估值口径", pi?.valuation_price_basis === "final_price" ? "最终价" : "招股价"],
    ["发行价", fmtNum(pi?.offer_price, " HKD")],
    ["每手股数", String(pi?.lot_size || "--")],
    ["18C回拨", is18C && clawbackMax !== undefined ? `可回拨至${clawbackMax}%` : "--"],
    ["入场费", fmtNum(pi?.entry_fee_hkd, " HKD")],
    ["市值", fmtNum(pi?.market_cap_hkd_million, " M HKD")],
    ["发行比例", fmtPct(pi?.issuance_ratio_pct)],
    ["孖展资金", fmtNum(result.margin_total, " 亿")],
    ["超购倍数", fmtNum(result.over_sub_ratio, "x")],
    ["市场热度", String(result.market_heat || "--")],
    ["行业", String(pi?.sector || "--")],
  ];

  return <KpiGrid items={infoItems} />;
}

export function InfoFinancials({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info as Record<string, unknown> | undefined;
  const val = (pi?.valuation as Record<string, unknown> | undefined) || {};
  const biz = (pi?.business_breakdown as Record<string, unknown> | undefined) || {};
  const geo = (pi?.geographic as Record<string, unknown> | undefined) || {};

  const rev = (pi?.revenue ?? undefined) as number | undefined;
  const revY1 = (pi?.revenue_y1 ?? undefined) as number | undefined;
  const revStr =
    rev !== undefined && revY1 !== undefined && revY1 !== 0
      ? `${rev.toFixed(1)} M (${rev > revY1 ? "↑" : "↓"}${Math.abs(((rev - revY1) / Math.abs(revY1)) * 100).toFixed(1)}%)`
      : fmtNum(rev, " M");

  const np = (pi?.net_profit ?? undefined) as number | undefined;
  const npY1 = (pi?.net_profit_y1 ?? undefined) as number | undefined;
  const npStr =
    np !== undefined && npY1 !== undefined && npY1 !== 0
      ? `${np.toFixed(1)} M (${np > npY1 ? "↑" : "↓"}${Math.abs(((np - npY1) / Math.abs(npY1)) * 100).toFixed(1)}%)`
      : fmtNum(np, " M");

  const gm = (pi?.gross_margin ?? undefined) as number | undefined;
  const gmY1 = (pi?.gross_margin_y1 ?? undefined) as number | undefined;
  const gmStr =
    gm !== undefined && gmY1 !== undefined
      ? `${gm.toFixed(1)}% (${gm > gmY1 ? "↑" : "↓"}${Math.abs(gm - gmY1).toFixed(1)}%)`
      : fmtPct(gm);

  const peDisplay =
    val.valuation_profitability_type === "loss_making" || (val.pe_ratio === null && val.valuation_framework_type === "18A_biotech")
      ? "PE不适用"
      : fmtNum(val.pe_ratio, "x");

  const finItems: [string, React.ReactNode][] = [
    ["收入", revStr],
    ["净利润", npStr],
    ["毛利率", gmStr],
    ["PE", peDisplay],
    ["PS", fmtNum(val.ps_ratio, "x")],
    ["EV/Sales", fmtNum(val.ev_sales_ratio, "x")],
    ["最终价PS", fmtNum(val.final_ps_ratio ?? pi?.final_ps_ratio, "x")],
    ["PB", fmtNum(val.pb_ratio, "x")],
    ["研发费率", fmtPct((pi?.rnd_pipeline as Record<string, unknown> | undefined)?.rd_expense_ratio)],
    ["海外占比", fmtPct(geo.overseas_revenue_pct)],
    ["增长来源", String(biz.growth_source || "--")],
    ["业务模型", String(biz.business_model_label || "--")],
    ["海外扩张", String(geo.overseas_growth_label || "--")],
  ];

  return <KpiGrid items={finItems} />;
}

export function InfoDeep({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info as Record<string, unknown> | undefined;
  const val = (pi?.valuation as Record<string, unknown> | undefined) || {};
  const rnd = (pi?.rnd_pipeline as Record<string, unknown> | undefined) || {};
  const cs = (pi?.customer_supplier as Record<string, unknown> | undefined) || {};
  const cf = (pi?.cashflow as Record<string, unknown> | undefined) || {};
  const cap = (pi?.capacity as Record<string, unknown> | undefined) || {};
  const risk = (pi?.risk_factors as Record<string, unknown> | undefined) || {};
  const pc = (pi?.peer_comparison as Record<string, unknown> | undefined) || {};
  const sh = (pi?.shareholder as Record<string, unknown> | undefined) || {};

  // --- data_availability 读取辅助 ---
  const csAvail = (cs.data_availability as Record<string, unknown>) || {};
  const cfAvail = (cf.data_availability as Record<string, unknown>) || {};
  const rndAvail = (rnd.data_availability as Record<string, unknown>) || {};
  const capAvail = (cap.data_availability as Record<string, unknown>) || {};

  function getAvail(src: Record<string, unknown>, key: string): AvailabilityMeta | undefined {
    const raw = src[key];
    if (!raw) return undefined;
    if (typeof raw === "string") return { status: raw as AvailabilityMeta["status"] };
    if (typeof raw === "object") return raw as unknown as AvailabilityMeta;
    return undefined;
  }

  const ocf = (cf.ocf_to_revenue ?? undefined) as number | undefined;

  const detailItems: KpiItem[] = [
    ["客户集中度", String(cs.concentration_risk_label || "--"), getAvail(csAvail, "concentration_risk_label")],
    ["客户质量", cs.customer_quality_label === "缺失" ? "不适用" : `${String(cs.customer_quality_label || "--")} (${cs.customer_quality_score ?? 0}/100)`, getAvail(csAvail, "customer_quality_score")],
    ["客户留存率", fmtPct(cs.customer_retention_rate_pct), getAvail(csAvail, "customer_retention_rate_pct")],
    ["NDR", fmtPct(cs.net_dollar_retention_rate_pct), getAvail(csAvail, "net_dollar_retention_rate_pct")],
    ["Top5客户占比", fmtPct(cs.top5_customer_revenue_pct), getAvail(csAvail, "top5_customer_revenue_pct")],
    ["最大客户占比", fmtPct(cs.largest_customer_revenue_pct), getAvail(csAvail, "largest_customer_revenue_pct")],
    ["现金流质量", String(cf.cash_quality_label || "--"), getAvail(cfAvail, "cash_quality_label")],
    ["营运资本趋势", String(cf.working_capital_trend_label || "--"), getAvail(cfAvail, "working_capital_trend_label")],
    ["营运资本压力", String(cf.working_capital_pressure_label || "--"), getAvail(cfAvail, "working_capital_pressure_label")],
    ["OCF/收入", (() => {
      if (ocf === undefined || isNaN(ocf)) return "--";
      return (
        <span className={ocf < 0 ? "text-[var(--danger)]" : "text-[var(--success)]"}>
          {fmtPct(ocf * 100)}
        </span>
      );
    })(), getAvail(cfAvail, "ocf_to_revenue")],
    ["现金余额", fmtNum(cf.cash_and_cash_equivalents, " M"), getAvail(cfAvail, "cash_and_cash_equivalents")],
    ["月耗现金", fmtNum(cf.monthly_cash_burn, " M"), getAvail(cfAvail, "monthly_cash_burn")],
    ["库存金额", fmtNum(cf.inventory_amount, " M"), getAvail(cfAvail, "inventory_amount")],
    ["应收金额", fmtNum(cf.receivables_amount, " M"), getAvail(cfAvail, "receivables_amount")],
    ["募资后runway", cf.post_ipo_cash_runway_years != null ? `${cf.post_ipo_cash_runway_years}年` : "--", getAvail(cfAvail, "post_ipo_cash_runway_years")],
    ["技术壁垒", `${String(rnd.pipeline_quality_label || "--")} (${rnd.technology_moat_score ?? 0}/10)`, getAvail(rndAvail, "technology_moat_score")],
    ["硬科技护城河", rnd.hardtech_moat_label === "缺失" ? "不适用" : `${String(rnd.hardtech_moat_label || "--")} (${rnd.hardtech_moat_score ?? 0}/10)`, getAvail(rndAvail, "hardtech_moat_label")],
    ["专利/软著", (() => {
      const pCount = rnd.patent_count;
      const sCount = rnd.software_copyright_count;
      const pAvail = getAvail(rndAvail, "patent_count");
      const sAvail = getAvail(rndAvail, "software_copyright_count");
      const pDisplay = pCount != null ? pCount : (pAvail?.status === "not_found" ? "0*" : "--");
      const sDisplay = sCount != null ? sCount : (sAvail?.status === "not_found" ? "0*" : "--");
      return `${pDisplay} / ${sDisplay}`;
    })(), (() => {
      const pAvail = getAvail(rndAvail, "patent_count");
      const sAvail = getAvail(rndAvail, "software_copyright_count");
      if (pAvail?.status === "not_found" || sAvail?.status === "not_found") {
        return { status: "not_found" as const, reason: "招股书未检索到专利/软著披露，*表示按0处理" };
      }
      return pAvail || sAvail;
    })()],
    ["研发团队", (() => {
      const count = rnd.rd_staff_count;
      const ratio = rnd.rd_staff_ratio;
      const avail = getAvail(rndAvail, "rd_staff_count");
      if (count != null) return `${count}人 / ${fmtPct(ratio)}`;
      if (avail?.status === "not_found") return "未披露";
      return "--";
    })(), getAvail(rndAvail, "rd_staff_count")],
    ["在手订单", fmtNum(rnd.backlog_amount, " M"), getAvail(rndAvail, "backlog_amount")],
    ["行业排名", String(rnd.industry_rank || "--"), getAvail(rndAvail, "industry_rank")],
    ["产能利用率", fmtPct(cap.utilization_rate), getAvail(capAvail, "utilization_rate")],
    ["招股书风险因子", String((risk as Record<string, unknown>).total_penalty ?? 0)],
    ["估值框架", String(val.valuation_framework_label || val.valuation_framework_type || "--")],
    ["市值/R&D", fmtNum(val.market_cap_to_rd_ratio, "x")],
    ["IPO溢价", fmtPct(val.ipo_valuation_premium_pct)],
    ["现金runway", val.cash_runway_years != null ? `${val.cash_runway_years}年` : "--"],
    ["临床阶段", String(val.latest_clinical_stage || "--")],
  ];

  const riskItems = (risk.risks as Record<string, Record<string, unknown>> | undefined) || {};
  const riskChips = Object.entries(riskItems)
    .filter(([, data]) => Number(data.score_penalty ?? 0) > 0)
    .map(([cat, data]) => {
      const level = String(data.risk_level || "--");
      const penalty = Number(data.score_penalty ?? 0);
      const color = level === "高" ? "text-[var(--danger)]" : level === "中" ? "text-[var(--warning)]" : "text-[var(--muted)]";
      const label = cat.replace(/_risk/g, "").replace(/_/g, " ");
      return { label, level, penalty, color };
    });

  const evidenceSections: [string, string][] = [];
  const caExcerpt = ((pi?.cornerstone_analysis as Record<string, unknown> | undefined)?.source_excerpt as string) || "";
  const bizExcerpt = ((pi?.business_breakdown as Record<string, unknown> | undefined)?.evidence_excerpt as string) || "";
  const cfExcerpt = (cf.evidence_excerpt as string) || "";
  const rndExcerpt = (rnd.evidence_excerpt as string) || "";
  const valExcerpt = (val.evidence_excerpt as string) || "";
  if (caExcerpt) evidenceSections.push(["基石原文", caExcerpt]);
  if (bizExcerpt) evidenceSections.push(["业务分部", bizExcerpt]);
  if (cfExcerpt) evidenceSections.push(["营运资本", cfExcerpt]);
  if (rndExcerpt) evidenceSections.push(["研发护城河", rndExcerpt]);
  if (valExcerpt) evidenceSections.push(["估值口径", valExcerpt]);

  const biz = (pi?.business_breakdown as Record<string, unknown> | undefined) || {};

  return (
    <div className="flex flex-col gap-4">
      <KpiGrid items={detailItems} />
      {riskChips.length > 0 && (
        <>
          <SectionTitle title="⚠️ 风险明细" />
          <div className="flex flex-wrap gap-2">
            {riskChips.map((r, i) => (
              <span
                key={i}
                className={`inline-flex items-center rounded-md border border-[var(--danger)]/20 bg-[var(--danger)]/5 px-2.5 py-1 text-xs ${r.color}`}
              >
                {r.label} {r.level}(-{r.penalty})
              </span>
            ))}
          </div>
        </>
      )}
      {evidenceSections.length > 0 && (
        <>
          <SectionTitle title="📎 原文证据" />
          <div className="flex flex-col gap-2">
            {evidenceSections.map(([title, excerpt]) => (
              <details
                key={title}
                className="rounded-lg border border-[var(--border)] bg-[var(--surface-strong)] px-4 py-2.5"
              >
                <summary className="cursor-pointer text-xs font-semibold text-[var(--foreground)]">{title}</summary>
                <pre className="mt-2 max-h-[200px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-[var(--border)] bg-[#05070d] p-3 text-xs leading-relaxed text-[var(--foreground)]">
                  {excerpt}
                </pre>
              </details>
            ))}
          </div>
        </>
      )}
      {!!biz.business_breakdown_warning && (
        <p className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-2.5 text-xs text-[var(--warning)]">
          ⚠️ {String(biz.business_breakdown_warning)}
        </p>
      )}
      {Number(biz.vbp_risk_score ?? 0) > 0 && (
        <p className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-2.5 text-xs text-[var(--warning)]">
          ⚠️ 集采/VBP风险: {String(biz.vbp_summary || "")}
        </p>
      )}
      {!!val.revenue_too_small_for_ps && (
        <p className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-2.5 text-xs text-[var(--warning)]">
          ⚠️ 收入基数极小，PS严重失真，仅作参考，需结合管线/技术阶段/平台价值判断
        </p>
      )}
      {!!pc.peer_sample_warning && (
        <p className="rounded-lg border border-[var(--accent)]/20 bg-[var(--accent)]/5 p-2.5 text-xs text-[var(--accent)]">
          ℹ️ {String(pc.peer_sample_warning)}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 5. Business Segments                                               */
/* ------------------------------------------------------------------ */
export function BusinessSegments({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info as Record<string, unknown> | undefined;
  const biz = (pi?.business_breakdown as Record<string, unknown> | undefined) || {};
  const segments = (biz.segments as Record<string, unknown>[] | undefined) || [];
  const growthSource = String(biz.growth_source || "");
  const confidence = String(biz.business_breakdown_confidence || "");
  if (!segments.length && !biz.business_model_label) {
    const isPreRevenue = confidence === "missing" && growthSource === "missing";
    const displayText = isPreRevenue
      ? "该公司为尚未产生营业收入的生物科技公司（Pre-revenue），暂无业务分部数据"
      : "招股书中未找到业务分部数据";
    return (
      <div className="flex items-center justify-center py-6 text-sm text-[var(--muted)]">
        <p>{displayText}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2 text-xs text-[var(--muted)]">
        {!!biz.business_model_label && <span>业务模型：{String(biz.business_model_label)}</span>}
        {!!biz.segment_concentration_label && <span>· 结构：{String(biz.segment_concentration_label)}</span>}
        {!!biz.segment_moat_label && <span>· 主业属性：{String(biz.segment_moat_label)}</span>}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {segments.slice(0, 6).map((seg, i) => {
          const share = (seg.share_pct ?? undefined) as number | undefined;
          const growth = (seg.growth_pct ?? undefined) as number | undefined;
          return (
            <div key={i} className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
              <p className="text-xs text-[var(--muted)]">{String(seg.name || "--")}</p>
              <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">
                {share !== undefined ? `${share.toFixed(1)}%` : "--"}
              </p>
              {growth !== undefined && (
                <p className={`text-xs ${growth > 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
                  {growth > 0 ? "↑" : "↓"}{Math.abs(growth).toFixed(1)}%
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 6. Fisher / Lynch Long-term Lens                                   */
/* ------------------------------------------------------------------ */
export function FisherLynch({ result }: { result: AnalysisResult }) {
  const raw = result.prospectus_info as Record<string, unknown> | undefined;
  const sq = (raw?.stock_quality as Record<string, unknown> | undefined) || {};
  if (!sq) return null;

  const fisherLabel = String(sq.fisher_label || "--");
  const lynchLabel = String(sq.lynch_label || "--");
  const fisherReasons = (sq.fisher_reasons as string[] | undefined) || [];
  const lynchReasons = (sq.lynch_reasons as string[] | undefined) || [];
  const notes = String(sq.long_term_notes || "");

  if (fisherLabel === "--" && lynchLabel === "--" && !fisherReasons.length && !lynchReasons.length) return null;

  return (
    <div className="flex flex-col gap-4">
      <KpiGrid
        items={[
          ["Fisher 视角", <span key="f" className={fisherLabel === "适配" ? "text-[var(--success)]" : fisherLabel === "部分适配" ? "text-[var(--warning)]" : "text-[var(--muted)]"}>{fisherLabel}</span>],
          ["Lynch 视角", <span key="l" className={lynchLabel === "适配" ? "text-[var(--success)]" : lynchLabel === "部分适配" ? "text-[var(--warning)]" : "text-[var(--muted)]"}>{lynchLabel}</span>],
        ]}
      />
      <div className="grid gap-4 md:grid-cols-2">
        {fisherReasons.length > 0 && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
            <p className="text-xs font-bold text-[var(--foreground)]">Fisher 理由</p>
            <p className="mt-2 text-xs leading-relaxed text-[var(--muted)]">
              {fisherReasons.slice(0, 4).join("；")}
            </p>
          </div>
        )}
        {lynchReasons.length > 0 && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
            <p className="text-xs font-bold text-[var(--foreground)]">Lynch 理由</p>
            <p className="mt-2 text-xs leading-relaxed text-[var(--muted)]">
              {lynchReasons.slice(0, 4).join("；")}
            </p>
          </div>
        )}
      </div>
      {notes && <p className="text-xs text-[var(--muted)]">{notes}</p>}
    </div>
  );
}
