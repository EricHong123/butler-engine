"""Tool: Generate structured reports (asset review, tax summary, health overview)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from butler.engine.base_tool import BaseTool, ToolResult


class ReportInput(BaseModel):
    """Input for generating reports."""
    report_type: str = Field(description="Report type: 'asset_monthly', 'tax_quarterly', 'health_annual', 'education_progress'")
    period: str | None = Field(default=None, description="Report period: '2026-04', '2026-Q1', '2026'")
    format: str = Field(default="markdown", description="Output format: 'markdown' or 'summary'")


class GenerateReportTool(BaseTool):
    """
    Compile structured reports for the family.

    Generates markdown reports that can be rendered in the Web portal
    or formatted for the quarterly physical report booklet.
    """

    name = "generate_report"
    aliases = ["生成报告", "资产月报", "报告"]
    search_hint = "report monthly quarterly asset tax health education"

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    async def call(self, args: dict, context: Any) -> ToolResult:
        tenant_id = self._require_tenant(context)
        report_type = args.get("report_type", "asset_monthly")
        period = args.get("period", "2026-04")
        fmt = args.get("format", "markdown")

        if report_type == "asset_monthly":
            report = _asset_monthly_report(period)
        elif report_type == "tax_quarterly":
            report = _tax_quarterly_report(period)
        elif report_type == "health_annual":
            report = _health_annual_report(period)
        elif report_type == "education_progress":
            report = _education_progress_report(period)
        else:
            return ToolResult(data={"error": f"Unknown report type: {report_type}"})

        return ToolResult(data={
            "report_type": report_type,
            "period": period,
            "format": fmt,
            "report_markdown": report if fmt == "markdown" else _summarize(report),
        })

    async def description(self, input: dict, options: dict) -> str:
        return f"Generate {input.get('report_type', 'report')} for {input.get('period', 'current period')}"

    def input_schema(self) -> type[BaseModel]:
        return ReportInput


def _asset_monthly_report(period: str) -> str:
    return f"""# 家族资产月报 — {period}

## 资产总览
截至{period}月末，家族总资产约 **¥1.72亿**（含不动产估值）。

## 资产分布

| 类别 | 市值 | 占比 | 变动 |
|------|------|------|------|
| 银行存款 | ¥975万 | 5.7% | +¥70万 |
| 证券投资 | ¥2,500万 | 14.5% | +¥45万 |
| 信托资产 | ¥8,000万 | 46.5% | 持平 |
| 保险现金价值 | ¥580万 | 3.4% | 持平 |
| 不动产 | ¥5,700万 | 33.2% | 持平 |

## 流动性分析
- 高流动性资产（活期+货币基金）：¥975万
- 中流动性资产（证券+可赎回信托）：¥4,200万
- 低流动性资产（不可赎回信托+不动产）：¥1.07亿

## 重点关注
1. **CMB活期余额偏高**：建议将超过¥500万部分转投短期理财，预计年化可提升¥12万收益
2. **HSBC美元账户**：汇率波动，CNY/USD从7.05升至7.18，美元资产增值约¥78万
3. **6月保险保费到期**：友邦年缴$50,000，请确保HSBC账户余额充足

## 下月关注
- 5月31日：香港物业税申报截止
- 6月1日：友邦保险年缴保费
- 6月7日：洪明SAT考试
"""


def _tax_quarterly_report(period: str) -> str:
    return f"""# 税务季度报告 — {period}

## 本季度待办

| 事项 | 截止日期 | 管辖地 | 状态 |
|------|----------|--------|------|
| 个人所得税汇算清缴 | 2026-06-30 | 中国大陆 | 待申报 |
| 物业税申报 | 2026-05-31 | 香港 | **紧急** |
| CRS信息申报 | 2026-05-31 | 中国大陆 | 自动交换 |
| 利得税申报 | 2026-08-15 | 香港 | 待审计 |

## 税务风险提示
- 香港与大陆CRS信息已自动交换，请确保两地申报一致性
- 北京投资房产租金收入需并入综合所得汇算

## 优化建议
- 考虑通过信托结构优化房产持有税负
- 子女教育信托分配可享受税收优惠
"""


def _health_annual_report(period: str) -> str:
    return f"""# 家庭健康年报 — {period}

## 洪伟 (48岁)
- 最近体检: 2026-02-20, 上海和睦家
- 总体评价: 良好
- 关注项: LDL胆固醇 3.8mmol/L (偏高), 建议3个月后复查
- 运动: 每周2次高尔夫，建议增加有氧运动

## 张丽 (45岁)
- 最近体检: 2026-01-15, 上海瑞金医院
- 总体评价: 良好
- 关注项: 甲状腺结节 (3类, 年度随访)

## 洪明 (16岁)
- 最近体检: 2025-09-01, Andover校医
- 总体评价: 良好
- 视力: 需年度检查

## 洪悦 (12岁)
- 最近体检: 2026-03-10, 上海儿童医学中心
- 总体评价: 良好
- 疫苗接种: 按时完成

## 建议
- 全家人建议每年至少一次全面体检
- 洪伟建议6月底前复查血脂
"""


def _education_progress_report(period: str) -> str:
    return f"""# 子女教育进展报告 — {period}

## 洪明 (16岁, Phillips Academy Andover, 11年级)

### 学业
- GPA: 3.8/4.0 (截至2026春季学期)
- 强项: Mathematics (AP Calculus BC, A), Physics (AP Physics C, A-)
- 待提升: English Literature (B+)

### 标化考试
- SAT考试: 2026-06-07 (即将)
- 目标: 1550+

### 大学申请准备
- 目标院校: MIT/Stanford/UC Berkeley (工科方向)
- 夏校: 已申请MIT RSI, 等待结果
- 推荐人: Dr. Smith (数学老师) 已确认

### 近期节点
- 06/07: SAT考试
- 07/15: RSI夏校结果
- 08/01: Common App文书启动

## 洪悦 (12岁, Harrow International School Shanghai, 7年级)

### 学业
- 整体表现优秀，数学和音乐突出
- 钢琴: ABRSM Grade 7 通过 (2026-03)

### 近期节点
- 05/20: 上海音乐学院钢琴比赛
- 08/15: 瑞士夏令营 (已报名)

## 财务概览
- 年度教育预算: ¥350万
- 已支出 (截至{period}): ¥180万
- 教育信托余额: ¥3,000万
"""


def _summarize(report: str) -> str:
    """Extract key bullets from a report as a brief summary."""
    lines = report.split("\n")
    bullets = [l.strip("- ") for l in lines if l.startswith("- ")]
    return "\n".join(bullets[:10])
