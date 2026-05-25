
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ipo_analyzer.core import reanalyze_ipo
import json

print("=" * 80)
print("丹诺医药 (06872) 长线评分详细分析")
print("=" * 80)

result = reanalyze_ipo(
    stock_code='06872',
    pdf_path='storage/06872_prospectus.pdf',
    force_refresh=True,
)

if result.get('status') in ('ok', 'warning'):
    full_result = result.get('result', {}).get('_full_result', result.get('result', {}))
    
    print("\n1. 整体评分概览")
    print("-" * 80)
    print(f"  最终综合评分: {full_result.get('final_score', 0)}")
    print(f"  打新交易评分: {full_result.get('ipo_trade_score', 0)}")
    print(f"  长线价值评分: {full_result.get('long_term_score', 0)}")
    print(f"  长线价值标签: {full_result.get('long_term_label', '')}")
    
    print("\n2. 长线评分详细计算 (score_trace)")
    print("-" * 80)
    score_trace = full_result.get('score_trace', {})
    if score_trace:
        print(f"  raw_weighted_score: {score_trace.get('raw_weighted_score', 0)}")
        print(f"  trade_score: {score_trace.get('trade_score', 0)}")
        print(f"  fundamental_score: {score_trace.get('fundamental_score', 0)}")
        print(f"  valuation_score: {score_trace.get('valuation_score', 0)}")
        print(f"  theme_score: {score_trace.get('theme_score', 0)}")
        print(f"  raw_long_term_score_before_penalty: {score_trace.get('raw_long_term_score_before_penalty', 0)}")
        print(f"  long_term_penalty: {score_trace.get('long_term_penalty', 0)}")
        print(f"  long_term_penalty_reasons: {score_trace.get('long_term_penalty_reasons', [])}")
        print(f"  weight_profile: {score_trace.get('weight_profile', {})}")
    
    print("\n3. Prospectus 信息")
    print("-" * 80)
    prospectus_info = full_result.get('prospectus_info', {})
    
    # 基本面质量
    stock_quality = prospectus_info.get('stock_quality', {})
    print(f"\n  3.1 基本面质量 (stock_quality)")
    print(f"    score: {stock_quality.get('score', 0)}")
    print(f"    label: {stock_quality.get('label', '')}")
    print(f"    reasons: {stock_quality.get('reasons', [])}")
    print(f"    fisher_label: {stock_quality.get('fisher_label', '')}")
    print(f"    lynch_label: {stock_quality.get('lynch_label', '')}")
    
    # 客户质量
    customer_supplier = prospectus_info.get('customer_supplier', {})
    print(f"\n  3.2 客户质量 (customer_supplier)")
    print(f"    customer_quality_score: {customer_supplier.get('customer_quality_score', 0)}")
    print(f"    customer_quality_label: {customer_supplier.get('customer_quality_label', '')}")
    
    # 现金流
    cashflow = prospectus_info.get('cashflow', {})
    print(f"\n  3.3 现金流 (cashflow)")
    print(f"    cash_quality_label: {cashflow.get('cash_quality_label', '')}")
    print(f"    cash_runway_years: {cashflow.get('cash_runway_years', '')}")
    print(f"    working_capital_risks: {cashflow.get('working_capital_risks', [])}")
    
    # 风险因素
    risk_factors = prospectus_info.get('risk_factors', {})
    print(f"\n  3.4 风险因素 (risk_factors)")
    print(f"    total_penalty: {risk_factors.get('total_penalty', 0)}")
    
    # 估值框架
    print(f"\n4. Signal Components")
    print("-" * 80)
    signal_components = full_result.get('signal_components', {})
    if signal_components:
        vf = signal_components.get('valuation_framework', {})
        print(f"  valuation_framework score: {vf.get('score', 0)}, max: {vf.get('max_score', 0)}")
        print(f"  valuation_framework label: {vf.get('label', '')}")
        print(f"  valuation_framework reasons: {vf.get('reasons', [])}")
    
    print("\n" + "=" * 80)
    print("原始数据 (JSON 片段)")
    print("=" * 80)
    # 输出关键部分的完整 JSON
    debug_output = {
        'long_term_score': full_result.get('long_term_score'),
        'long_term_label': full_result.get('long_term_label'),
        'score_trace': full_result.get('score_trace'),
        'prospectus_info': {
            'stock_quality': stock_quality,
            'customer_supplier': customer_supplier,
            'cashflow': cashflow,
            'risk_factors': risk_factors,
        },
    }
    print(json.dumps(debug_output, indent=2, ensure_ascii=False))
else:
    print(f"分析失败: {result}")

