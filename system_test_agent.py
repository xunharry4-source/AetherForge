import sys
import os
import datetime
from typing import Dict, List
from logger_utils import get_logger

# Add current dir to sys.path for probe imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from test_probes.api_probes import APIProbe
from test_probes.sync_probes import SyncProbe

logger = get_logger("system.test.agent")

class SystemTestAgent:
    def __init__(self, output_report: str = "system_health_report.md"):
        self.output_report = output_report
        self.probes = {
            "API 接口审计 (REST API)": APIProbe(),
            "同步与数据审计 (Sync & Data)": SyncProbe()
        }

    def run_audit(self):
        logger.info("Starting System-Wide Audit...")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        full_results = {}
        for name, probe in self.probes.items():
            logger.info(f"Running probe: {name}")
            full_results[name] = probe.run_all()

        report_content = self.generate_report_markdown(timestamp, full_results)
        
        with open(self.output_report, "w", encoding="utf-8") as f:
            f.write(report_content)
        
        logger.info(f"Audit completed. Report generated: {self.output_report}")
        return full_results

    def generate_report_markdown(self, timestamp: str, results: dict) -> str:
        report = []
        report.append(f"# 系统健康审计报告 (System Health Report)\n")
        report.append(f"> **审计时间**: `{timestamp}`\n")
        
        overall_status = "🟢 HEALTHY"
        for section in results.values():
            for test in section.values():
                if test["status"] == "FAIL" or test["status"] == "ERROR":
                    overall_status = "🔴 CRITICAL"
                    break
        
        report.append(f"## 总体状态: {overall_status}\n")
        report.append("---\n")

        for section_name, section_results in results.items():
            report.append(f"### {section_name}\n")
            report.append("| 测试项目 | 状态 | 详情 |")
            report.append("| :--- | :--- | :--- |")
            for test_name, res in section_results.items():
                status_emoji = "✅" if res["status"] == "PASS" else ("⚠️" if res["status"] == "WARN" else "❌")
                report.append(f"| {test_name} | {status_emoji} {res['status']} | {res['msg']} |")
            report.append("\n")

        report.append("---\n")
        report.append("### 建议 (Recommendations)\n")
        
        issues_found = False
        for section in results.values():
            for name, test in section.items():
                if test["status"] in ["FAIL", "ERROR", "WARN"]:
                    issues_found = True
                    report.append(f"- **{name}**: {test['msg']}")
        
        if not issues_found:
            report.append("- 所有核心链路均正常，系统处于最佳状态。")

        return "\n".join(report)

if __name__ == "__main__":
    agent = SystemTestAgent()
    agent.run_audit()
