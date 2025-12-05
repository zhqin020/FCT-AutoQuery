"""Enhanced statistics service for comprehensive batch processing reporting."""

from datetime import datetime
from typing import Dict, Any
import psycopg2
from src.lib.config import Config
from src.lib.logging_config import get_logger

logger = get_logger()


class EnhancedStatisticsService:
    """Service for providing comprehensive statistics before and after batch runs."""
    
    def __init__(self):
        self.config = Config()
        self.db_config = self.config.get_db_config()
    
    def get_year_statistics(self, year: int) -> Dict[str, Any]:
        """Get comprehensive statistics for a specific year.
        
        Args:
            year: Year to get statistics for (e.g., 2021)
            
        Returns:
            Dict containing comprehensive statistics
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            year_suffix = year % 100
            like_pattern = f"%-{year_suffix:02d}"
            
            # Get status breakdown for the year
            cursor.execute("""
                SELECT 
                    status,
                    COUNT(*) as count,
                    MAX(retry_count) as max_retries,
                    AVG(retry_count) as avg_retries
                FROM cases 
                WHERE case_number LIKE %s
                GROUP BY status
                ORDER BY count DESC
            """, (like_pattern,))
            
            status_stats = {}
            total_cases = 0
            for row in cursor.fetchall():
                if len(row) >= 4:
                    status, count, max_retries, avg_retries = row[0], row[1], row[2], row[3]
                elif len(row) == 3:
                    status, count, max_retries = row
                    avg_retries = 0
                elif len(row) == 2:
                    status, count = row
                    max_retries = 0
                    avg_retries = 0
                else:
                    continue
                    
                status_stats[status] = {
                    'count': count,
                    'max_retries': max_retries or 0,
                    'avg_retries': round(avg_retries or 0, 2)
                }
                total_cases += count
            
            # Get timing information
            cursor.execute("""
                SELECT 
                    MIN(scraped_at) as first_scraped,
                    MAX(scraped_at) as last_scraped,
                    COUNT(CASE WHEN scraped_at IS NOT NULL THEN 1 END) as scraped_count
                FROM cases 
                WHERE case_number LIKE %s
            """, (like_pattern,))
            
            timing_row = cursor.fetchone()
            if timing_row and len(timing_row) >= 3:
                first_scraped, last_scraped, scraped_count = timing_row[0], timing_row[1], timing_row[2]
                first_created = first_scraped  # Use scraped_at as created time fallback
            else:
                first_created, last_scraped, first_scraped, scraped_count = None, None, None, 0
            
            # Get retry statistics
            cursor.execute("""
                SELECT 
                    retry_count,
                    COUNT(*) as count
                FROM cases 
                WHERE case_number LIKE %s AND retry_count > 0
                GROUP BY retry_count
                ORDER BY retry_count DESC
            """, (like_pattern,))
            
            retry_distribution = {}
            for row in cursor.fetchall():
                if len(row) >= 2:
                    retry_distribution[row[0]] = row[1]
            
            cursor.close()
            conn.close()
            
            return {
                'year': year,
                'total_cases': total_cases,
                'by_status': status_stats,
                'success_count': status_stats.get('success', {}).get('count', 0),
                'failed_count': status_stats.get('failed', {}).get('count', 0),
                'no_data_count': status_stats.get('no_data', {}).get('count', 0),
                'other_count': total_cases - (
                    status_stats.get('success', {}).get('count', 0) +
                    status_stats.get('failed', {}).get('count', 0) +
                    status_stats.get('no_data', {}).get('count', 0)
                ),
                'scraped_count': scraped_count or 0,
                'first_created': first_created,
                'last_scraped': last_scraped,
                'first_scraped': first_scraped,
                'retry_distribution': retry_distribution
            }
            
        except Exception as e:
            logger.error(f"Error getting year statistics for {year}: {e}")
            return {
                'year': year,
                'total_cases': 0,
                'by_status': {},
                'success_count': 0,
                'failed_count': 0,
                'no_data_count': 0,
                'other_count': 0,
                'error': str(e)
            }
    
    def format_statistics_for_display(self, stats: Dict[str, Any], title: str = None) -> str:
        """Format statistics for readable console and log output.
        
        Args:
            stats: Statistics dictionary from get_year_statistics or run_statistics
            title: Optional title for the statistics display
            
        Returns:
            Formatted string for display
        """
        if title:
            lines = [f"\n{'='*60}", f"{title}", f"{'='*60}"]
        else:
            lines = []
        
        if 'year' in stats:
            lines.append(f"年份 (Year): {stats['year']}")
        
        lines.append(f"总计案例 (Total Cases): {stats['total_cases']}")
        
        # Status breakdown
        if stats.get('by_status'):
            lines.append("\n状态分布 (Status Distribution):")
            for status, data in stats['by_status'].items():
                lines.append(f"  {status}: {data['count']} 案例")
                if data.get('max_retries', 0) > 0:
                    lines.append(f"    - 最大重试次数: {data['max_retries']}")
                    lines.append(f"    - 平均重试次数: {data['avg_retries']}")
        
        # Summary counts
        lines.append("\n汇总统计 (Summary):")
        lines.append(f"  成功 (Success): {stats['success_count']}")
        lines.append(f"  失败 (Failed): {stats['failed_count']}")
        lines.append(f"  无数据 (No Data): {stats['no_data_count']}")
        lines.append(f"  其他 (Other): {stats['other_count']}")
        
        # Timing information
        if stats.get('start_time'):
            lines.append("\n时间信息 (Timing):")
            lines.append(f"  开始时间: {stats['start_time']}")
            if stats.get('end_time'):
                lines.append(f"  结束时间: {stats['end_time']}")
                if stats.get('duration_seconds'):
                    lines.append(f"  运行时长: {stats['duration_seconds']:.2f} 秒")
        
        if stats.get('last_scraped'):
            lines.append(f"  最后采集时间: {stats['last_scraped']}")
        if stats.get('first_scraped'):
            lines.append(f"  首次采集时间: {stats['first_scraped']}")
        
        # Additional run-specific information
        if 'upper_bound' in stats:
            lines.append(f"\n运行信息 (Run Information):")
            lines.append(f"  上边界编号: {stats['upper_bound']}")
            lines.append(f"  处理数量: {stats.get('processed_count', 0)}")
            lines.append(f"  探测次数: {stats.get('probes_used', 0)}")
        
        return "\n".join(lines)
    
    def calculate_run_statistics(
        self,
        year: int,
        start_time: datetime,
        end_time: datetime,
        upper_bound: int = None,
        processed_count: int = 0,
        probes_used: int = 0,
        cases_collected: int = 0,
        run_id: str = None
    ) -> Dict[str, Any]:
        """Calculate comprehensive run statistics.
        
        Args:
            year: Year being processed
            start_time: Run start time
            end_time: Run end time
            upper_bound: Upper bound found during probing
            processed_count: Number of cases processed in this run
            probes_used: Number of probes used during probing
            cases_collected: Number of cases collected in this run
            run_id: Optional run ID for tracking
            
        Returns:
            Comprehensive run statistics
        """
        duration_seconds = (end_time - start_time).total_seconds()
        
        # Get before/after statistics for comparison
        # Note: In a real implementation, you'd want to get "before" stats
        # at the start of the run and "after" stats at the end
        after_stats = self.get_year_statistics(year)
        
        return {
            'run_id': run_id,
            'year': year,
            'start_time': start_time,
            'end_time': end_time,
            'duration_seconds': duration_seconds,
            'upper_bound': upper_bound,
            'processed_count': processed_count,
            'probes_used': probes_used,
            'cases_collected': cases_collected,
            'success_rate': (cases_collected / processed_count * 100) if processed_count > 0 else 0,
            **after_stats  # Include all the year statistics
        }
    
    def log_and_display_statistics(self, stats: Dict[str, Any], title: str = None):
        """Log and display statistics in a readable format.
        
        Args:
            stats: Statistics dictionary
            title: Optional title for display
        """
        formatted_stats = self.format_statistics_for_display(stats, title)
        
        # Print to console
        print(formatted_stats)
        
        # Log to file
        logger.info(f"Statistics Report:\n{formatted_stats}")