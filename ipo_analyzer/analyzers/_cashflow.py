import re
import logging
from ..utils import _is_num, _extract_table_nums
from ..table_extraction import extract_financial_table_by_row
from ..settings import SETTINGS
from . import _adjust_for_unit
logger = logging.getLogger(__name__)


class WorkingCapitalCashFlowAnalyzer:
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

    def analyze(self, prospectus_info: dict, text: str = '', ipo_data: dict = None) -> dict:
        # 防御：某些调用者把 ipo_data 传到了 text 位置
        if isinstance(text, dict):
            text = ''
        result = {
            'operating_cash_flow': None,
            'ocf_to_net_profit': None,
            'ocf_to_revenue': None,
            'cash_and_cash_equivalents': None,
            'cash_runway_years': None,
            'post_ipo_cash_runway_years': None,
            'inventory_turnover_days_latest': None,
            'receivables_turnover_days_latest': None,
            'receivables_growth_vs_revenue': None,
            'cash_quality_label': '缺失',
            'financing_dependency_label': '缺失',
            'working_capital_risks': [],
            'confidence': 'missing',
        }
        try:
            result['operating_cash_flow'] = self._extract_operating_cash_flow(text)

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

            net_profit = prospectus_info.get('net_profit')
            if _is_num(net_profit) and net_profit > 0 and _is_num(result['operating_cash_flow']):
                result['ocf_to_net_profit'] = round(abs(result['operating_cash_flow']) / net_profit, 2)
            revenue = prospectus_info.get('revenue')
            if _is_num(revenue) and revenue > 0 and _is_num(result['operating_cash_flow']):
                result['ocf_to_revenue'] = round(result['operating_cash_flow'] / revenue, 2)

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

            # 单位合理性检查：如果 cash 远大于 revenue（>20x），说明 cash 可能未从千元级转换为百万元级
            cash_balance = result.get('cash_and_cash_equivalents')
            revenue_for_unit_check = prospectus_info.get('revenue')
            if _is_num(cash_balance) and _is_num(revenue_for_unit_check) and revenue_for_unit_check > 0:
                if cash_balance / revenue_for_unit_check > 20:
                    cash_balance = cash_balance / 1000
                    result['cash_and_cash_equivalents'] = round(cash_balance, 3)

            operating_cash_flow = result.get('operating_cash_flow')
            if _is_num(cash_balance) and _is_num(operating_cash_flow) and operating_cash_flow < 0:
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
            if _is_num(operating_cash_flow) and operating_cash_flow < 0:
                result['cash_quality_label'] = '弱'
                risks.append('经营现金流为负')
                if _is_num(result.get('ocf_to_revenue')):
                    risks.append(f"经营现金流/收入{result['ocf_to_revenue']*100:.1f}%")
            elif ocf_np is not None:
                cf = SETTINGS.cash_flow
                if ocf_np >= cf.ocf_np_strong:
                    result['cash_quality_label'] = '强'
                elif ocf_np >= cf.ocf_np_fair:
                    result['cash_quality_label'] = '一般'
                else:
                    result['cash_quality_label'] = '弱'
                    risks.append('经营现金流弱于净利润')

            inv_days = result.get('inventory_turnover_days_latest')
            if inv_days is not None and inv_days > SETTINGS.cash_flow.inventory_days_warning:
                risks.append(f'存货周转天数偏高({inv_days:.0f}天)')

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
            if _is_num(post_runway):
                risks.append(f'募资后现金runway约{post_runway:.1f}年')

            result['working_capital_risks'] = risks
            if result['operating_cash_flow'] is not None or inv_days is not None or result.get('cash_and_cash_equivalents') is not None:
                result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result
