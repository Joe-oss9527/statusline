#!/usr/bin/env python3
"""
Unit tests for Claude Code Productivity Statusline
"""

import unittest
import json
import os
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import module by executing it (since it has a hyphen in the name)
import importlib.util
spec = importlib.util.spec_from_file_location("statusline", Path(__file__).parent.parent / "statusline-hz.py")
statusline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(statusline)


class TestConstants(unittest.TestCase):
    """Test that constants are properly defined"""

    def test_time_constants(self):
        self.assertEqual(statusline.SECONDS_PER_DAY, 86400)
        self.assertEqual(statusline.CACHE_EXPIRY_SECONDS, 86400)
        self.assertEqual(statusline.LOG_RETENTION_DAYS, 7)

    def test_performance_thresholds(self):
        self.assertEqual(statusline.PERF_FAST_MS, 10000)
        self.assertEqual(statusline.PERF_MODERATE_MS, 60000)

    def test_trend_threshold(self):
        self.assertEqual(statusline.TREND_THRESHOLD, 0.2)

    def test_git_settings(self):
        self.assertEqual(statusline.GIT_TIMEOUT_SECONDS, 1)
        self.assertEqual(statusline.GIT_CACHE_TTL_SECONDS, 5.0)


class TestColors(unittest.TestCase):
    """Test Colors class functionality"""

    def test_colors_defined(self):
        """Verify all color codes are defined"""
        self.assertIsNotNone(statusline.Colors.ORANGE)
        self.assertIsNotNone(statusline.Colors.CYAN)
        self.assertIsNotNone(statusline.Colors.DIM)
        self.assertIsNotNone(statusline.Colors.GREEN)
        self.assertIsNotNone(statusline.Colors.YELLOW)
        self.assertIsNotNone(statusline.Colors.RED)
        self.assertIsNotNone(statusline.Colors.RESET)

    def test_disable_colors(self):
        """Test that disable() clears all colors"""
        # Save original values
        original_orange = statusline.Colors.ORANGE

        statusline.Colors.disable()

        self.assertEqual(statusline.Colors.ORANGE, '')
        self.assertEqual(statusline.Colors.RESET, '')

        # Restore (for other tests)
        statusline.Colors.ORANGE = original_orange


class TestConfig(unittest.TestCase):
    """Test Config class"""

    def test_default_values(self):
        """Test default configuration values"""
        with patch.dict(os.environ, {}, clear=True):
            config = statusline.Config()
            self.assertEqual(config.cost_threshold, 0.50)
            self.assertEqual(config.log_level, 'WARNING')
            self.assertFalse(config.debug)

    def test_custom_cost_threshold(self):
        """Test custom cost threshold from environment"""
        with patch.dict(os.environ, {'STATUSLINE_COST_THRESHOLD': '1.25'}):
            config = statusline.Config()
            self.assertEqual(config.cost_threshold, 1.25)

    def test_invalid_cost_threshold_fallback(self):
        """Test fallback for invalid cost threshold"""
        with patch.dict(os.environ, {'STATUSLINE_COST_THRESHOLD': 'invalid'}):
            config = statusline.Config()
            self.assertEqual(config.cost_threshold, 0.50)

    def test_negative_cost_threshold_fallback(self):
        """Test fallback for negative cost threshold"""
        with patch.dict(os.environ, {'STATUSLINE_COST_THRESHOLD': '-5'}):
            config = statusline.Config()
            self.assertEqual(config.cost_threshold, 0.50)

    def test_valid_log_levels(self):
        """Test valid log level configuration"""
        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'OFF']:
            with patch.dict(os.environ, {'STATUSLINE_LOG_LEVEL': level}):
                config = statusline.Config()
                self.assertEqual(config.log_level, level)

    def test_invalid_log_level_fallback(self):
        """Test fallback for invalid log level"""
        with patch.dict(os.environ, {'STATUSLINE_LOG_LEVEL': 'INVALID'}):
            config = statusline.Config()
            self.assertEqual(config.log_level, 'WARNING')

    def test_debug_mode(self):
        """Test debug mode configuration"""
        with patch.dict(os.environ, {'STATUSLINE_DEBUG': '1'}):
            config = statusline.Config()
            self.assertTrue(config.debug)

    def test_is_valid(self):
        """Test configuration validation"""
        config = statusline.Config()
        self.assertTrue(config.is_valid())


