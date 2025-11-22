#!/usr/bin/env python3
"""
Federal Court Case Scraper - 演示脚本
联邦法院案件抓取器 - 演示脚本

这个脚本演示了如何使用联邦法院案件抓取器的基本功能。
This script demonstrates basic usage of the Federal Court Case Scraper.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.services.case_scraper_service import CaseScraperService
from src.services.export_service import ExportService
from src.lib.logging_config import setup_logging

def demo_basic_scraping():
    """演示基本的抓取功能 / Demonstrate basic scraping functionality."""
    print("🔍 联邦法院案件抓取器演示 / Federal Court Case Scraper Demo")
    print("=" * 60)

    # 初始化服务 / Initialize services
    scraper = CaseScraperService(headless=True)  # 使用无头模式 / Use headless mode
    exporter = ExportService(output_dir="./demo_output")

    # 示例URL / Example URLs
    test_urls = [
        "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22",
        "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-67890-23"
    ]

    cases = []

    print("📄 开始抓取测试案件... / Starting to scrape test cases...")

    for i, url in enumerate(test_urls, 1):
        try:
            print(f"\n🔄 处理URL {i}/{len(test_urls)}: {url}")
            print(f"🔄 Processing URL {i}/{len(test_urls)}: {url}")

            # 注意：这只是演示，实际URL可能不存在
            # Note: This is just a demo, actual URLs may not exist
            print("⚠️  注意：这是一个演示，实际URL可能无法访问")
            print("⚠️  Note: This is a demo, actual URLs may not be accessible")

            # 这里我们创建一个模拟的案例数据用于演示
            # Here we create mock case data for demonstration
            from datetime import date, datetime
            from src.models.case import Case

            mock_case = Case(
                case_id=url,
                case_number=f"IMM-{12345 + i - 1}-22",
                title=f"Demo Case {i}",
                court="Federal Court",
                date=date(2023, 6, 15),
                html_content=f"<html><body>Demo case {i} content</body></html>",
                scraped_at=datetime.now()
            )

            cases.append(mock_case)
            print(f"✅ 模拟案例创建成功: {mock_case.case_number}")
            print(f"✅ Mock case created: {mock_case.case_number}")

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            print(f"❌ Processing failed: {e}")

    # 导出结果 / Export results
    if cases:
        print(f"\n📊 导出 {len(cases)} 个案例... / Exporting {len(cases)} cases...")

        try:
            # 导出为JSON和CSV / Export to JSON and CSV
            files = exporter.export_all_formats(cases, "demo_cases")
            print("✅ 导出成功! / Export successful!")
            print(f"   JSON: {files['json']}")
            print(f"   CSV: {files['csv']}")

        except Exception as e:
            print(f"❌ 导出失败: {e}")
            print(f"❌ Export failed: {e}")

    print("\n🎉 演示完成! / Demo completed!")
    print("📁 检查 demo_output/ 目录查看结果文件")
    print("📁 Check demo_output/ directory for result files")

    # 清理资源 / Cleanup resources
    scraper.cleanup()

def demo_url_validation():
    """演示URL验证功能 / Demonstrate URL validation functionality."""
    print("\n🔍 URL验证演示 / URL Validation Demo")
    print("=" * 40)

    from src.lib.url_validator import URLValidator

    test_urls = [
        ("https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22", True),
        ("https://www.fct-cf.ca/en/court-files-and-decisions/IMM-67890-23", True),
        ("https://example.com/case/123", False),
        ("https://www.fct-cf.ca/other-path/IMM-12345-22", False),
        ("not-a-url", False),
    ]

    for url, expected in test_urls:
        is_valid, reason = URLValidator.validate_case_url(url)
        status = "✅" if is_valid == expected else "❌"
        print(f"{status} {url}")
        if not is_valid:
            print(f"   原因: {reason}")

def main():
    """主函数 / Main function."""
    # 设置日志 / Setup logging
    setup_logging()

    print("🚀 联邦法院案件抓取器演示开始 / Federal Court Case Scraper Demo Starting")
    print()

    try:
        # 演示URL验证 / Demo URL validation
        demo_url_validation()

        # 演示基本抓取 / Demo basic scraping
        demo_basic_scraping()

    except KeyboardInterrupt:
        print("\n⏹️ 演示被用户中断 / Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ 演示过程中发生错误: {e}")
        print(f"\n❌ Error during demo: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())