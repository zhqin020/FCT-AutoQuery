"""
简化的案例跟踪服务
使用 cases 表中的状态字段来跟踪采集状态，替代复杂的跟踪表结构

状态值定义和处理规则：
- success: 已成功采集数据，跳过重复采集
- no_data: 确认案例无数据（仅在页面检测到'No data available in table'时设置），跳过重复采集
- failed: 采集失败，可以重试（受重试次数和时间间隔限制）
- pending: 待采集（默认状态），需要采集

注意：no_data 状态只有在页面采集时检测到'No data available in table'之后才能设置，
不能因为其他错误（如网络错误、解析错误等）就设置为 no_data。
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, List
import psycopg2
from psycopg2.extras import RealDictCursor

from lib.config import Config

logger = logging.getLogger(__name__)

# 状态常量
class CaseStatus:
    SUCCESS = 'success'      # 成功采集，跳过
    NO_DATA = 'no_data'      # 确认案例无数据（页面显示'No data available in table'），跳过
    FAILED = 'failed'        # 采集失败，可重试
    PENDING = 'pending'      # 待采集


class SimplifiedTrackingService:
    """简化的案例跟踪服务"""
    
    def __init__(self):
        self.db_config = {
            'host': Config.get_db_host(),
            'port': Config.get_db_port(),
            'database': Config.get_db_name(),
            'user': Config.get_db_user(),
            'password': Config.get_db_password()
        }
    
    def should_skip_case(self, case_number: str, force: bool = False) -> Tuple[bool, str]:
        """
        判断是否应该跳过某个案例的采集
        
        Args:
            case_number: 案例编号
            force: 是否强制重新采集
            
        Returns:
            Tuple[bool, str]: (是否跳过, 跳过原因)
        """
        if force:
            return False, ""
        
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT status, last_attempt_at, retry_count, error_message
                FROM cases 
                WHERE case_number = %s
            """, (case_number,))
            
            result = cursor.fetchone()
            
            if not result:
                # 案例不存在，需要采集
                return False, ""
            
            status = result['status']
            last_attempt = result['last_attempt_at']
            retry_count = result['retry_count']
            error_message = result['error_message']
            
            # 如果已经成功采集，跳过
            if status == CaseStatus.SUCCESS:
                logger.info(f"Skipping {case_number}: exists_in_db (status: success, retry_count: {retry_count})")
                return True, "already_collected"
            
            # 如果案例无数据且已确认，跳过
            if status == CaseStatus.NO_DATA:
                logger.info(f"Skipping {case_number}: exists_in_db (status: no_data, retry_count: {retry_count})")
                return True, "confirmed_no_data"
            
            # 如果状态是 pending，当作未采集处理，不能跳过
            if status == CaseStatus.PENDING:
                logger.info(f"Case {case_number}: status is pending, treating as uncollected")
                return False, ""
            
            # 不基于持久化的 retry_count 跳过失败案例。
            # 如果案例状态为 FAILED，我们仍然尝试重新采集（受冷却时间限制），
            # 并通过 get_failed_cases_for_retry 方法筛选可重试的失败案例。
            
            # 如果最近尝试过（冷却时间内），跳过以避免频繁重试
            if last_attempt:
                # Robustly compute time difference regardless of whether DB stored
                # timestamps with tzinfo. If last_attempt is naive, compare to
                # a naive local 'now'; otherwise, compare using UTC.
                if last_attempt.tzinfo is None:
                    now_local = datetime.now()
                    time_diff = (now_local - last_attempt).total_seconds()
                else:
                    now = datetime.now(timezone.utc)
                    last_attempt_utc = last_attempt.astimezone(timezone.utc)
                    time_diff = (now - last_attempt_utc).total_seconds()
                if time_diff < Config.get_retry_cooldown_seconds():
                    return True, f"recently_attempted ({int(time_diff/60)} minutes ago)"
            
            return False, ""
            
        except Exception as e:
            logger.warning(f"Failed to check skip status for {case_number}: {e}")
            return False, ""
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
    
    def get_case_info(self, case_number: str) -> Optional[dict]:
        """
        获取案例的详细信息
        
        Args:
            case_number: 案例编号
            
        Returns:
            Optional[dict]: 案例信息字典，如果不存在则返回None
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT status, last_attempt_at, retry_count, error_message, scraped_at
                FROM cases 
                WHERE case_number = %s
            """, (case_number,))
            
            result = cursor.fetchone()
            
            if result:
                return dict(result)
            else:
                return None
            
        except Exception as e:
            logger.error(f"Failed to get case info for {case_number}: {e}")
            return None
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
    
    def mark_case_attempt(self, case_number: str, status: str, error_message: Optional[str] = None):
        """
        标记案例采集尝试
        
        Args:
            case_number: 案例编号
            status: 状态 (success/failed/no_data)
            error_message: 错误信息（如果失败）
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            now = datetime.now(timezone.utc)
            
            if status == CaseStatus.SUCCESS:
                # 成功采集，重置重试计数
                cursor.execute("""
                    INSERT INTO cases (case_number, status, last_attempt_at, retry_count, scraped_at)
                    VALUES (%s, %s, %s, 0, %s)
                    ON CONFLICT (case_number) 
                    DO UPDATE SET 
                        status = EXCLUDED.status,
                        last_attempt_at = EXCLUDED.last_attempt_at,
                        retry_count = 0,
                        error_message = NULL,
                        scraped_at = EXCLUDED.scraped_at
                """, (case_number, status, now, now))
                
            elif status == CaseStatus.NO_DATA:
                # 确认案例无数据（仅在检测到'No data available in table'时设置）
                # Treat NO_DATA as definitive; reset retry counter and clear error_message
                cursor.execute("""
                    INSERT INTO cases (case_number, status, last_attempt_at, retry_count, error_message)
                    VALUES (%s, %s, %s, 0, NULL)
                    ON CONFLICT (case_number) 
                    DO UPDATE SET 
                        status = EXCLUDED.status,
                        last_attempt_at = EXCLUDED.last_attempt_at,
                        retry_count = 0,
                        error_message = NULL
                """, (case_number, status, now))
                
            elif status == CaseStatus.FAILED:
                # 采集失败，增加重试计数
                cursor.execute("""
                    INSERT INTO cases (case_number, status, last_attempt_at, retry_count, error_message)
                    VALUES (%s, %s, %s, 1, %s)
                    ON CONFLICT (case_number) 
                    DO UPDATE SET 
                        status = EXCLUDED.status,
                        last_attempt_at = EXCLUDED.last_attempt_at,
                        retry_count = cases.retry_count + 1,
                        error_message = EXCLUDED.error_message
                """, (case_number, status, now, error_message))
            
            conn.commit()
            logger.debug(f"Marked {case_number} as {status}")
            
        except Exception as e:
            logger.error(f"Failed to mark attempt for {case_number}: {e}")
            if 'conn' in locals():
                conn.rollback()
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
    
    def get_case_info(self, case_number: str) -> Optional[dict]:
        """
        获取案例的详细信息
        
        Args:
            case_number: 案例编号
            
        Returns:
            Optional[dict]: 案例信息字典，如果不存在则返回None
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT status, last_attempt_at, retry_count, error_message, scraped_at
                FROM cases 
                WHERE case_number = %s
            """, (case_number,))
            
            result = cursor.fetchone()
            
            if result:
                return dict(result)
            else:
                return None
            
        except Exception as e:
            logger.error(f"Failed to get case info for {case_number}: {e}")
            return None
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
    
    def get_failed_cases_for_retry(self, max_retry_count: Optional[int] = None, hours_since_last_attempt: Optional[int] = None) -> List[str]:
        """
        获取需要重试的失败案例列表
        
        Args:
            max_retry_count: 最大重试次数
            hours_since_last_attempt: 距离上次尝试的小时数
            
        Returns:
            List[str]: 需要重试的案例编号列表
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # 如果没有指定最大重试次数，使用配置中的默认值
            if max_retry_count is None:
                max_retry_count = Config.get_max_retries()
            
            # 如果没有指定时间间隔，使用配置中的默认值
            if hours_since_last_attempt is None:
                hours_since_last_attempt = Config.get_retry_hours_since_last_attempt()
            
            cursor.execute("""
                SELECT case_number 
                FROM cases 
                WHERE status = %s 
                AND retry_count < %s
                AND (last_attempt_at IS NULL OR last_attempt_at < NOW() - INTERVAL '%s hours')
                ORDER BY last_attempt_at ASC NULLS FIRST
                LIMIT 100
            """, (CaseStatus.FAILED, max_retry_count, hours_since_last_attempt))
            
            results = [row[0] for row in cursor.fetchall()]
            return results
            
        except Exception as e:
            logger.error(f"Failed to get failed cases for retry: {e}")
            return []
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
    
    def get_case_info(self, case_number: str) -> Optional[dict]:
        """
        获取案例的详细信息
        
        Args:
            case_number: 案例编号
            
        Returns:
            Optional[dict]: 案例信息字典，如果不存在则返回None
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT status, last_attempt_at, retry_count, error_message, scraped_at
                FROM cases 
                WHERE case_number = %s
            """, (case_number,))
            
            result = cursor.fetchone()
            
            if result:
                return dict(result)
            else:
                return None
            
        except Exception as e:
            logger.error(f"Failed to get case info for {case_number}: {e}")
            return None
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
    
    def get_statistics(self) -> dict:
        """获取采集统计信息"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    status,
                    COUNT(*) as count,
                    MAX(retry_count) as max_retries
                FROM cases 
                GROUP BY status
                ORDER BY count DESC
            """)
            
            stats = {}
            for row in cursor.fetchall():
                stats[row[0]] = {
                    'count': row[1],
                    'max_retries': row[2]
                }
            
            # 获取总数
            cursor.execute("SELECT COUNT(*) FROM cases")
            total_cases = cursor.fetchone()[0]
            
            return {
                'total_cases': total_cases,
                'by_status': stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {'total_cases': 0, 'by_status': {}}
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
    
    def get_case_info(self, case_number: str) -> Optional[dict]:
        """
        获取案例的详细信息
        
        Args:
            case_number: 案例编号
            
        Returns:
            Optional[dict]: 案例信息字典，如果不存在则返回None
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT status, last_attempt_at, retry_count, error_message, scraped_at
                FROM cases 
                WHERE case_number = %s
            """, (case_number,))
            
            result = cursor.fetchone()
            
            if result:
                return dict(result)
            else:
                return None
            
        except Exception as e:
            logger.error(f"Failed to get case info for {case_number}: {e}")
            return None
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()