class TestParseClaudeContext(unittest.TestCase):
    """Test parse_claude_context function"""

    def test_parse_valid_json(self):
        """Test parsing valid Claude context JSON"""
        mock_input = json.dumps({
            'model': {'display_name': 'Sonnet 4.5'},
            'workspace': {'current_dir': '/test/path'},
            'cost': {
                'total_cost_usd': 0.125,
                'total_duration_ms': 300000,
                'total_lines_added': 100,
                'total_lines_removed': 50,
                'total_api_duration_ms': 5000
            }
        })

        with patch('sys.stdin', StringIO(mock_input)):
            result = statusline.parse_claude_context()

        self.assertEqual(result['model'], 'Sonnet 4.5')
        self.assertEqual(result['lines_added'], 100)
        self.assertEqual(result['lines_removed'], 50)
        self.assertEqual(result['cost_usd'], 0.125)
        self.assertEqual(result['api_duration_ms'], 5000)
        self.assertEqual(result['duration'], '5m')

    def test_parse_empty_input(self):
        """Test parsing empty input"""
        with patch('sys.stdin', StringIO('')):
            result = statusline.parse_claude_context()

        self.assertEqual(result['model'], 'Claude')
        self.assertEqual(result['lines_added'], 0)

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON gracefully"""
        with patch('sys.stdin', StringIO('not valid json')):
            result = statusline.parse_claude_context()

        self.assertEqual(result['model'], 'Claude')

    def test_duration_under_one_minute(self):
        """Test duration formatting for sessions under 1 minute"""
        mock_input = json.dumps({
            'cost': {'total_duration_ms': 45000}  # 45 seconds
        })

        with patch('sys.stdin', StringIO(mock_input)):
            result = statusline.parse_claude_context()

        self.assertEqual(result['duration'], '45s')


class TestStatsTracker(unittest.TestCase):
    """Test StatsTracker class"""

    def setUp(self):
        """Create temporary directory for cache"""
        self.temp_dir = tempfile.mkdtemp()
        self.config = MagicMock()
        self.config.stats_cache_file = Path(self.temp_dir) / 'session_stats.json'
        self.tracker = statusline.StatsTracker(self.config)

    def tearDown(self):
        """Clean up temporary directory"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_first_session_indicator(self):
        """Test that first session shows (new) indicator"""
        trend = self.tracker.calculate_trend(100, 50)
        self.assertEqual(trend, ' (new)')

    def test_trend_increase(self):
        """Test trend arrow for increased activity"""
        # Save first session
        self.tracker.save_session_stats(100, 50)

        # Second session with more changes (>20% increase)
        trend = self.tracker.calculate_trend(200, 100)
        self.assertEqual(trend, ' ↗')

    def test_trend_decrease(self):
        """Test trend arrow for decreased activity"""
        # Save first session with high activity
        self.tracker.save_session_stats(200, 100)

        # Second session with fewer changes (>20% decrease)
        trend = self.tracker.calculate_trend(50, 25)
        self.assertEqual(trend, ' ↘')

    def test_trend_similar(self):
        """Test trend arrow for similar activity"""
        # Save first session
        self.tracker.save_session_stats(100, 50)

        # Second session with similar changes (within 20%)
        trend = self.tracker.calculate_trend(110, 55)
        self.assertEqual(trend, ' →')


class TestGitStatusChecker(unittest.TestCase):
    """Test GitStatusChecker class"""

    def test_non_git_directory(self):
        """Test behavior in non-git directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = statusline.GitStatusChecker.check_dirty_status(temp_dir)
            self.assertFalse(result)

    def test_cache_behavior(self):
        """Test that git status is cached"""
        # Clear cache
        statusline.GitStatusChecker._cache.clear()

        with tempfile.TemporaryDirectory() as temp_dir:
            # First call
            result1 = statusline.GitStatusChecker.check_dirty_status(temp_dir)

            # Second call should use cache
            result2 = statusline.GitStatusChecker.check_dirty_status(temp_dir)

            self.assertEqual(result1, result2)
            # Verify cache was used
            self.assertIn(temp_dir, statusline.GitStatusChecker._cache)


class TestLoggingSetup(unittest.TestCase):
    """Test logging setup functions"""

    def test_should_run_cleanup_first_time(self):
        """Test that cleanup should run on first execution"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = statusline._should_run_log_cleanup(Path(temp_dir))
            self.assertTrue(result)

    def test_cleanup_marker(self):
        """Test cleanup marker file creation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            statusline._mark_cleanup_done(log_dir)

            marker = log_dir / '.last_cleanup'
            self.assertTrue(marker.exists())


if __name__ == '__main__':
    unittest.main()
