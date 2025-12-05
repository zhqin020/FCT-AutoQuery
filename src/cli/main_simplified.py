"""
简化的 CLI 主程序，使用简化的跟踪服务
"""

import logging
import time
from typing import Optional

from services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
from services.export_service import ExportService
from services.case_scraper_service import CaseScraperService
from lib.config import Config

logger = logging.getLogger(__name__)


class SimplifiedCLI:
    """简化的 CLI 类"""
    
    def __init__(self, force: bool = False):
        self.force = force
        self.tracking_service = SimplifiedTrackingService()
        self.exporter = ExportService(Config())
        self.scraper = None
    
    def scrape_single_case(self, case_number: str) -> Optional[object]:
        """采集单个案例"""
        if self.scraper is None:
            self.scraper = CaseScraperService(headless=True)
        
        try:
            # 检查是否应该跳过
            should_skip, reason = self.tracking_service.should_skip_case(case_number, force=self.force)
            if should_skip:
                logger.info(f"Skipping {case_number}: {reason}")
                return None
            
            # 检查是否已存在
            if not self.force and self.exporter.case_exists(case_number):
                logger.info(f"Case {case_number} already exists, skipping")
                self.tracking_service.mark_case_attempt(case_number, CaseStatus.SUCCESS)
                return None
            
            # 初始化页面
            if not getattr(self.scraper, "_initialized", False):
                self.scraper.initialize_page()
            
            # 搜索案例
            exists = self.scraper.search_case(case_number)
            if not exists:
                # search_case 返回 False 仅当检测到 'No data available in table'
                # 这是设置 no_data 状态的唯一合法情况
                logger.info(f"Case {case_number} not found (No data available detected)")
                self.tracking_service.mark_case_attempt(case_number, CaseStatus.NO_DATA)
                return None
            
            # 采集数据
            case_data = self.scraper.scrape_case_data(case_number)
            if case_data:
                # 保存到数据库
                from services.export_service import Case
                case_obj = Case(
                    case_number=case_number,
                    case_type=getattr(case_data.get('case', {}), 'case_type', None),
                    action_type=getattr(case_data.get('case', {}), 'action_type', None),
                    nature_of_proceeding=getattr(case_data.get('case', {}), 'nature_of_proceeding', None),
                    filing_date=getattr(case_data.get('case', {}), 'filing_date', None),
                    office=getattr(case_data.get('case', {}), 'office', None),
                    style_of_cause=getattr(case_data.get('case', {}), 'style_of_cause', None),
                    language=getattr(case_data.get('case', {}), 'language', None),
                    docket_entries=case_data.get('docket_entries', [])
                )
                
                status, message = self.exporter.save_case_to_database(case_obj)
                if status == 'failed':
                    logger.error(f"Failed to save {case_number}: {message}")
                    self.tracking_service.mark_case_attempt(case_number, CaseStatus.FAILED, message)
                    return None
                else:
                    logger.info(f"Successfully saved {case_number}")
                    self.tracking_service.mark_case_attempt(case_number, CaseStatus.SUCCESS)
                    return case_obj
            else:
                logger.error(f"Failed to scrape data for {case_number}")
                self.tracking_service.mark_case_attempt(case_number, CaseStatus.FAILED, "Scraping failed")
                return None
                
        except Exception as e:
            logger.error(f"Error processing {case_number}: {e}")
            self.tracking_service.mark_case_attempt(case_number, CaseStatus.FAILED, str(e))
            return None
    
    def get_statistics(self):
        """获取统计信息"""
        stats = self.tracking_service.get_statistics()
        print("\n=== 采集统计 ===")
        print(f"总案例数: {stats['total_cases']}")
        print("\n按状态分布:")
        for status, data in stats['by_status'].items():
            print(f"  {status}: {data['count']} (最大重试次数: {data['max_retries']})")
    
    def retry_failed_cases(self):
        """重试失败的案例"""
        failed_cases = self.tracking_service.get_failed_cases_for_retry()
        if not failed_cases:
            print("没有需要重试的失败案例")
            return
        
        print(f"找到 {len(failed_cases)} 个需要重试的案例")
        for case_number in failed_cases:
            print(f"重试案例: {case_number}")
            self.scrape_single_case(case_number)


def test_simplified_tracking():
    """测试简化的跟踪功能"""
    logging.basicConfig(level=logging.INFO)
    
    cli = SimplifiedCLI(force=False)
    
    # 测试案例
    test_cases = ['IMM-5-21', 'IMM-9-21', 'IMM-10-21']
    
    print("=== 开始测试采集 ===")
    for case_number in test_cases:
        print(f"\n处理案例: {case_number}")
        result = cli.scrape_single_case(case_number)
        if result:
            print(f"✓ {case_number} 采集成功")
        else:
            print(f"✗ {case_number} 采集失败或跳过")
    
    # 显示统计信息
    cli.get_statistics()
    
    # 再次运行以测试跳过功能
    print("\n=== 再次运行测试跳过功能 ===")
    for case_number in test_cases:
        print(f"\n处理案例: {case_number}")
        result = cli.scrape_single_case(case_number)
        if result:
            print(f"✓ {case_number} 采集成功")
        else:
            print(f"✗ {case_number} 采集失败或跳过")
    
    # 显示最终统计
    cli.get_statistics()


if __name__ == "__main__":
    test_simplified_tracking()