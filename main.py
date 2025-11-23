#!/usr/bin/env python3
"""
Federal Court Case Scraper - Main Entry Point
联邦法院案件抓取器 - 主入口程序

This script demonstrates how to use the Federal Court Case Scraper
to automatically query and export case information from the Canadian
Federal Court website.

Usage:
    python main.py [case_url]

Example:
    python main.py "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.lib.logging_config import setup_logging
from src.services.case_scraper_service import CaseScraperService
from src.services.export_service import ExportService

# Setup logging
setup_logging()


def main():
    """Main entry point for the Federal Court Case Scraper."""
    parser = argparse.ArgumentParser(
        description="Federal Court Case Scraper - 联邦法院案件自动查询系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例 / Usage Examples:

1. 抓取单个案件 / Scrape single case:
   python main.py "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"

2. 批量抓取多个案件 / Batch scrape multiple cases:
   python main.py --batch cases.txt

3. 指定输出目录 / Specify output directory:
   python main.py --output ./results "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"

注意事项 / Important Notes:
- 程序会自动遵守速率限制 (1秒间隔)
- 所有操作都会记录到日志中
- 程序会自动验证URL的有效性
- 如遇连续错误会触发紧急停止机制
        """,
    )

    parser.add_argument(
        "url", nargs="?", help="联邦法院案件URL / Federal Court case URL"
    )

    parser.add_argument(
        "--batch",
        type=str,
        help="包含多个URL的文件路径 / File containing multiple URLs (one per line)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="./output",
        help="输出目录 / Output directory (default: ./output)",
    )

    parser.add_argument(
        "--format",
        choices=["json", "csv", "both"],
        default="both",
        help="导出格式 / Export format (default: both)",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="无头模式运行浏览器 / Run browser in headless mode (default: True)",
    )

    parser.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless",
        help="显示浏览器窗口 / Show browser window",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.url and not args.batch:
        parser.error(
            "必须提供案件URL或批量文件 / Must provide either a case URL or batch file"
        )

    if args.url and args.batch:
        parser.error(
            "不能同时指定URL和批量文件 / Cannot specify both URL and batch file"
        )

    try:
        # Initialize services
        print(
            "🚀 初始化联邦法院案件抓取器... / Initializing Federal Court Case Scraper..."
        )
        scraper = CaseScraperService(headless=args.headless)
        exporter = ExportService(output_dir=args.output)

        cases = []

        if args.url:
            # Single case scraping
            print(f"📄 正在抓取案件: {args.url}")
            print(f"📄 Scraping case: {args.url}")

            case = scraper.scrape_single_case(args.url)
            cases.append(case)

            print("✅ 案件抓取成功! / Case scraped successfully!")
            print(f"   案件编号: {case.case_number}")
            print(f"   标题: {case.title}")
            print(f"   日期: {case.date}")
            print(f"   Case Number: {case.case_number}")
            print(f"   Title: {case.title}")
            print(f"   Date: {case.date}")

        elif args.batch:
            # Batch scraping
            batch_file = Path(args.batch)
            if not batch_file.exists():
                print(f"❌ 批量文件不存在: {args.batch}")
                print(f"❌ Batch file not found: {args.batch}")
                return 1

            print(f"📋 正在读取批量文件: {args.batch}")
            print(f"📋 Reading batch file: {args.batch}")

            with open(batch_file, "r", encoding="utf-8") as f:
                urls = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                ]

            print(f"📄 发现 {len(urls)} 个URL / Found {len(urls)} URLs")

            for i, url in enumerate(urls, 1):
                try:
                    print(f"🔄 正在处理 ({i}/{len(urls)}): {url}")
                    print(f"🔄 Processing ({i}/{len(urls)}): {url}")

                    case = scraper.scrape_single_case(url)
                    cases.append(case)

                    print(f"   ✅ 成功: {case.case_number}")
                    print(f"   ✅ Success: {case.case_number}")

                except Exception as e:
                    print(f"   ❌ 失败: {e}")
                    print(f"   ❌ Failed: {e}")

                    # Check for emergency stop
                    if scraper.is_emergency_stop_active():
                        print(
                            "🚨 紧急停止已激活，停止所有操作 / Emergency stop activated, halting all operations"
                        )
                        break

        # Export results
        if cases:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"federal_court_cases_{timestamp}"

            print(
                f"\n📊 正在导出 {len(cases)} 个案件... / Exporting {len(cases)} cases..."
            )

            if args.format == "json":
                json_file = exporter.export_to_json(cases, f"{base_filename}.json")
                print(f"📄 JSON文件已保存: {json_file}")
                print(f"📄 JSON file saved: {json_file}")

            elif args.format == "csv":
                csv_file = exporter.export_to_csv(cases, f"{base_filename}.csv")
                print(f"📄 CSV文件已保存: {csv_file}")
                print(f"📄 CSV file saved: {csv_file}")

            else:  # both
                files = exporter.export_all_formats(cases, base_filename)
                print(f"📄 文件已保存 / Files saved:")
                print(f"   JSON: {files['json']}")
                print(f"   CSV: {files['csv']}")

            print("\n🎉 所有操作完成! / All operations completed!")
            print(f"📁 输出目录: {args.output}")
            print(f"📁 Output directory: {args.output}")

        else:
            print("\n❌ 未成功抓取任何案件 / No cases were successfully scraped")
            return 1

    except KeyboardInterrupt:
        print("\n⏹️  用户中断操作 / Operation interrupted by user")
        return 130

    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        print(f"\n❌ Error occurred: {e}")
        return 1

    finally:
        # Always cleanup
        scraper.cleanup()

    return 0


if __name__ == "__main__":
    sys.exit(main())
