import os
import re
import glob
import logging
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.enums import TA_CENTER

from .utils import _is_num, format_iso_date, _format_cornerstone_amount
from .settings import SETTINGS

logger = logging.getLogger(__name__)




def _get_chinese_font():
    """获取中文字体，跨平台搜索，保障中文正常显示"""
    # 精确路径候选（macOS / Windows / Linux）
    font_candidates = [
        ("PingFangTC-Regular", "/System/Library/Fonts/PingFang.ttc"),
        ("PingFangSC-Regular", "/System/Library/Fonts/PingFang.ttc"),
        ("SongtiTC-Regular", "/System/Library/Fonts/Songti.ttc"),
        ("SongtiSC-Regular", "/System/Library/Fonts/Songti.ttc"),
        ("HiraginoSansGB-W6", "/System/Library/Fonts/Hiragino Sans GB.ttc"),
        ("STHeitiTC-Medium", "/System/Library/Fonts/STHeiti Medium.ttc"),
        ("STHeitiSC-Medium", "/System/Library/Fonts/STHeiti Medium.ttc"),
        ("ArialUnicodeMS", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        ("ArialUnicodeMS", "/Library/Fonts/Arial Unicode.ttf"),
        ("NotoSansCJK-Regular", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        ("NotoSansCJK-Regular", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ("NotoSansCJKsc-Regular", "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf"),
        ("DroidSansFallback", "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
        ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
        ("MicrosoftYaHei", "C:/Windows/Fonts/msyh.ttc"),
        ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
    ]

    for font_name, font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                return font_name
            except Exception:
                continue

    # 模糊搜索：在常见字体目录下搜索中文字体文件
    search_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/Library/Fonts"),
    ]
    font_patterns = [
        "*noto*", "*Noto*", "*CJK*",
        "*chinese*", "*Chinese*", "*chinese*",
        "*wqy*", "*WQY*", "*wenquanyi*",
        "*uming*", "*ukai*", "*fangsong*",
        "*Songti*", "*PingFang*", "*Heiti*",
        "*simhei*", "*SimHei*", "*msyh*", "*simsun*",
        "*DroidSansFallback*",
    ]
    tried_names = set()
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for pattern in font_patterns:
            for font_path in glob.glob(os.path.join(search_dir, "**", pattern), recursive=True):
                if font_path.lower().endswith((".ttf", ".ttc", ".otf")):
                    font_name = os.path.splitext(os.path.basename(font_path))[0]
                    if font_name in tried_names:
                        continue
                    tried_names.add(font_name)
                    try:
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                        return font_name
                    except Exception:
                        continue

    logger.warning("未找到中文字体，PDF中文可能无法正常显示")
    return "Helvetica"


def export_pdf_report(results, output_file):
    """生成美观的PDF报告"""
    
    font_name = _get_chinese_font()
    
    doc = SimpleDocTemplate(
        output_file,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=48,
        bottomMargin=48,
        title="港股IPO申购分析报告",
        author="IPO Analyzer",
    )
    
    styles = getSampleStyleSheet()

    _C = {
        'navy': '#0f172a',
        'brand': '#1e3a5f',
        'brand_light': '#2d5a8e',
        'slate_50': '#f8fafc',
        'slate_100': '#f1f5f9',
        'slate_200': '#e2e8f0',
        'slate_300': '#cbd5e1',
        'slate_400': '#94a3b8',
        'slate_500': '#64748b',
        'slate_600': '#475569',
        'slate_700': '#334155',
        'slate_800': '#1e293b',
        'green': '#16a34a',
        'green_bg': '#f0fdf4',
        'green_light': '#dcfce7',
        'amber': '#d97706',
        'amber_bg': '#fffbeb',
        'red': '#dc2626',
        'red_bg': '#fef2f2',
        'teal': '#0f766e',
        'blue': '#2563eb',
        'purple': '#7c3aed',
        'orange': '#ea580c',
        'gold': '#a16207',
        'blue_light': '#93c5fd',
        'purple_bg': '#f0e7ff',
        'blue_bg': '#eff6ff',
        'yellow_bg': '#fefce8',
        'amber_bg2': '#fef3c7',
        'brown': '#92400e',
    }

    styles.add(ParagraphStyle(name="ReportTitle", fontName=font_name, fontSize=22, leading=28, textColor=colors.white, alignment=TA_CENTER, spaceAfter=4))
    styles.add(ParagraphStyle(name="ReportSubtitle", fontName=font_name, fontSize=10, leading=13, textColor=colors.HexColor(_C['blue_light']), alignment=TA_CENTER, spaceAfter=0))
    styles.add(ParagraphStyle(name="IPOTitle", fontName=font_name, fontSize=16, leading=20, textColor=colors.HexColor(_C['navy']), spaceBefore=0, spaceAfter=0))
    styles.add(ParagraphStyle(name="Label", fontName=font_name, fontSize=9, leading=12, textColor=colors.HexColor(_C['slate_500'])))
    styles.add(ParagraphStyle(name="Value", fontName=font_name, fontSize=9, leading=12, textColor=colors.HexColor(_C['navy'])))
    styles.add(ParagraphStyle(name="MutedValue", fontName=font_name, fontSize=8.5, leading=11, textColor=colors.HexColor(_C['slate_500'])))
    styles.add(ParagraphStyle(name="BulletPoint", fontName=font_name, fontSize=9, leading=12, leftIndent=12, textColor=colors.HexColor(_C['slate_700']), spaceAfter=2))
    styles.add(ParagraphStyle(name="Tiny", fontName=font_name, fontSize=7, leading=9, textColor=colors.HexColor(_C['slate_400'])))
    styles.add(ParagraphStyle(name="TableHeader", fontName=font_name, fontSize=8, leading=10, textColor=colors.white, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Score", fontName=font_name, fontSize=32, leading=38, textColor=colors.HexColor(_C['navy']), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Footer", fontName=font_name, fontSize=7.5, leading=10, textColor=colors.HexColor(_C['slate_400']), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="RecommendTag", fontName=font_name, fontSize=9, leading=12, alignment=TA_CENTER))

    pdf_cfg = SETTINGS.pdf_report

    def _score_color(score):
        if score >= pdf_cfg.score_excellent:
            return _C['green']
        if score >= pdf_cfg.score_good:
            return _C['amber']
        return _C['red']

    def _score_label(score):
        if score >= pdf_cfg.recommend_active:
            return "积极申购"
        if score >= pdf_cfg.recommend_neutral:
            return "中性试水"
        if score >= pdf_cfg.recommend_cautious:
            return "谨慎试水"
        return "建议跳过"

    def _progress_bar(score, width=80, height=6, bar_color=None):
        if bar_color is None:
            bar_color = _score_color(score)
        outer = Table(
            [[Paragraph("", styles["Value"])]],
            colWidths=[width], rowHeights=[height],
        )
        outer.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_C['slate_200'])),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        fill_width = max(1, width * min(score, 100) / 100)
        inner = Table(
            [[Paragraph("", styles["Value"])]],
            colWidths=[fill_width], rowHeights=[height],
        )
        inner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bar_color)),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        bar = Table([[inner, Paragraph("", styles["Value"])]], colWidths=[fill_width, width - fill_width], rowHeights=[height])
        bar.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(bar_color)),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(_C['slate_200'])),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return bar

    def _recommend_tag(recommendation, score):
        if recommendation in ("积极申购",):
            tag_color, tag_bg = _C['green'], _C['green_bg']
        elif recommendation in ("中性试水",):
            tag_color, tag_bg = _C['blue'], _C['blue_bg']
        elif recommendation in ("谨慎试水", "谨慎"):
            tag_color, tag_bg = _C['amber'], _C['amber_bg']
        else:
            tag_color, tag_bg = _C['red'], _C['red_bg']
        tag = Table(
            [[Paragraph(f"<font color='{tag_color}'><b>{recommendation}</b></font>", styles["RecommendTag"])]],
            colWidths=[72], rowHeights=[20],
        )
        tag.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tag_bg)),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(tag_color)),
        ]))
        return tag

    elements = []

    banner = Table([
        [Paragraph("<b>港股IPO申购分析报告</b>", styles["ReportTitle"])],
        [Paragraph(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  |  分析 {len(results)} 只新股  |  AiPO + HKEX", styles["ReportSubtitle"])],
    ], colWidths=[510])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_C['brand'])),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (0, 0), 22),
        ("BOTTOMPADDING", (-1, -1), (-1, -1), 16),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
    ]))
    elements.append(banner)
    elements.append(Spacer(1, 16))

    if results:
        def _fmt_shares_m(share_count):
            if share_count is None:
                return "--"
            return f"{share_count / 10000:.2f}"

        def _fmt_hkd_billion(value_million):
            if value_million is None:
                return "--"
            return f"HK${value_million / 100:.2f}亿"

        def _fmt_entry_fee(value_hkd):
            if value_hkd is None:
                return "--"
            return f"HK${value_hkd:,.2f}"

        def build_prospectus_basic_info_table(ipo):
            prospectus_info = ipo.get('prospectus_info', {}) or {}
            cornerstone_analysis = prospectus_info.get('cornerstone_analysis', {}) or {}
            margin_detail = ipo.get('margin_detail', {}) or {}

            sector_map = {'healthcare': '医疗保健', 'hardtech': '硬科技', 'consumer': '消费', 'unknown': '未明确'}
            sector_label = sector_map.get(prospectus_info.get('sector', 'unknown'), '未明确')

            offer_price = prospectus_info.get('offer_price') or prospectus_info.get('max_price') or ipo.get('max_price')
            indicative_offer_price = prospectus_info.get('indicative_offer_price')
            price_basis = "最终价" if prospectus_info.get('valuation_price_basis') == 'final_price' else "招股价"
            board_lot = prospectus_info.get('lot_size') or ipo.get('lot_size')
            entry_fee_hkd = prospectus_info.get('entry_fee_hkd')
            market_cap_million = prospectus_info.get('market_cap_hkd_million')
            net_proceeds_million = prospectus_info.get('net_proceeds_hkd_million')
            issuance_ratio_pct = prospectus_info.get('issuance_ratio_pct')
            public_offer_ratio_pct = prospectus_info.get('public_offer_ratio_pct')
            listing_date = prospectus_info.get('listing_date')
            prospectus_info.get('results_date')
            cornerstone_total_hkd = prospectus_info.get('cornerstone_investment_hkd_million')
            cornerstone_total_usd = prospectus_info.get('cornerstone_investment_usd_million')
            cornerstone_pct_text = cornerstone_analysis.get('cornerstone_pct')
            cornerstone_pct_table = prospectus_info.get('cornerstone_offer_ratio_pct')
            if _is_num(cornerstone_pct_text) and _is_num(cornerstone_pct_table) and abs(cornerstone_pct_text - cornerstone_pct_table) > 10:
                cornerstone_offer_ratio_pct = cornerstone_pct_text
            else:
                cornerstone_offer_ratio_pct = cornerstone_pct_table or cornerstone_analysis.get('cornerstone_pct')
            valuation = prospectus_info.get('valuation', {}) or {}
            cashflow = prospectus_info.get('cashflow', {}) or {}
            global_offer_shares = prospectus_info.get('global_offer_shares')
            hk_offer_shares = prospectus_info.get('hk_offer_shares')
            intl_offer_shares = prospectus_info.get('international_offer_shares')
            mechanism = margin_detail.get('offering_mechanism') or '--'
            if public_offer_ratio_pct is not None:
                mechanism = f"公开发售{public_offer_ratio_pct:.2f}%"
                if prospectus_info.get('is_chapter_18c') and prospectus_info.get('public_offer_clawback_max_pct'):
                    mechanism += f"（可回拨至{prospectus_info['public_offer_clawback_max_pct']:g}%）"

            gross_proceeds_million = None
            if _is_num(ipo.get('public_offer')):
                gross_proceeds_million = ipo.get('public_offer') * 100
            ipo_pre_valuation_million = None
            if market_cap_million is not None and gross_proceeds_million is not None:
                ipo_pre_valuation_million = max(0, market_cap_million - gross_proceeds_million)
            pe_ratio = valuation.get('adjusted_pe_ratio') or valuation.get('pe_ratio')
            ev_sales_ratio = valuation.get('ev_sales_ratio')
            ipo_valuation_premium_pct = valuation.get('ipo_valuation_premium_pct')

            global_offer_lots = None
            hk_offer_lots = None
            if _is_num(global_offer_shares) and _is_num(board_lot) and board_lot > 0:
                global_offer_lots = global_offer_shares / board_lot
            if _is_num(hk_offer_shares) and _is_num(board_lot) and board_lot > 0:
                hk_offer_lots = hk_offer_shares / board_lot
            hk_offer_lots_text = "--"
            if global_offer_lots is not None and hk_offer_lots is not None:
                hk_offer_lots_text = f"{global_offer_lots:,.0f}/{hk_offer_lots:,.0f}"
                clawback_pct = prospectus_info.get('public_offer_clawback_max_pct') if prospectus_info.get('is_chapter_18c') else None
                if _is_num(clawback_pct) and _is_num(global_offer_shares) and _is_num(board_lot) and board_lot > 0:
                    max_hk_lots = global_offer_shares * clawback_pct / 100 / board_lot
                    hk_offer_lots_text += f"（公开可至{max_hk_lots:,.0f}）"

            rows = []
            ts = []

            def add_section(title, bg_color):
                row_idx = len(rows)
                rows.append([Paragraph(f"<b>{title}</b>", styles["TableHeader"]), "", "", ""])
                ts.extend([
                    ("SPAN", (0, row_idx), (-1, row_idx)),
                    ("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor(bg_color)),
                    ("TEXTCOLOR", (0, row_idx), (-1, row_idx), colors.white),
                    ("ALIGN", (0, row_idx), (-1, row_idx), "CENTER"),
                    ("VALIGN", (0, row_idx), (-1, row_idx), "MIDDLE"),
                    ("TOPPADDING", (0, row_idx), (-1, row_idx), 5),
                    ("BOTTOMPADDING", (0, row_idx), (-1, row_idx), 5),
                ])

            def vp(value, color=_C['navy'], bold=False):
                t = value if isinstance(value, str) else str(value)
                if bold:
                    t = f"<b>{t}</b>"
                return Paragraph(f"<font color='{color}'>{t}</font>", styles["Value"])

            def add_pair(l_label, l_value, r_label, r_value, val_bg="#ffffff", l_color=_C['navy'], r_color=_C['navy'], l_bold=False, r_bold=False):
                row_idx = len(rows)
                rows.append([
                    Paragraph(f"<b>{l_label}</b>", styles["Label"]),
                    vp(l_value, l_color, l_bold),
                    Paragraph(f"<b>{r_label}</b>", styles["Label"]),
                    vp(r_value, r_color, r_bold),
                ])
                ts.extend([
                    ("BACKGROUND", (0, row_idx), (0, row_idx), colors.HexColor(_C['purple_bg'])),
                    ("BACKGROUND", (2, row_idx), (2, row_idx), colors.HexColor(_C['purple_bg'])),
                    ("BACKGROUND", (1, row_idx), (1, row_idx), colors.HexColor(val_bg)),
                    ("BACKGROUND", (3, row_idx), (3, row_idx), colors.HexColor(val_bg)),
                    ("VALIGN", (0, row_idx), (-1, row_idx), "MIDDLE"),
                    ("TOPPADDING", (0, row_idx), (-1, row_idx), 3),
                    ("BOTTOMPADDING", (0, row_idx), (-1, row_idx), 3),
                    ("LEFTPADDING", (0, row_idx), (-1, row_idx), 6),
                    ("RIGHTPADDING", (0, row_idx), (-1, row_idx), 6),
                ])

            add_section("发行信息", _C['brand'])
            add_pair("公司名称", ipo.get('company_name', '--'), "股票代码", f"{ipo.get('hk_code', '--')}.HK", _C['blue_bg'], l_bold=True)
            add_pair("所属行业", sector_label, "发行机制", mechanism, _C['blue_bg'])
            add_pair(price_basis, f"HK${offer_price:.2f}" if _is_num(offer_price) else "--", "原招股价", f"HK${indicative_offer_price:.2f}" if _is_num(indicative_offer_price) else "--", _C['green_light'], l_color=_C['red'], l_bold=True)
            add_pair("每手股数", f"{int(board_lot)}" if board_lot else "--", "入场费", _fmt_entry_fee(entry_fee_hkd), _C['green_light'], r_color=_C['red'], r_bold=True)
            add_pair("公开发售比例", f"{public_offer_ratio_pct:.2f}%" if public_offer_ratio_pct is not None else "--", "估值口径", price_basis, _C['green_light'])
            add_pair("全球发售(万股)", _fmt_shares_m(global_offer_shares), "公开发售(万股)", _fmt_shares_m(hk_offer_shares), _C['yellow_bg'])
            add_pair("国际发售(万股)", _fmt_shares_m(intl_offer_shares), "发售手数(全球/公开)", hk_offer_lots_text, _C['yellow_bg'])
            add_pair("招股日期", f"{format_iso_date(ipo.get('apply_start_date', ''))} ~ {format_iso_date(ipo.get('apply_end_date', ''))}", "预计上市", listing_date or "--", _C['amber_bg2'])

            add_section("估值与资金", _C['brown'])
            cornerstone_value = "--"
            if cornerstone_total_hkd is not None and cornerstone_offer_ratio_pct is not None:
                cornerstone_value = f"HK${cornerstone_total_hkd/100:.2f}亿({cornerstone_offer_ratio_pct:.2f}%)"
            elif cornerstone_total_usd is not None and cornerstone_offer_ratio_pct is not None:
                cornerstone_hkd = cornerstone_total_usd * SETTINGS.fx.usd_to_hkd_precise
                cornerstone_value = f"HK${cornerstone_hkd/100:.2f}亿({cornerstone_offer_ratio_pct:.2f}%)"
            add_pair("IPO前估值", _fmt_hkd_billion(ipo_pre_valuation_million), "总市值", _fmt_hkd_billion(market_cap_million), "#ffffff", l_color=_C['red'], r_color=_C['red'], l_bold=True, r_bold=True)
            add_pair("募集(公开)", _fmt_hkd_billion(gross_proceeds_million), "净募集", _fmt_hkd_billion(net_proceeds_million), _C['green_light'])
            add_pair("发行比例", f"{issuance_ratio_pct:.2f}%" if issuance_ratio_pct is not None else "--", "市盈率", f"{pe_ratio:.2f}x" if pe_ratio is not None else "--", "#ffffff")
            add_pair("EV/Sales", f"{ev_sales_ratio:.2f}x" if ev_sales_ratio is not None else "--", "IPO溢价", f"{ipo_valuation_premium_pct:.1f}%" if ipo_valuation_premium_pct is not None else "--", _C['blue_bg'])
            add_pair("营运资本趋势", cashflow.get("working_capital_trend_label") or "--", "现金流质量", cashflow.get("cash_quality_label") or "--", _C['blue_bg'])
            add_pair("基石投资", cornerstone_value, "基石占比", f"{cornerstone_offer_ratio_pct:.2f}%" if cornerstone_offer_ratio_pct is not None else "--", _C['blue_bg'])

            tbl = Table(rows, colWidths=[100, 150, 100, 150], hAlign="LEFT")
            tbl.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(_C['slate_300'])),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                *ts,
            ]))
            return tbl

        def build_signal_breakdown_table(ipo):
            """交易信号拆解表（替代旧版进阶框架表）"""
            signal_breakdown = ipo.get('signal_breakdown') or {}
            if not signal_breakdown:
                # 回退到旧结构（兼容缓存数据）
                prospectus_info = ipo.get('prospectus_info', {}) or {}
                advanced = prospectus_info.get('advanced_framework') or {}
                if not advanced:
                    return None
                signal_breakdown = advanced.get('signal_breakdown', {})
            if not signal_breakdown:
                return None

            def short_text(value, limit=68):
                text = str(value or '--')
                return text if len(text) <= limit else text[:limit - 3] + '...'

            # UI 展示名称映射
            items = [
                ('real_money', '资金热度', _C['red']),
                ('float_structure', '筹码弹性', _C['blue']),
                ('cornerstone_quality', '基石质量', _C['gold']),
                ('valuation_reading', '估值解释', _C['amber']),
                ('market_heat', '实时热度', _C['teal']),
                ('sector_flow', '板块资金流', _C['green']),
                ('sector_momentum', '板块动能', _C['blue']),
                ('sector_board', '板块指数', _C['navy']),
                ('theme_bonus', '主题催化', _C['purple']),
                ('liquidity_bonus', '港股通路径', _C['teal']),
                ('data_confidence', '数据置信度', _C['green']),
            ]

            rows = [[
                Paragraph("<b>交易信号拆解</b>", styles["TableHeader"]),
                Paragraph("<b>强度</b>", styles["TableHeader"]),
                Paragraph("<b>说明</b>", styles["TableHeader"]),
            ]]
            row_styles = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['brand'])),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ]

            for key, title, accent in items:
                item = signal_breakdown.get(key, {})
                strength = item.get('strength', '缺失')
                detail = short_text(item.get('detail', '--'))
                row_idx = len(rows)
                strength_color = _C['slate_600']
                if strength in ('强', '高'):
                    strength_color = _C['green']
                elif strength in ('中'):
                    strength_color = _C['amber']
                elif strength in ('弱', '低'):
                    strength_color = _C['red']
                rows.append([
                    Paragraph(f"<font color='{accent}'><b>{title}</b></font>", styles["Value"]),
                    Paragraph(f"<font color='{strength_color}'><b>{strength}</b></font>", styles["Value"]),
                    Paragraph(detail, styles["MutedValue"]),
                ])
                if item.get('red_flags'):
                    row_styles.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor(_C['red_bg'])))

            tbl = Table(rows, colWidths=[120, 80, 300], hAlign="LEFT", repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(_C['slate_300'])),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_C['slate_50'])]),
                *row_styles,
            ]))
            return tbl

        def build_overview_table(ipo):
            prospectus_info = ipo.get('prospectus_info', {}) or {}
            valuation = prospectus_info.get('valuation', {}) or {}
            cashflow = prospectus_info.get('cashflow', {}) or {}
            business_breakdown = prospectus_info.get('business_breakdown', {}) or {}
            rnd_pipeline = prospectus_info.get('rnd_pipeline', {}) or {}
            cornerstone_analysis = prospectus_info.get('cornerstone_analysis', {}) or {}
            live_heat = ipo.get('live_market_heat') or (ipo.get('signal_breakdown') or {}).get('market_heat') or {}

            def _text(value, limit=42):
                text = str(value if value is not None else '--')
                text = text if len(text) <= limit else text[:limit - 3] + '...'
                return xml_escape(text)

            rows = [
                [
                    Paragraph("<b>总览判断</b>", styles["TableHeader"]),
                    Paragraph("<b>关键标签</b>", styles["TableHeader"]),
                    Paragraph("<b>补充说明</b>", styles["TableHeader"]),
                ]
            ]
            key_labels = [
                valuation.get("valuation_label", "--"),
                cornerstone_analysis.get("label", "--"),
                cashflow.get("working_capital_trend_label", "--"),
                cashflow.get("working_capital_pressure_label", "--"),
                live_heat.get("sector_heat_label", "--"),
                live_heat.get("sector_board_label", "--"),
                live_heat.get("sector_momentum_label", "--"),
            ]
            notes = []
            if prospectus_info.get("is_chapter_18c") and _is_num(prospectus_info.get("public_offer_clawback_max_pct")):
                notes.append(f"18C可回拨至{prospectus_info['public_offer_clawback_max_pct']:g}%")
            elif prospectus_info.get("public_offer_ratio_pct") is not None:
                notes.append(f"公开发售{prospectus_info['public_offer_ratio_pct']:.1f}%")
            if business_breakdown.get("business_model_label"):
                notes.append(str(business_breakdown.get("business_model_label")))
            if rnd_pipeline.get("hardtech_moat_label"):
                notes.append(f"护城河{rnd_pipeline.get('hardtech_moat_label')}")
            if cashflow.get("working_capital_trend_reasons"):
                notes.append("；".join(cashflow.get("working_capital_trend_reasons", [])[:2]))
            if cashflow.get("working_capital_pressure_reasons"):
                notes.append("；".join(cashflow.get("working_capital_pressure_reasons", [])[:2]))
            if live_heat.get("sector_flow_label") and live_heat.get("sector_flow_label") != "缺失":
                notes.append(f"资金流{live_heat.get('sector_flow_label')}")
            if live_heat.get("sector_board_label") and live_heat.get("sector_board_label") != "缺失":
                notes.append(f"板块指数{live_heat.get('sector_board_label')}")

            rows.append([
                Paragraph(_text(ipo.get("subscription_recommendation") or "--", 18), styles["Value"]),
                Paragraph(_text(" · ".join(str(item) for item in key_labels if item and item != "缺失"), 80), styles["MutedValue"]),
                Paragraph(_text("；".join(notes) if notes else "--", 120), styles["MutedValue"]),
            ])

            tbl = Table(rows, colWidths=[84, 170, 266], hAlign="LEFT")
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['slate_100'])),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(_C['slate_200'])),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]))
            return tbl

        def build_evidence_section(ipo):
            prospectus_info = ipo.get('prospectus_info', {}) or {}
            cornerstone_analysis = prospectus_info.get('cornerstone_analysis', {}) or {}
            sections = []

            def _compact_text(value, limit):
                text = re.sub(r'\s+', ' ', str(value or '')).strip()
                if len(text) > limit:
                    text = text[:limit - 3] + '...'
                return xml_escape(text)

            cornerstone_excerpt = cornerstone_analysis.get('source_excerpt') or cornerstone_analysis.get('raw_pdf_excerpt') or ''
            if cornerstone_excerpt:
                sections.append(('基石原文', cornerstone_excerpt))

            business_excerpt = (prospectus_info.get('business_breakdown', {}) or {}).get('evidence_excerpt') or ''
            if business_excerpt:
                sections.append(('业务分部', business_excerpt))

            cashflow_excerpt = (prospectus_info.get('cashflow', {}) or {}).get('evidence_excerpt') or ''
            if cashflow_excerpt:
                sections.append(('营运资本', cashflow_excerpt))

            rnd_excerpt = (prospectus_info.get('rnd_pipeline', {}) or {}).get('evidence_excerpt') or ''
            if rnd_excerpt:
                sections.append(('研发护城河', rnd_excerpt))

            valuation_excerpt = (prospectus_info.get('valuation', {}) or {}).get('evidence_excerpt') or ''
            if valuation_excerpt:
                sections.append(('估值口径', valuation_excerpt))

            if not sections:
                return None

            rows = [
                [Paragraph("<b>证据来源</b>", styles["TableHeader"]), Paragraph("<b>原文摘录</b>", styles["TableHeader"])],
            ]
            for title, excerpt in sections[:5]:
                rows.append([
                    Paragraph(_compact_text(title, 24), styles["Value"]),
                    Paragraph(_compact_text(excerpt, 220), styles["MutedValue"]),
                ])

            tbl = Table(rows, colWidths=[88, 422], hAlign="LEFT", repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['brand'])),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(_C['slate_200'])),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_C['slate_50'])]),
            ]))
            return tbl

        def build_investment_thesis_section(ipo):
            prospectus_info = ipo.get('prospectus_info', {}) or {}
            thesis = ipo.get('investment_thesis') or prospectus_info.get('investment_thesis') or {}
            if not isinstance(thesis, dict) or not thesis:
                return None

            def _txt(value, limit=160):
                text = re.sub(r'\s+', ' ', str(value or '')).strip()
                if len(text) > limit:
                    text = text[:limit - 3] + '...'
                return xml_escape(text)

            tone = thesis.get('overall_tone') or '--'
            conclusion = thesis.get('one_line_conclusion') or thesis.get('conclusion') or '--'
            short_case = thesis.get('short_seller_case') or {}
            target = short_case.get('target_price_range_hkd') if isinstance(short_case, dict) else None
            target_text = '--'
            if isinstance(target, (list, tuple)) and len(target) >= 2 and all(_is_num(x) for x in target[:2]):
                target_text = f"HK${target[0]:.2f}-{target[1]:.2f}"

            rows = [
                [
                    Paragraph("<b>投研结论</b>", styles["TableHeader"]),
                    Paragraph("<b>一句话判断</b>", styles["TableHeader"]),
                    Paragraph("<b>做空重估区间</b>", styles["TableHeader"]),
                ],
                [
                    Paragraph(f"<b>{_txt(tone, 20)}</b>", styles["Value"]),
                    Paragraph(_txt(conclusion, 180), styles["Value"]),
                    Paragraph(_txt(target_text, 36), styles["Value"]),
                ],
            ]

            def _bullets(title, items, limit=3):
                if not items:
                    return None
                if isinstance(items, dict):
                    items = items.get('bear_points') or items.get('items') or []
                if not isinstance(items, list):
                    return None
                text = "<br/>".join(f"• {_txt(item, 96)}" for item in items[:limit])
                return [Paragraph(f"<b>{_txt(title, 16)}</b>", styles["Label"]), Paragraph(text or "--", styles["MutedValue"])]

            detail_rows = []
            for title, items in (
                ("基本面诊断", thesis.get('fundamental_diagnosis')),
                ("商业模式", thesis.get('business_model_takeaways')),
                ("估值要点", thesis.get('valuation_takeaways')),
                ("做空视角", short_case.get('bear_points') if isinstance(short_case, dict) else None),
                ("反证指标", thesis.get('invalidation_signals')),
            ):
                row = _bullets(title, items)
                if row:
                    detail_rows.append(row)

            table = Table(rows, colWidths=[80, 330, 100], hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['brand'])),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(_C['slate_200'])),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor(_C['blue_bg'])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))

            if not detail_rows:
                return table
            detail = Table(detail_rows[:5], colWidths=[78, 432], hAlign="LEFT")
            detail.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(_C['slate_200'])),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(_C['slate_50'])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            return Table([[table], [detail]], colWidths=[510], hAlign="LEFT")

        avg_score = sum(item.get('ipo_trade_score', item.get('trade_score', item.get('score', 0))) for item in results) / len(results)
        best_item = max(results, key=lambda item: item.get('ipo_trade_score', item.get('trade_score', item.get('score', 0))))
        prospectus_count = sum(1 for item in results if item.get('prospectus_info'))
        quality_count = sum(1 for item in results if item.get('stock_quality', {}).get('score', 0) >= 45)
        def _has_effective_cornerstone_v2(item):
            ca = item.get('prospectus_info', {}).get('cornerstone_analysis', {}) or {}
            if ca.get('cornerstone_investors') or ca.get('cornerstone_pct') is not None:
                return True
            return _is_num(ca.get('score')) and ca.get('score') > 0

        cornerstone_count = sum(1 for item in results if _has_effective_cornerstone_v2(item))

        def metric_card(title, value, accent=_C['brand']):
            card = Table([
                [Paragraph(f"<font size='8' color='{_C['slate_500']}'>{title}</font>", styles["MutedValue"])],
                [Paragraph(f"<font size='20' color='{accent}'><b>{value}</b></font>", styles["Value"])],
            ], colWidths=[96])
            card.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEABOVE", (0, 0), (-1, 0), 2.5, colors.HexColor(accent)),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            return card

        best_trade_score = best_item.get('ipo_trade_score', best_item.get('trade_score', best_item.get('score', 0)))
        summary = Table([[
            metric_card("平均打新分", f"{avg_score:.0f}", _score_color(avg_score)),
            metric_card("最高打新分", f"{best_trade_score}", _score_color(best_trade_score)),
            metric_card("招股书解析", f"{prospectus_count}", _C['teal']),
            metric_card("质地达标", f"{quality_count}", _C['blue']),
            metric_card("基石V2", f"{cornerstone_count}", _C['gold']),
        ]], colWidths=[98, 98, 98, 98, 98], hAlign="LEFT")
        summary.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_C['slate_50'])),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(_C['slate_200'])),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(summary)
        elements.append(Spacer(1, 16))

        overview_data = [[
            Paragraph(f"<b>{'排名'}</b>", styles["Label"]),
            Paragraph(f"<b>{'公司'}</b>", styles["Label"]),
            Paragraph(f"<b>{'代码'}</b>", styles["Label"]),
            Paragraph(f"<b>{'打新/长期'}</b>", styles["Label"]),
            Paragraph(f"<b>{'申购判断'}</b>", styles["Label"]),
            Paragraph(f"<b>{'超购倍数'}</b>", styles["Label"]),
            Paragraph(f"<b>{'基石/质地'}</b>", styles["Label"]),
        ]]

        for idx, ipo in enumerate(results, 1):
            total_score = ipo.get('ipo_trade_score', ipo.get('trade_score', ipo.get('score', 0)))
            long_score = ipo.get('long_term_score', ipo.get('fundamental_score', 0))
            cornerstone_analysis = ipo.get('prospectus_info', {}).get('cornerstone_analysis', {}) or {}
            recommendation = ipo.get('subscription_recommendation') or cornerstone_analysis.get('recommendation')
            if not recommendation:
                recommendation = _score_label(total_score)
            over_sub = ipo.get('actual_over_sub_ratio') or ipo.get('forecast_over_sub_ratio') or ipo.get('over_sub_ratio')
            over_text = f"{float(over_sub):.1f}x" if _is_num(over_sub) else "--"
            cornerstone_label = cornerstone_analysis.get('label', '--')
            cornerstone_band = cornerstone_analysis.get('grade_band') or cornerstone_label
            cornerstone_score = cornerstone_analysis.get('score')
            if _is_num(cornerstone_score):
                cornerstone_text = f"{cornerstone_band} {cornerstone_score}/100"
            else:
                cornerstone_text = cornerstone_band
            quality_label = ipo.get('stock_quality', {}).get('label', '--')
            quality_score = ipo.get('stock_quality', {}).get('score', 0)

            sc = _score_color(total_score)
            overview_data.append([
                Paragraph(str(idx), styles["Value"]),
                Paragraph(ipo.get('company_name', ''), styles["Value"]),
                Paragraph(ipo.get('hk_code', ''), styles["Value"]),
                Paragraph(f"<font color='{sc}'><b>{total_score}</b></font><br/><font size='7' color='{_C['slate_400']}'>长 {long_score}</font>", styles["Value"]),
                _recommend_tag(recommendation, total_score),
                Paragraph(over_text, styles["Value"]),
                Paragraph(f"{cornerstone_text}<br/><font size='7' color='{_C['slate_400']}'>质地{quality_label} {quality_score}分</font>", styles["Value"]),
            ])

        overview = Table(overview_data, colWidths=[26, 82, 40, 36, 78, 60, 172], repeatRows=1, hAlign="LEFT")
        overview.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['brand'])),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("LEADING", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_C['slate_50'])]),
        ]))
        elements.append(overview)
        elements.append(Spacer(1, 16))

    for idx, ipo in enumerate(results):
        ipo_elements = []

        company_name = ipo.get('company_name', 'N/A')
        hk_code = ipo.get('hk_code', 'N/A')
        total_score = ipo.get('ipo_trade_score', ipo.get('trade_score', ipo.get('score', 0)))
        long_score = ipo.get('long_term_score', ipo.get('fundamental_score', 0))
        recommendation = ipo.get('subscription_recommendation') or _score_label(total_score)
        sc = _score_color(total_score)

        header_data = [
            [
                Paragraph(f"<b>{company_name}</b><br/><font size=9 color='{_C['slate_500']}'>HKEX {hk_code}</font>", styles["IPOTitle"]),
                Paragraph(f"<font size='32' color='{sc}'><b>{total_score}</b></font><br/><font size='8' color='{_C['slate_500']}'>长期 {long_score}/100</font>", styles["Score"]),
            ],
            [
                Paragraph("", styles["Value"]),
                _progress_bar(total_score, width=120, height=5, bar_color=sc),
            ],
            [
                _recommend_tag(recommendation, total_score),
                Paragraph(f"<font size=7.5 color='{_C['slate_400']}'>打新交易分</font>", styles["MutedValue"]),
            ],
        ]
        header = Table(header_data, colWidths=[340, 160])
        header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_C['slate_50'])),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(_C['slate_200'])),
            ("LINEBELOW", (0, 0), (-1, 0), 0.3, colors.HexColor(_C['slate_200'])),
            ("VALIGN", (0, 0), (0, -1), "MIDDLE"),
            ("VALIGN", (1, 0), (1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ]))
        ipo_elements.append(header)
        ipo_elements.append(Spacer(1, 10))

        # 发行信息 / 估值与资金表（放在评分卡之前）
        prospectus_info_table = build_prospectus_basic_info_table(ipo)
        ipo_elements.append(prospectus_info_table)
        ipo_elements.append(Spacer(1, 10))

        thesis_section = build_investment_thesis_section(ipo)
        if thesis_section:
            ipo_elements.append(thesis_section)
            ipo_elements.append(Spacer(1, 10))

        signal_breakdown_table = build_signal_breakdown_table(ipo)
        if signal_breakdown_table:
            ipo_elements.append(signal_breakdown_table)
            ipo_elements.append(Spacer(1, 10))

        overview_table = build_overview_table(ipo)
        if overview_table:
            ipo_elements.append(overview_table)
            ipo_elements.append(Spacer(1, 10))

        evidence_section = build_evidence_section(ipo)
        if evidence_section:
            ipo_elements.append(Paragraph("<b>原文证据</b>", styles["Label"]))
            ipo_elements.append(Spacer(1, 4))
            ipo_elements.append(evidence_section)
            ipo_elements.append(Spacer(1, 10))

        # --- waterfall 得分拆解 ---
        wp = ipo.get('weight_profile', {}) or {}
        weights = wp.get('weights', {})
        if weights:
            waterfall_rows = [
                [Paragraph("<b>维度</b>", styles["Label"]),
                 Paragraph("<b>原始分</b>", styles["Label"]),
                 Paragraph("<b>权重</b>", styles["Label"]),
                 Paragraph("<b>贡献</b>", styles["Label"])],
            ]
            wf_items = [
                ("交易面", ipo.get('trade_score', 0), weights.get('trade', 0)),
                ("基本面", ipo.get('fundamental_score', 0), weights.get('fundamental', 0)),
                ("估值面", ipo.get('valuation_score', 0), weights.get('valuation', 0)),
                ("主题面", ipo.get('theme_score', 0), weights.get('theme', 0)),
            ]
            raw_total = 0
            for title, score, weight in wf_items:
                contrib = round(score * weight)
                raw_total += contrib
                waterfall_rows.append([
                    Paragraph(title, styles["Value"]),
                    Paragraph(str(score), styles["Value"]),
                    Paragraph(f"{weight:.0%}", styles["Value"]),
                    Paragraph(str(contrib), styles["Value"]),
                ])
            penalty = ipo.get('risk_penalty', 0)
            if penalty > 0:
                waterfall_rows.append([
                    Paragraph("<font color='{_C['red']}'><b>风险惩罚</b></font>", styles["Value"]),
                    Paragraph("", styles["Value"]),
                    Paragraph("", styles["Value"]),
                    Paragraph(f"<font color='{_C['red']}'><b>-{penalty}</b></font>", styles["Value"]),
                ])
            final_score = ipo.get('score', 0)
            waterfall_rows.append([
                Paragraph("<b>旧综合分</b>", styles["Label"]),
                Paragraph("", styles["Label"]),
                Paragraph("", styles["Label"]),
                Paragraph(f"<font color='{_score_color(final_score)}'><b>{final_score}</b></font>", styles["Label"]),
            ])
            wf_tbl = Table(waterfall_rows, colWidths=[120, 60, 60, 60], hAlign="LEFT")
            wf_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['brand'])),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor(_C['navy'])),
            ]))
            ipo_elements.append(wf_tbl)
            ipo_elements.append(Spacer(1, 10))

        breakdown = ipo.get('score_breakdown', {})
        if breakdown:
            def _compact_detail(detail):
                """Shorten verbose detail to fit PDF card width (<= 2 lines)."""
                # "预测超购 399.34 倍，较实际变化 34.0%" -> "超购 399x | 较实际 +34.0%"
                m = re.match(r'预测超购 ([\d.]+) 倍，较(\S+)变化 ([\d.\-]+)%', detail)
                if m:
                    val, base, pct = m.groups()
                    sign = '+' if float(pct) >= 0 else ''
                    return f"超购 {val}x | 较{base} {sign}{pct}%"
                # Truncate overly long detail to ~2 lines at card width
                if len(detail) > 35:
                    return detail[:32] + '...'
                return detail

            def component_cell(title, component, accent):
                score = component.get('score', 0)
                label = component.get('label', '--')
                detail = _compact_detail(component.get('detail', ''))
                cell_rows = [
                    [Paragraph(f"<font size='8.5' color='{accent}'><b>{title}</b></font>", styles["Value"])],
                    [Paragraph(f"<font size='16' color='{_C['navy']}'><b>{score}</b></font><font size='7' color='{_C['slate_400']}'>  /100</font>", styles["Value"])],
                    [_progress_bar(score, width=130, height=4, bar_color=accent)],
                    [Paragraph(f"<font size='7.5' color='{_C['slate_600']}'>{label}</font>", styles["MutedValue"])],
                    [Paragraph(f"<font size='6.5' color='{_C['slate_400']}'>{detail or ' '}</font>", styles["Tiny"])],
                ]
                cell = Table(cell_rows, colWidths=[152])
                cell.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("LINEABOVE", (0, 0), (-1, 0), 2.5, colors.HexColor(accent)),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]))
                return cell

            # 2x2 layout: 热度/质地 + 规模/基石
            bd = Table([
                [
                    component_cell("热度", breakdown.get('heat', {}), _C['red']),
                    component_cell("质地", breakdown.get('quality', {}), _C['teal']),
                ],
                [
                    component_cell("规模", breakdown.get('scale', {}), _C['blue']),
                    component_cell("基石", breakdown.get('cornerstone', {}), _C['gold']),
                ],
            ], colWidths=[247, 247], hAlign="LEFT")
            bd.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_C['slate_50'])),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(_C['slate_200'])),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            # Suppress visible borders on the empty bottom-right filler cell
            bd.setStyle(TableStyle([
                ("BOX", (2, 1), (2, 1), 0, colors.white),
                ("INNERGRID", (2, 1), (2, 1), 0, colors.white),
                ("LINEBELOW", (2, 1), (2, 1), 0, colors.white),
                ("LINEAFTER", (2, 1), (2, 1), 0, colors.white),
            ]))
            ipo_elements.append(bd)
            ipo_elements.append(Spacer(1, 10))

        score_quality = ipo.get('stock_quality', {})
        dimensions = score_quality.get('dimensions', {}) if score_quality else {}
        if dimensions:
            dim_labels = {'growth': '成长性', 'profitability': '盈利质量', 'valuation': '估值压力', 'risk': '风险点'}
            dim_colors = {'growth': _C['green'], 'profitability': _C['blue'], 'valuation': _C['amber'], 'risk': _C['red']}
            dim_data = [[
                Paragraph("<b>维度</b>", styles["Label"]),
                Paragraph("<b>结论</b>", styles["Label"]),
                Paragraph("<b>说明</b>", styles["Label"]),
            ]]
            for key in ['growth', 'profitability', 'valuation', 'risk']:
                item = dimensions.get(key)
                if not item:
                    continue
                label_text = item.get('label', '--')
                label_color = dim_colors.get(key, _C['navy'])
                dim_data.append([
                    Paragraph(f"<font color='{label_color}'><b>{dim_labels.get(key, key)}</b></font>", styles["Value"]),
                    Paragraph(f"<font color='{label_color}'><b>{label_text}</b></font>", styles["Value"]),
                    Paragraph(item.get('detail', '--'), styles["MutedValue"]),
                ])
            dim_tbl = Table(dim_data, colWidths=[65, 80, 355], hAlign="LEFT")
            dim_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['slate_100'])),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(_C['slate_200'])),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_C['slate_50'])]),
            ]))
            ipo_elements.append(dim_tbl)
            ipo_elements.append(Spacer(1, 10))

        # ---- 同行对比 ----
        peer_comparison = ipo.get('prospectus_info', {}).get('peer_comparison', {}) or {}
        if peer_comparison.get('subsector') and peer_comparison.get('matched_peers'):
            pc_rows = [[
                Paragraph("<b>同行对比</b>", styles["TableHeader"]),
                Paragraph(f"<b>{peer_comparison.get('subsector', '').replace('_', ' / ')}</b>", styles["TableHeader"]),
                Paragraph(f"<b>评分 {peer_comparison.get('peer_score', 0)}/15</b>", styles["TableHeader"]),
            ]]
            pc_styles = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['brand'])),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ]

            # 估值对比行
            def _compact_detail(detail, limit=55):
                text = str(detail or '')
                return text if len(text) <= limit else text[:limit - 3] + '...'

            company_ps = peer_comparison.get('company_ps')
            peer_ps = peer_comparison.get('peer_median_ps')
            premium = peer_comparison.get('relative_ps_premium_pct')
            scarcity = peer_comparison.get('scarcity_score', 0)
            position = peer_comparison.get('valuation_position', '--')
            summary = peer_comparison.get('summary', '')

            ps_detail = f"PS {company_ps:.1f}x" if company_ps else "PS --"
            if peer_ps:
                ps_detail += f" vs 同行 {peer_ps:.1f}x"
            if premium is not None:
                ps_detail += f" ({premium:+.0f}%)"
            if scarcity:
                ps_detail += f" | 稀缺 {scarcity}/10"
            pc_rows.append([
                Paragraph("<b>估值定位</b>", styles["Value"]),
                Paragraph(position, styles["Value"]),
                Paragraph(_compact_detail(ps_detail), styles["MutedValue"]),
            ])

            # 同行列表（最多5家）
            peers_short = peer_comparison.get('matched_peers', [])[:5]
            for p in peers_short:
                p_name = p.get('name', '')
                p_ticker = p.get('ticker', '')
                p_type = p.get('type', '')
                p_ps = f"PS {p.get('ps'):.1f}x" if p.get('ps') else '--'
                p_pe = f"PE {p.get('pe'):.1f}x" if p.get('pe') else '--'
                p_gm = f"毛利率{p.get('gross_margin_pct'):.0f}%" if p.get('gross_margin_pct') else ''
                p_gr = f"增长{p.get('revenue_growth_pct'):.0f}%" if p.get('revenue_growth_pct') else ''
                p_detail = f"{p_ps} {p_pe} {p_gm} {p_gr}"
                type_tag = "(上市)" if p_type == 'listed' else "(未上市)"
                pc_rows.append([
                    Paragraph(f"{p_name} {type_tag}", styles["Value"]),
                    Paragraph(p_ticker, styles["MutedValue"]),
                    Paragraph(_compact_detail(p_detail), styles["MutedValue"]),
                ])

            # 警告
            for w in peer_comparison.get('warnings', []):
                pc_rows.append([
                    Paragraph(f"<font color='{_C['red']}'><b>[!]</b></font>", styles["Value"]),
                    Paragraph(f"<font color='{_C['red']}'>注意</font>", styles["Value"]),
                    Paragraph(f"<font color='{_C['slate_600']}'>{_compact_detail(w, 70)}</font>", styles["MutedValue"]),
                ])

            if summary:
                pc_rows.append([
                    Paragraph("<b>小结</b>", styles["Value"]),
                    Paragraph("", styles["Value"]),
                    Paragraph(_compact_detail(summary, 80), styles["MutedValue"]),
                ])

            # 潜在需人工核查的同行（仅非空时展示）
            unmatched = peer_comparison.get("unmatched_peer_candidates", [])
            if unmatched:
                names_str = "、".join(unmatched[:6])
                pc_rows.append([
                    Paragraph("<b>候选核查</b>", styles["Value"]),
                    Paragraph("人工", styles["MutedValue"]),
                    Paragraph(f"招股书竞争章节疑似提及但未收录: {_compact_detail(names_str, 70)}",
                              styles["MutedValue"]),
                ])

            pc_tbl = Table(pc_rows, colWidths=[82, 90, 328], hAlign="LEFT", repeatRows=1)
            pc_tbl.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(_C['slate_300'])),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_C['slate_50'])]),
                *pc_styles,
            ]))
            ipo_elements.append(pc_tbl)
            ipo_elements.append(Spacer(1, 10))

        cornerstone_analysis = ipo.get('prospectus_info', {}).get('cornerstone_analysis', {})

        if cornerstone_analysis:
            cornerstone_rows = cornerstone_analysis.get('cornerstone_investors', [])

            def _pdf_text(value, limit=None):
                text = str(value if value is not None else '--')
                text = text if limit is None or len(text) <= limit else text[:limit - 3] + '...'
                return xml_escape(text)

            def _dim_line(dim_key):
                dim = (cornerstone_analysis.get('dimension_scores') or {}).get(dim_key) or {}
                if not dim:
                    return "--"
                return f"{dim.get('label', dim_key)} {dim.get('score', 0)}/{dim.get('max_score', 0)}"

            combo = cornerstone_analysis.get('combination_summary') or '--'
            band = cornerstone_analysis.get('grade_band') or cornerstone_analysis.get('label', '--')
            pct = cornerstone_analysis.get('cornerstone_pct')
            pct_text = f"{pct:.1f}%" if pct is not None else "--"
            summary_rows = [
                [
                    Paragraph("<b>基石V2总评</b>", styles["TableHeader"]),
                    Paragraph(f"<b>{_pdf_text(cornerstone_analysis.get('label', '--'))} / {_pdf_text(band)}</b>", styles["TableHeader"]),
                    Paragraph(f"<b>{cornerstone_analysis.get('score', 0)}/100</b>", styles["TableHeader"]),
                ],
                [
                    Paragraph("组合画像", styles["Label"]),
                    Paragraph(_pdf_text(combo, 92), styles["MutedValue"]),
                    Paragraph(f"占比 {pct_text}", styles["Value"]),
                ],
                [
                    Paragraph("五维评分", styles["Label"]),
                    Paragraph(_pdf_text("；".join([
                        _dim_line('institution_quality'),
                        _dim_line('independence'),
                        _dim_line('sector_fit'),
                        _dim_line('subscription_strength'),
                        _dim_line('lockup_history'),
                    ]), 110), styles["MutedValue"]),
                    Paragraph(_pdf_text(cornerstone_analysis.get('recommendation', '--'), 18), styles["Value"]),
                ],
            ]
            summary_tbl = Table(summary_rows, colWidths=[78, 320, 80], hAlign="LEFT")
            summary_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['gold'])),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(_C['slate_200'])),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]))
            ipo_elements.append(summary_tbl)
            ipo_elements.append(Spacer(1, 6))

            if cornerstone_rows:
                cs_data = [[
                    Paragraph("<b>投资者</b>", styles["TableHeader"]),
                    Paragraph("<b>分级/类别</b>", styles["TableHeader"]),
                    Paragraph("<b>占比/金额</b>", styles["TableHeader"]),
                    Paragraph("<b>作用与判断</b>", styles["TableHeader"]),
                ]]
                row_styles = []
                tier_order = {'S': 0, 'A': 1, 'B': 2, '弱': 3, None: 4}
                rows_for_pdf = sorted(
                    cornerstone_rows,
                    key=lambda item: (tier_order.get(item.get('tier'), 4), -(item.get('offer_shares_pct') or 0)),
                )[:8]
                for row_idx, row in enumerate(rows_for_pdf, start=1):
                    row_name = row.get('name', '--')
                    tier = row.get('tier')
                    category = row.get('category', '未知')
                    role_note = row.get('role_note') or row.get('match_note') or '--'
                    fit = row.get('sector_fit_label') or '--'
                    offer_pct = f"{row.get('offer_shares_pct'):.2f}%" if row.get('offer_shares_pct') is not None else "--"
                    amount = _format_cornerstone_amount(row)
                    investor_name = row.get('short_name') or row_name
                    if investor_name != row_name:
                        investor_cell = f"<b>{_pdf_text(investor_name)}</b><br/><font size='6.5' color='{_C['slate_400']}'>{_pdf_text(row_name, 45)}</font>"
                    else:
                        investor_cell = f"<b>{_pdf_text(investor_name)}</b>"
                    cs_data.append([
                        Paragraph(investor_cell, styles["Value"]),
                        Paragraph(f"<b>{_pdf_text(tier or '未知')}</b><br/><font size='6.5' color='{_C['slate_500']}'>{_pdf_text(category, 28)}</font>", styles["Value"]),
                        Paragraph(f"{offer_pct}<br/><font size='6.5' color='{_C['slate_500']}'>{_pdf_text(amount, 24)}</font>", styles["Value"]),
                        Paragraph(f"{_pdf_text(role_note, 58)}<br/><font size='6.5' color='{_C['slate_400']}'>{_pdf_text(fit, 24)}</font>", styles["MutedValue"]),
                    ])
                    if tier in ('S', 'A'):
                        row_styles.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor(_C['green_bg'])))
                    elif tier == 'B':
                        row_styles.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor(_C['amber_bg'])))

                cs_tbl = Table(cs_data, colWidths=[130, 82, 78, 188], repeatRows=1, hAlign="LEFT")
                cs_tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['brand'])),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(_C['slate_200'])),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(_C['slate_200'])),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_C['slate_50'])]),
                    *row_styles,
                ]))
                ipo_elements.append(cs_tbl)
            matched_investors = cornerstone_analysis.get('matched_investors')
            if matched_investors:
                for item in matched_investors:
                    ipo_elements.append(Paragraph(f"- {item.get('name', 'N/A')} ({item.get('tier', 'N/A')})", styles["BulletPoint"]))

            for reason in cornerstone_analysis.get('strengths', [])[:3]:
                ipo_elements.append(Paragraph(f"<font color='{_C['green']}'><b>亮点</b></font> {_pdf_text(reason, 88)}", styles["BulletPoint"]))
            for concern in cornerstone_analysis.get('concerns', [])[:3]:
                ipo_elements.append(Paragraph(f"<font color='{_C['amber']}'><b>隐忧</b></font> {_pdf_text(concern, 88)}", styles["BulletPoint"]))
            for red_flag in cornerstone_analysis.get('red_flags', []):
                ipo_elements.append(Paragraph(f"<font color='{_C['red']}'><b>[!] {_pdf_text(red_flag, 88)}</b></font>", styles["BulletPoint"]))
            ipo_elements.append(Spacer(1, 10))

        reasons = ipo.get('score_reasons', [])
        if reasons:
            reason_data = [[Paragraph("<b>评分理由</b>", styles["Label"])]]
            for reason in reasons:
                reason_data.append([Paragraph(f"  {reason}", styles["BulletPoint"])])
            reason_tbl = Table(reason_data, colWidths=[500], hAlign="LEFT")
            reason_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C['slate_100'])),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(_C['slate_200'])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]))
            ipo_elements.append(reason_tbl)

        sep = Table([[Paragraph("", styles["Value"])]], colWidths=[510])
        sep.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.5, colors.HexColor(_C['brand'])),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        ipo_elements.append(Spacer(1, 10))
        ipo_elements.append(sep)

        for e in ipo_elements:
            elements.append(e)

        if idx < len(results) - 1:
            elements.append(Spacer(1, 14))

    elements.append(Spacer(1, 24))
    footer_line = Table([[Paragraph("", styles["Value"])]], colWidths=[510])
    footer_line.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.HexColor(_C['slate_300'])),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(footer_line)
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(f"报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  港股IPO申购分析系统", styles["Footer"]))

    def add_page_decoration(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor(_C['brand']))
        canvas.setLineWidth(0.5)
        canvas.line(42, A4[1] - 40, A4[0] - 42, A4[1] - 40)
        canvas.setFillColor(colors.HexColor(_C['slate_400']))
        canvas.setFont(font_name, 7)
        page_num = canvas.getPageNumber()
        canvas.drawCentredString(A4[0] / 2, 28, f"— {page_num} —")
        canvas.setFont(font_name, 6.5)
        canvas.drawString(42, 28, "港股IPO申购分析")
        canvas.drawRightString(A4[0] - 42, 28, datetime.now().strftime('%Y-%m-%d'))
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_page_decoration, onLaterPages=add_page_decoration)
    logger.info("✓ PDF报告已生成: %s", output_file)
