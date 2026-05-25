import re
import logging
from ..utils import _is_num, _extract_table_nums, extract_text_excerpts
from ..table_extraction import extract_financial_table_by_row
from ..settings import SETTINGS
from ..industry_router import classify_company
from . import _adjust_for_unit
logger = logging.getLogger(__name__)


class WorkingCapitalCashFlowAnalyzer:
    @staticmethod
    def _extract_chinese_operating_cash_flow_pair(text):
        match = re.search(
            r'經營活動所得╱（所用）現金淨額(?P<row>[\s\S]{0,260}?)(?=\n\s*(?:投資活動|融资活動|融資活動|現金及現金等價物|$))',
            text,
            re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r'经营活动所得[／/╱]（所用）现金净额(?P<row>[\s\S]{0,260}?)(?=\n\s*(?:投资活动|融资活动|现金及现金等价物|$))',
                text,
                re.IGNORECASE,
            )
        if not match:
            return None, None
        row = match.group('row')
        nums = _extract_table_nums(row, 3, min_val=0)
        if len(nums) < 2:
            return None, None
        latest = nums[-1]
        prev = nums[-2]
        unit_context = text[max(0, match.start() - 500):match.start()]
        return _adjust_for_unit(latest, unit_context), _adjust_for_unit(prev, unit_context)

    @staticmethod
    def _extract_operating_cash_flow(text):
        row_match = re.search(
            r'Net\s+cash\s+(?:used\s+in|generated\s+from|\(used\s+in\)/generated\s+from|used\s+in/generated\s+from)\s+operating\s+activities'
            r'(?P<row>[\s\S]{0,320}?)(?=Net\s+cash|Net\s+increase|Net\s+decrease|$)',
            text,
            re.IGNORECASE,
        )
        if not row_match:
            return None

        row = row_match.group(0)
        row = re.split(
            r'\n\s*\n|\n\s*(?:Financial assets|Financial liabilities|Cash and cash equivalents|Net cash generated from investing|Net cash used in investing)\b',
            row,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        nums = _extract_table_nums(row, 2, min_val=500)
        if not nums:
            return None

        latest = nums[-1]
        if re.search(r'\bused\s+in\b', row, re.IGNORECASE) and latest > 0:
            latest = -latest
        unit_context = text[max(0, row_match.start() - 500):row_match.start()]
        return _adjust_for_unit(latest, unit_context)

    @staticmethod
    def _extract_latest_row_value(text, label_pattern, min_val=0):
        lines = text.split('\n')
        for idx, line in enumerate(lines):
            if not re.match(rf'\s*{label_pattern}\b', line, re.IGNORECASE):
                continue
            window = ' '.join(line.strip() for line in lines[idx:min(idx + 6, len(lines))])
            nums = _extract_table_nums(window, 3, min_val=min_val)
            if len(nums) < 2:
                continue
            latest = nums[2] if len(nums) >= 3 else nums[-1]
            unit_context = '\n'.join(lines[max(0, idx - 80):idx])
            return _adjust_for_unit(latest, unit_context)

        match = re.search(
            rf'\n\s*{label_pattern}(?P<row>[\s\S]{{0,260}}?)(?=\n[A-Z][A-Za-z /&(),-]{{4,}}|\n\d+\.|\Z)',
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        row = match.group(0)
        nums = _extract_table_nums(row, 3, min_val=min_val)
        if not nums:
            nums = _extract_table_nums(row, 2, min_val=min_val)
        if len(nums) < 2:
            return None
        latest = nums[2] if len(nums) >= 3 else nums[-1]
        unit_context = text[max(0, match.start() - 3000):match.start()]
        return _adjust_for_unit(latest, unit_context)

    @staticmethod
    def _extract_latest_amount(text, label_patterns, min_val=0):
        for label_pattern in label_patterns:
            value = WorkingCapitalCashFlowAnalyzer._extract_latest_row_value(text, label_pattern, min_val=min_val)
            if value is not None:
                return value
        return None

    @staticmethod
    def _extract_latest_pair(text, label_patterns, min_val=0):
        for label_pattern in label_patterns:
            lines = text.split('\n')
            for idx, line in enumerate(lines):
                if not re.match(rf'\s*{label_pattern}\b', line, re.IGNORECASE):
                    continue
                window = ' '.join(line.strip() for line in lines[idx:min(idx + 6, len(lines))])
                nums = _extract_table_nums(window, 3, min_val=min_val)
                if len(nums) >= 2:
                    return nums[-1], nums[-2]
                if len(nums) == 1:
                    return nums[-1], None
        return None, None

    def analyze(self, prospectus_info: dict, text: str = '', ipo_data: dict = None) -> dict:
        # 防御：某些调用者把 ipo_data 传到了 text 位置
        if isinstance(text, dict):
            text = ''
        result = {
            'operating_cash_flow': None,
            'ocf_to_net_profit': None,
            'ocf_to_revenue': None,
            'cash_and_cash_equivalents': None,
            'inventory_amount': None,
            'receivables_amount': None,
            'monthly_cash_burn': None,
            'cash_runway_years': None,
            'post_ipo_cash_runway_years': None,
            'inventory_turnover_days_latest': None,
            'receivables_turnover_days_latest': None,
            'receivables_growth_vs_revenue': None,
            'inventory_amount_prev': None,
            'receivables_amount_prev': None,
            'operating_cash_flow_prev': None,
            'cash_balance_prev': None,
            'working_capital_trend_label': '缺失',
            'working_capital_trend_reasons': [],
            'working_capital_pressure_label': '缺失',
            'working_capital_pressure_score': 0,
            'working_capital_pressure_reasons': [],
            'cash_quality_label': '缺失',
            'financing_dependency_label': '缺失',
            'working_capital_risks': [],
            'adjusted_net_profit': None,
            'adjusted_net_profit_y1': None,
            'adjusted_profit_trend_label': '缺失',
            'payables_turnover_days_latest': None,
            'payables_turnover_days_prev': None,
            'yoy_anomalies': [],
            'confidence': 'missing',
            'evidence_excerpt': '',
        }
        try:
            ocf_pair_latest, ocf_pair_prev = self._extract_latest_pair(
                text,
                [
                    r'Net\s+cash\s+(?:used\s+in|generated\s+from|\(used\s+in\)/generated\s+from|used\s+in/generated\s+from)\s+operating\s+activities',
                    r'net\s+cash\s+from\s+operating\s+activities',
                    r'operating\s+cash\s+flow',
                ],
                min_val=500,
            )
            zh_ocf_latest, zh_ocf_prev = self._extract_chinese_operating_cash_flow_pair(text)
            if zh_ocf_latest is not None:
                ocf_pair_latest = zh_ocf_latest
                ocf_pair_prev = zh_ocf_prev
            result['operating_cash_flow_prev'] = ocf_pair_prev
            result['operating_cash_flow'] = self._extract_operating_cash_flow(text)
            if result['operating_cash_flow'] is None:
                result['operating_cash_flow'] = ocf_pair_latest

            ocf_table = extract_financial_table_by_row(text, {
                'operating_cash_flow': ['cash generated from operations', 'net cash from operating activities', 'operating cash flow'],
            })
            if result['operating_cash_flow'] is None and ocf_table and 'operating_cash_flow' in ocf_table:
                years = sorted(ocf_table['operating_cash_flow'].keys())
                if years:
                    result['operating_cash_flow'] = ocf_table['operating_cash_flow'][years[-1]]

            result['cash_and_cash_equivalents'] = self._extract_latest_row_value(
                text,
                r'Cash\s+and\s+cash\s+equivalents',
                min_val=100,
            )
            result['cash_and_cash_equivalents'], result['cash_balance_prev'] = self._extract_latest_pair(
                text,
                [
                    r'Cash\s+and\s+cash\s+equivalents',
                    r'cash\s+and\s+cash\s+equivalents',
                    r'现金及现金等价物',
                ],
                min_val=100,
            )
            result['inventory_amount'] = self._extract_latest_amount(
                text,
                [
                    r'Inventor(?:y|ies)\b',
                    r'Inventories\s+and\s+work\s+in\s+progress',
                    r'存货',
                ],
                min_val=10,
            )
            result['inventory_amount'], result['inventory_amount_prev'] = self._extract_latest_pair(
                text,
                [
                    r'Inventor(?:y|ies)\b',
                    r'Inventories\s+and\s+work\s+in\s+progress',
                    r'存货',
                ],
                min_val=10,
            )
            result['receivables_amount'] = self._extract_latest_amount(
                text,
                [
                    r'(?:Trade\s+)?receivables\b',
                    r'Receivables\s+and\s+other\s+receivables',
                    r'应收账款',
                    r'贸易应收款项',
                ],
                min_val=10,
            )
            result['receivables_amount'], result['receivables_amount_prev'] = self._extract_latest_pair(
                text,
                [
                    r'(?:Trade\s+)?receivables\b',
                    r'Receivables\s+and\s+other\s+receivables',
                    r'应收账款',
                    r'贸易应收款项',
                ],
                min_val=10,
            )

            net_profit = prospectus_info.get('net_profit')
            if _is_num(net_profit) and net_profit > 0 and _is_num(result['operating_cash_flow']):
                result['ocf_to_net_profit'] = round(result['operating_cash_flow'] / net_profit, 2)
            revenue = prospectus_info.get('revenue')
            if _is_num(revenue) and revenue > 0 and _is_num(result['operating_cash_flow']):
                result['ocf_to_revenue'] = round(result['operating_cash_flow'] / revenue, 2)

            adj_np_latest, adj_np_prev = self._extract_latest_pair(
                text,
                [
                    r'Adjusted\s+net\s+loss',
                    r'Adjusted\s+net\s+profit',
                    r'经调整净亏损',
                    r'经调整净利润',
                    r'Adjusted\s+net\s+loss/profit',
                ],
                min_val=0,
            )
            result['adjusted_net_profit'] = adj_np_latest
            result['adjusted_net_profit_y1'] = adj_np_prev
            if adj_np_latest is not None and adj_np_prev is not None:
                if adj_np_latest > adj_np_prev:
                    result['adjusted_profit_trend_label'] = '改善'
                elif adj_np_latest < adj_np_prev:
                    result['adjusted_profit_trend_label'] = '恶化'
                else:
                    result['adjusted_profit_trend_label'] = '平稳'

            inv_match = re.search(r'inventory\s+turnover\s+days\s+were\s+([\d,]+)\s*,\s*([\d,]+)\s*(?:and|&)\s*([\d,]+)', text, re.IGNORECASE)
            if inv_match:
                try:
                    result['inventory_turnover_days_latest'] = float(inv_match.group(3).replace(',', ''))
                except ValueError:
                    pass
            if result['inventory_turnover_days_latest'] is None:
                inv_match = re.search(r'inventor(?:y|ies)\s+turnover\s+days[^.\n]{0,160}?([\d,]+(?:\.\d+)?)\s*(?:days)?', text, re.IGNORECASE)
                if inv_match:
                    try:
                        result['inventory_turnover_days_latest'] = float(inv_match.group(1).replace(',', ''))
                    except ValueError:
                        pass

            rec_match = re.search(r'(?:trade\s+)?receivables?\s+turnover\s+days\s+were\s+([\d,]+)\s*,\s*([\d,]+)\s*(?:and|&)\s*([\d,]+)', text, re.IGNORECASE)
            if rec_match:
                try:
                    result['receivables_turnover_days_latest'] = float(rec_match.group(3).replace(',', ''))
                except ValueError:
                    pass

            payables_turnover_days_prev = None
            pay_match = re.search(r'trade\s+payables?\s+turnover\s+days\s+were\s+([\d,]+)\s*,\s*([\d,]+)\s*(?:and|&)\s*([\d,]+)', text, re.IGNORECASE)
            if pay_match:
                try:
                    result['payables_turnover_days_latest'] = float(pay_match.group(3).replace(',', ''))
                    payables_turnover_days_prev = float(pay_match.group(2).replace(',', ''))
                    result['payables_turnover_days_prev'] = payables_turnover_days_prev
                except ValueError:
                    pass
            if result['payables_turnover_days_latest'] is None:
                pay_match = re.search(r'payables?\s+turnover\s+days[^.\n]{0,160}?([\d,]+(?:\.\d+)?)', text, re.IGNORECASE)
                if pay_match:
                    try:
                        result['payables_turnover_days_latest'] = float(pay_match.group(1).replace(',', ''))
                    except ValueError:
                        pass
            if result['payables_turnover_days_latest'] is None:
                pay_match = re.search(r'(?:应付账款周转天数|应付票据周转天数)[^.\n]{0,80}?([\d,]+(?:\.\d+)?)', text)
                if pay_match:
                    try:
                        result['payables_turnover_days_latest'] = float(pay_match.group(1).replace(',', ''))
                    except ValueError:
                        pass

            # 单位合理性检查：如果某项远大于 revenue（>20x），说明可能未从千元级转换为百万元级
            cash_balance = result.get('cash_and_cash_equivalents')
            revenue_for_unit_check = prospectus_info.get('revenue')
            if _is_num(cash_balance) and _is_num(revenue_for_unit_check) and revenue_for_unit_check > 0:
                if cash_balance / revenue_for_unit_check > 20:
                    cash_balance = cash_balance / 1000
                    result['cash_and_cash_equivalents'] = round(cash_balance, 3)

            inv_amount = result.get('inventory_amount')
            if _is_num(inv_amount) and _is_num(revenue_for_unit_check) and revenue_for_unit_check > 0:
                if inv_amount / revenue_for_unit_check > 20:
                    result['inventory_amount'] = round(inv_amount / 1000, 3)

            rec_amount = result.get('receivables_amount')
            if _is_num(rec_amount) and _is_num(revenue_for_unit_check) and revenue_for_unit_check > 0:
                if rec_amount / revenue_for_unit_check > 20:
                    result['receivables_amount'] = round(rec_amount / 1000, 3)

            operating_cash_flow = result.get('operating_cash_flow')
            if _is_num(cash_balance) and _is_num(operating_cash_flow) and operating_cash_flow < 0:
                result['monthly_cash_burn'] = round(abs(operating_cash_flow) / 12, 2)
                result['cash_runway_years'] = round(cash_balance / abs(operating_cash_flow), 1)
                net_proceeds_hkd = prospectus_info.get('net_proceeds_hkd_million')
                if _is_num(net_proceeds_hkd):
                    fin_currency = prospectus_info.get('financial_currency', 'RMB')
                    if fin_currency == 'RMB':
                        net_proceeds_same_currency = net_proceeds_hkd / SETTINGS.fx.rmb_to_hkd
                    elif fin_currency == 'USD':
                        net_proceeds_same_currency = net_proceeds_hkd / SETTINGS.fx.usd_to_hkd
                    else:
                        net_proceeds_same_currency = net_proceeds_hkd
                    result['post_ipo_cash_runway_years'] = round((cash_balance + net_proceeds_same_currency) / abs(operating_cash_flow), 1)

            risks = []
            ocf_np = result.get('ocf_to_net_profit')
            # Biotech 豁免：现金runway充足时，经营现金流为负不直接判弱
            profile = classify_company(prospectus_info, text)
            is_biotech_with_runway = profile.is_biotech and _is_num(result.get('cash_runway_years')) and result['cash_runway_years'] >= 5
            if _is_num(operating_cash_flow) and operating_cash_flow < 0:
                if is_biotech_with_runway:
                    result['cash_quality_label'] = '一般'
                    risks.append('经营现金流为负，但现金runway充足(≥5年)')
                else:
                    result['cash_quality_label'] = '弱'
                    risks.append('经营现金流为负')
                if _is_num(result.get('ocf_to_revenue')):
                    risks.append(f"经营现金流/收入{result['ocf_to_revenue']*100:.1f}%")
            elif ocf_np is not None:
                cf = SETTINGS.cash_flow
                if ocf_np < 0:
                    result['cash_quality_label'] = '弱'
                    risks.append('经营现金流与净利润方向相反')
                elif ocf_np >= cf.ocf_np_strong:
                    result['cash_quality_label'] = '强'
                elif ocf_np >= cf.ocf_np_fair:
                    result['cash_quality_label'] = '一般'
                else:
                    result['cash_quality_label'] = '弱'
                    risks.append('经营现金流弱于净利润')

            inv_days = result.get('inventory_turnover_days_latest')
            if inv_days is not None and inv_days > SETTINGS.cash_flow.inventory_days_warning:
                risks.append(f'存货周转天数偏高({inv_days:.0f}天)')
            if _is_num(result.get('inventory_amount')) and _is_num(revenue) and revenue > 0:
                inventory_ratio = result['inventory_amount'] / revenue * 100
                if inventory_ratio > 60:
                    risks.append(f'存货/收入偏高({inventory_ratio:.1f}%)')
            if _is_num(result.get('receivables_amount')) and _is_num(revenue) and revenue > 0:
                receivables_ratio = result['receivables_amount'] / revenue * 100
                if result.get('receivables_growth_vs_revenue') is None:
                    result['receivables_growth_vs_revenue'] = round(receivables_ratio, 1)
                if receivables_ratio > 50:
                    risks.append(f'应收/收入偏高({receivables_ratio:.1f}%)')
            if _is_num(result.get('receivables_turnover_days_latest')) and result['receivables_turnover_days_latest'] > 120:
                risks.append(f'应收周转天数偏高({result["receivables_turnover_days_latest"]:.0f}天)')

            adj_np = result.get('adjusted_net_profit')
            if _is_num(adj_np) and adj_np > 0 and _is_num(net_profit) and net_profit < 0:
                risks.append(f'经调整净利润为正({adj_np:.1f}m)，剔除一次性项目后实际盈利')

            pay_days_latest = result.get('payables_turnover_days_latest')
            if _is_num(pay_days_latest) and _is_num(payables_turnover_days_prev) and payables_turnover_days_prev > 0:
                pay_days_change = (pay_days_latest - payables_turnover_days_prev) / payables_turnover_days_prev * 100
                if pay_days_change > 20:
                    risks.append('应付周转天数增加，靠拉长付款缓冲现金流')

            trend_reasons = []
            trend_score = 0
            pressure_score = 0
            pressure_reasons = []
            inv_prev = result.get('inventory_amount_prev')
            rec_prev = result.get('receivables_amount_prev')
            ocf_prev = result.get('operating_cash_flow_prev')
            cash_prev = result.get('cash_balance_prev')
            if _is_num(result.get('inventory_amount')) and _is_num(inv_prev) and inv_prev > 0:
                inv_change = (result['inventory_amount'] - inv_prev) / inv_prev * 100
                trend_reasons.append(f'存货较前期{inv_change:+.1f}%')
                if inv_change > 10:
                    trend_score -= 1
                    pressure_score += 1
                elif inv_change < -10:
                    trend_score += 1
            if _is_num(result.get('receivables_amount')) and _is_num(rec_prev) and rec_prev > 0:
                rec_change = (result['receivables_amount'] - rec_prev) / rec_prev * 100
                trend_reasons.append(f'应收较前期{rec_change:+.1f}%')
                if rec_change > 10:
                    trend_score -= 1
                    pressure_score += 1
                elif rec_change < -10:
                    trend_score += 1
            if _is_num(result.get('operating_cash_flow')) and _is_num(ocf_prev) and ocf_prev != 0:
                ocf_change = (result['operating_cash_flow'] - ocf_prev) / abs(ocf_prev) * 100
                trend_reasons.append(f'OCF较前期{ocf_change:+.1f}%')
                if result['operating_cash_flow'] < ocf_prev:
                    trend_score -= 1
                    pressure_score += 1
                elif result['operating_cash_flow'] > ocf_prev:
                    trend_score += 1
            if _is_num(result.get('cash_and_cash_equivalents')) and _is_num(cash_prev) and cash_prev > 0:
                cash_change = (result['cash_and_cash_equivalents'] - cash_prev) / cash_prev * 100
                trend_reasons.append(f'现金较前期{cash_change:+.1f}%')
                if cash_change < -10:
                    pressure_score += 1
                elif cash_change > 10:
                    pressure_score -= 1
            if _is_num(result.get('inventory_amount')) and _is_num(revenue) and revenue > 0:
                inv_ratio = result['inventory_amount'] / revenue * 100
                if inv_ratio > 80:
                    pressure_score += 2
                    pressure_reasons.append(f'存货/收入{inv_ratio:.1f}%')
                elif inv_ratio > 60:
                    pressure_score += 1
                    pressure_reasons.append(f'存货/收入{inv_ratio:.1f}%')
            if _is_num(result.get('receivables_amount')) and _is_num(revenue) and revenue > 0:
                rec_ratio = result['receivables_amount'] / revenue * 100
                if rec_ratio > 70:
                    pressure_score += 2
                    pressure_reasons.append(f'应收/收入{rec_ratio:.1f}%')
                elif rec_ratio > 50:
                    pressure_score += 1
                    pressure_reasons.append(f'应收/收入{rec_ratio:.1f}%')
            if _is_num(result.get('monthly_cash_burn')) and result['monthly_cash_burn'] > 0:
                pressure_reasons.append(f'月均现金消耗约{result["monthly_cash_burn"]:.2f}M')
                if result['monthly_cash_burn'] > 50:
                    pressure_score += 2
                elif result['monthly_cash_burn'] > 20:
                    pressure_score += 1
            if _is_num(result.get('cash_runway_years')):
                if result['cash_runway_years'] < 1:
                    pressure_score += 2
                    pressure_reasons.append(f'上市前现金runway仅{result["cash_runway_years"]:.1f}年')
                elif result['cash_runway_years'] < 2:
                    pressure_score += 1
            if _is_num(result.get('post_ipo_cash_runway_years')):
                if result['post_ipo_cash_runway_years'] < 1.5:
                    pressure_score += 1
                    pressure_reasons.append(f'募资后runway约{result["post_ipo_cash_runway_years"]:.1f}年')
            if trend_score > 0:
                result['working_capital_trend_label'] = '改善'
            elif trend_score < 0:
                result['working_capital_trend_label'] = '恶化'
            elif trend_reasons:
                result['working_capital_trend_label'] = '平稳'
            result['working_capital_trend_reasons'] = trend_reasons[:4]
            if pressure_score >= 4:
                result['working_capital_pressure_label'] = '高'
            elif pressure_score >= 2:
                result['working_capital_pressure_label'] = '中'
            elif pressure_score > 0:
                result['working_capital_pressure_label'] = '低'
            else:
                result['working_capital_pressure_label'] = '可控' if trend_score >= 0 else '低'
            result['working_capital_pressure_score'] = max(0, pressure_score)
            result['working_capital_pressure_reasons'] = pressure_reasons[:5]

            runway = result.get('cash_runway_years')
            post_runway = result.get('post_ipo_cash_runway_years')
            if _is_num(runway):
                if runway < 1:
                    result['financing_dependency_label'] = '高'
                    risks.append(f'上市前现金runway约{runway:.1f}年')
                elif runway < 2:
                    result['financing_dependency_label'] = '中'
                else:
                    result['financing_dependency_label'] = '低'
            if _is_num(result.get('monthly_cash_burn')) and result['monthly_cash_burn'] > 0:
                risks.append(f'月均现金消耗约{result["monthly_cash_burn"]:.2f}M')
            if _is_num(post_runway):
                risks.append(f'募资后现金runway约{post_runway:.1f}年')

            result['working_capital_risks'] = risks

            anomalies = []
            yoy_checks = [
                ('收入', prospectus_info.get('revenue'), prospectus_info.get('revenue_y1')),
                ('毛利率', prospectus_info.get('gross_margin'), prospectus_info.get('gross_margin_y1')),
                ('净利润', prospectus_info.get('net_profit'), prospectus_info.get('net_profit_y1')),
                ('经营现金流', result.get('operating_cash_flow'), result.get('operating_cash_flow_prev')),
            ]
            for item_name, latest_val, prev_val in yoy_checks:
                if not _is_num(latest_val) or not _is_num(prev_val) or prev_val == 0:
                    continue
                change_pct = abs((latest_val - prev_val) / prev_val * 100)
                if change_pct > 50:
                    direction = '上升' if latest_val > prev_val else '下降'
                    explanation = None
                    search_terms = {
                        '收入': [r'revenue', r'收入', r'turnover'],
                        '毛利率': [r'gross\s+margin', r'毛利率', r'gross\s+profit\s+margin'],
                        '净利润': [r'net\s+profit', r'net\s+loss', r'净利润', r'净亏损'],
                        '经营现金流': [r'operating\s+cash\s+flow', r'net\s+cash\s+from\s+operating', r'经营现金流'],
                    }
                    terms = search_terms.get(item_name, [])
                    for term in terms:
                        exp_match = re.search(
                            rf'{term}[^.\n]{{0,120}}?(?:due\s+to|主要由于|was\s+primarily|driven\s+by)[^.\n]{{0,200}}',
                            text,
                            re.IGNORECASE,
                        )
                        if exp_match:
                            explanation = exp_match.group(0).strip()[:200]
                            break
                    anomalies.append({
                        'item': item_name,
                        'change_pct': round(change_pct, 1),
                        'direction': direction,
                        'explanation': explanation,
                    })
            anomalies.sort(key=lambda x: x['change_pct'], reverse=True)
            result['yoy_anomalies'] = anomalies[:5]

            excerpt_patterns = [
                r'Net\s+cash\s+(?:used\s+in|generated\s+from|\(used\s+in\)/generated\s+from|used\s+in/generated\s+from)\s+operating\s+activities',
                r'Cash\s+and\s+cash\s+equivalents',
                r'Inventor(?:y|ies)\b',
                r'(?:Trade\s+)?receivables\b',
            ]
            result['evidence_excerpt'] = "\n\n".join(
                extract_text_excerpts(text, excerpt_patterns, window=200, max_chars=1000, limit=3)
            )
            if result['operating_cash_flow'] is not None or inv_days is not None or result.get('cash_and_cash_equivalents') is not None:
                result['confidence'] = 'regex_context'

            # --- data_availability 元数据 ---
            availability = {}

            def _avail_cf(key, val, na_reason=None):
                if val is not None and val != '缺失':
                    availability[key] = {'status': 'available', 'method': 'computed', 'reason': f'{key} 已提取'}
                elif na_reason:
                    availability[key] = {'status': 'not_applicable', 'reason': na_reason, 'source_excerpt': None}
                else:
                    availability[key] = {'status': 'not_found', 'reason': f'招股书未披露 {key}', 'source_excerpt': None}

            _avail_cf('operating_cash_flow', result.get('operating_cash_flow'))
            _avail_cf('ocf_to_revenue', result.get('ocf_to_revenue'),
                      '收入基数极小，OCF/收入无意义' if profile.is_early_stage() else None)
            _avail_cf('cash_and_cash_equivalents', result.get('cash_and_cash_equivalents'))
            _avail_cf('inventory_amount', result.get('inventory_amount'))
            _avail_cf('receivables_amount', result.get('receivables_amount'))
            _avail_cf('monthly_cash_burn', result.get('monthly_cash_burn'),
                      '经营现金流为正，月耗现金不适用' if result.get('operating_cash_flow') is not None and result['operating_cash_flow'] >= 0 else None)
            _avail_cf('working_capital_trend_label', result.get('working_capital_trend_label', '缺失'))
            _avail_cf('working_capital_pressure_label', result.get('working_capital_pressure_label', '缺失'))
            _avail_cf('cash_quality_label', result.get('cash_quality_label', '缺失'))
            _avail_cf('post_ipo_cash_runway_years', result.get('post_ipo_cash_runway_years'))

            result['data_availability'] = availability
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result
