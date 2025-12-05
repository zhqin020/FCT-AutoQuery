"""Tests for enhanced statistics service."""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from src.services.enhanced_statistics_service import EnhancedStatisticsService


class TestEnhancedStatisticsService(unittest.TestCase):
    """Test cases for EnhancedStatisticsService."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = EnhancedStatisticsService()

    @patch('src.services.enhanced_statistics_service.psycopg2.connect')
    def test_get_year_statistics_success(self, mock_connect):
        """Test successful retrieval of year statistics."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock status query results - need to handle multiple execute() calls
        status_results = [('success', 100, 0, 0.0), ('failed', 20, 5, 2.5), ('no_data', 30, 0, 0.0)]
        timing_results = [(datetime(2023, 1, 1), datetime(2023, 12, 31), datetime(2023, 1, 2), 100)]
        retry_results = [(3, 10), (2, 5)]
        
        # Set up the cursor to return different results for different queries
        mock_cursor.fetchall.side_effect = [status_results, timing_results, retry_results]
        
        stats = self.service.get_year_statistics(2021)
        
        # Verify structure
        self.assertEqual(stats['year'], 2021)
        self.assertEqual(stats['total_cases'], 150)  # 100 + 20 + 30
        self.assertEqual(stats['success_count'], 100)
        self.assertEqual(stats['failed_count'], 20)
        self.assertEqual(stats['no_data_count'], 30)
        self.assertEqual(stats['other_count'], 0)
        
        # Verify status breakdown
        self.assertIn('success', stats['by_status'])
        self.assertIn('failed', stats['by_status'])
        self.assertIn('no_data', stats['by_status'])
        
        self.assertEqual(stats['by_status']['success']['count'], 100)
        self.assertEqual(stats['by_status']['failed']['count'], 20)
        self.assertEqual(stats['by_status']['no_data']['count'], 30)

    @patch('src.services.enhanced_statistics_service.psycopg2.connect')
    def test_get_year_statistics_database_error(self, mock_connect):
        """Test handling of database errors."""
        mock_connect.side_effect = Exception("Database connection failed")
        
        stats = self.service.get_year_statistics(2021)
        
        # Should return error state
        self.assertEqual(stats['year'], 2021)
        self.assertEqual(stats['total_cases'], 0)
        self.assertIn('error', stats)

    def test_format_statistics_for_display(self):
        """Test formatting of statistics for display."""
        test_stats = {
            'year': 2021,
            'total_cases': 150,
            'success_count': 100,
            'failed_count': 20,
            'no_data_count': 30,
            'other_count': 0,
            'by_status': {
                'success': {'count': 100, 'max_retries': 0, 'avg_retries': 0.0},
                'failed': {'count': 20, 'max_retries': 5, 'avg_retries': 2.5}
            },
            'start_time': datetime(2023, 1, 1, 10, 0, 0),
            'end_time': datetime(2023, 1, 1, 11, 0, 0),
            'duration_seconds': 3600.0,
            'upper_bound': 500,
            'processed_count': 200,
            'probes_used': 25
        }
        
        formatted = self.service.format_statistics_for_display(test_stats, "Test Statistics")
        
        # Verify key elements are present
        self.assertIn("Test Statistics", formatted)
        self.assertIn("年份 (Year): 2021", formatted)
        self.assertIn("总计案例 (Total Cases): 150", formatted)
        self.assertIn("状态分布 (Status Distribution):", formatted)
        self.assertIn("success: 100 案例", formatted)
        self.assertIn("failed: 20 案例", formatted)
        self.assertIn("汇总统计 (Summary):", formatted)
        self.assertIn("成功 (Success): 100", formatted)
        self.assertIn("失败 (Failed): 20", formatted)
        self.assertIn("无数据 (No Data): 30", formatted)
        self.assertIn("时间信息 (Timing):", formatted)
        self.assertIn("运行信息 (Run Information):", formatted)
        self.assertIn("上边界编号: 500", formatted)

    @patch('src.services.enhanced_statistics_service.psycopg2.connect')
    def test_calculate_run_statistics(self, mock_connect):
        """Test calculation of run statistics."""
        # Mock the get_year_statistics call
        with patch.object(self.service, 'get_year_statistics') as mock_get_stats:
            mock_get_stats.return_value = {
                'year': 2021,
                'total_cases': 150,
                'success_count': 100,
                'failed_count': 20,
                'no_data_count': 30,
                'other_count': 0
            }
            
            start_time = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
            end_time = datetime(2023, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
            
            run_stats = self.service.calculate_run_statistics(
                year=2021,
                start_time=start_time,
                end_time=end_time,
                upper_bound=500,
                processed_count=200,
                probes_used=25,
                cases_collected=100,
                run_id="test_run_123"
            )
            
            # Verify run-specific fields
            self.assertEqual(run_stats['run_id'], "test_run_123")
            self.assertEqual(run_stats['year'], 2021)
            self.assertEqual(run_stats['start_time'], start_time)
            self.assertEqual(run_stats['end_time'], end_time)
            self.assertEqual(run_stats['duration_seconds'], 3600.0)
            self.assertEqual(run_stats['upper_bound'], 500)
            self.assertEqual(run_stats['processed_count'], 200)
            self.assertEqual(run_stats['probes_used'], 25)
            self.assertEqual(run_stats['cases_collected'], 100)
            self.assertEqual(run_stats['success_rate'], 50.0)  # 100/200 * 100
            
            # Verify that year statistics are included
            self.assertEqual(run_stats['total_cases'], 150)
            self.assertEqual(run_stats['success_count'], 100)

    @patch('builtins.print')
    @patch('src.services.enhanced_statistics_service.logger')
    def test_log_and_display_statistics(self, mock_logger, mock_print):
        """Test logging and display of statistics."""
        test_stats = {
            'year': 2021,
            'total_cases': 150,
            'success_count': 100,
            'failed_count': 20,
            'no_data_count': 30,
            'other_count': 0
        }
        
        self.service.log_and_display_statistics(test_stats, "Test Stats")
        
        # Verify print was called
        mock_print.assert_called_once()
        
        # Verify logger was called
        mock_logger.info.assert_called_once()
        
        # Check that the formatted stats contain expected content
        call_args = mock_print.call_args[0][0]
        self.assertIn("Test Stats", call_args)
        self.assertIn("2021", call_args)
        self.assertIn("150", call_args)


if __name__ == '__main__':
    unittest.main()