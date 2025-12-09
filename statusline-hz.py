#!/usr/bin/env python3
"""
Claude Code Productivity Statusline
Displays code metrics, performance stats, and development context
Replaces weather data with actual coding productivity indicators
"""

import os
import sys
import json
import time
import fcntl
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import subprocess

# ===================== Constants =====================
# Time constants
SECONDS_PER_DAY = 86400
CACHE_EXPIRY_SECONDS = SECONDS_PER_DAY  # 24 hours
LOG_RETENTION_DAYS = 7

# Performance thresholds (for cumulative API time in session)
# These are higher than single-request thresholds since they're cumulative
PERF_FAST_MS = 10000       # < 10s cumulative = green (fast session)
PERF_MODERATE_MS = 60000   # < 60s cumulative = yellow (normal session)
# > 60s = red (long/slow session)

# Trend analysis threshold
TREND_THRESHOLD = 0.2  # 20% change triggers trend arrow

# Git settings
GIT_TIMEOUT_SECONDS = 1
GIT_CACHE_TTL_SECONDS = 5.0  # Cache git status for 5 seconds

# ===================== Colors =====================
class Colors:
    """ANSI color codes for terminal output (eye-friendly palette)"""

    _enabled = 'NO_COLOR' not in os.environ

    ORANGE = '\033[38;5;173m' if _enabled else ''   # Model name
    CYAN = '\033[38;5;87m' if _enabled else ''      # Cost/metrics
    DIM = '\033[2m' if _enabled else ''             # Secondary info
    GREEN = '\033[38;5;78m' if _enabled else ''     # Positive/fast
    YELLOW = '\033[38;5;185m' if _enabled else ''   # Warning/moderate
    RED = '\033[38;5;167m' if _enabled else ''      # Alert/slow
    RESET = '\033[0m' if _enabled else ''

    @classmethod
    def disable(cls):
        """Disable all colors"""
        cls.ORANGE = cls.CYAN = cls.DIM = ''
        cls.GREEN = cls.YELLOW = cls.RED = cls.RESET = ''

# ===================== Configuration =====================
class Config:
    """Configuration management for statusline"""

    VALID_LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'OFF']

    def __init__(self):
        # Cost Alert Configuration - with error handling
        try:
            self.cost_threshold = float(os.environ.get('STATUSLINE_COST_THRESHOLD', '0.50'))
            if self.cost_threshold < 0:
                self.cost_threshold = 0.50
        except (ValueError, TypeError):
            self.cost_threshold = 0.50  # Fallback to default

        # Cache directory for trends
        self.cache_dir_base = Path.home() / '.cache' / 'claude-statusline'
        self.stats_cache_file = self.cache_dir_base / 'session_stats.json'

        # Logging - default to WARNING for better performance
        log_level_str = os.environ.get('STATUSLINE_LOG_LEVEL', 'WARNING').upper()
        self.log_level = log_level_str if log_level_str in self.VALID_LOG_LEVELS else 'WARNING'
        self.log_dir = self.cache_dir_base / 'logs'

        # Debug Mode
        self.debug = os.environ.get('STATUSLINE_DEBUG', '0') == '1'

        # Color Output - also update Colors class
        self.no_color = 'NO_COLOR' in os.environ
        if self.no_color:
            Colors.disable()

    def ensure_directories(self) -> bool:
        """Ensure required directories exist (initialization)"""
        success = True
        try:
            self.cache_dir_base.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            logging.warning(f"Cache directory unavailable: {e}")
            success = False
        return success

    def is_valid(self) -> bool:
        """Check if configuration is valid"""
        if self.cost_threshold < 0:
            return False
        if self.log_level not in self.VALID_LOG_LEVELS:
            return False
        return True

# ===================== Logging Setup =====================
def _should_run_log_cleanup(log_dir: Path) -> bool:
    """Check if log cleanup should run (once per day)"""
    marker_file = log_dir / '.last_cleanup'
    try:
        if marker_file.exists():
            last_cleanup = marker_file.stat().st_mtime
            if time.time() - last_cleanup < SECONDS_PER_DAY:
                return False
    except OSError:
        pass
    return True


def _mark_cleanup_done(log_dir: Path):
    """Mark that cleanup was performed"""
    marker_file = log_dir / '.last_cleanup'
    try:
        marker_file.touch()
    except OSError:
        pass


def setup_logging(config: Config):
    """Setup logging system"""
    if config.log_level == 'OFF':
        logging.disable(logging.CRITICAL)
        return

    try:
        config.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = config.log_dir / f"statusline-{datetime.now().strftime('%Y%m%d')}.log"

        # Configure logging (log_level already validated in Config)
        logging.basicConfig(
            level=getattr(logging, config.log_level),
            format='[%(asctime)s] [%(levelname)s] [%(funcName)s] %(message)s',
            handlers=[logging.FileHandler(log_file)]
        )

        # Log rotation - only run once per day for performance
        if _should_run_log_cleanup(config.log_dir):
            retention_cutoff = time.time() - (LOG_RETENTION_DAYS * SECONDS_PER_DAY)
            for old_log in config.log_dir.glob("statusline-*.log*"):
                try:
                    if old_log.stat().st_mtime < retention_cutoff:
                        old_log.unlink()
                except (OSError, PermissionError):
                    pass  # Ignore errors deleting old logs
            _mark_cleanup_done(config.log_dir)

    except (OSError, PermissionError):
        # If logging setup fails, disable logging but continue
        logging.disable(logging.CRITICAL)

# ===================== Git Status Checker =====================
class GitStatusChecker:
    """Check git repository status with caching for performance"""

    # Cache: {cwd: (is_dirty, timestamp)}
    _cache: Dict[str, Tuple[bool, float]] = {}

    @classmethod
    def check_dirty_status(cls, cwd: str) -> bool:
        """Check if git repo has uncommitted changes (with caching)"""
        now = time.time()

        # Check cache first
        if cwd in cls._cache:
            is_dirty, cached_at = cls._cache[cwd]
            if now - cached_at < GIT_CACHE_TTL_SECONDS:
                return is_dirty

        # Cache miss or expired - perform actual check
        is_dirty = cls._check_dirty_impl(cwd)
        cls._cache[cwd] = (is_dirty, now)
        return is_dirty

    @staticmethod
    def _check_dirty_impl(cwd: str) -> bool:
        """Actual git dirty status check implementation"""
        try:
            git_dir = Path(cwd) / '.git'
            if not git_dir.exists():
                return False

            # Quick check using git status --porcelain
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT_SECONDS
            )

            # If output is not empty, there are uncommitted changes
            return bool(result.stdout.strip())

        except FileNotFoundError:
            logging.debug("Git command not found")
            return False
        except subprocess.TimeoutExpired:
            logging.debug("Git status check timed out")
            return False
        except (OSError, subprocess.SubprocessError) as e:
            logging.debug(f"Failed to check git status: {e}")
            return False

# ===================== Stats Tracker =====================
class StatsTracker:
    """Track code change trends across sessions"""

    def __init__(self, config: Config):
        self.config = config
        self.cache_file = config.stats_cache_file

    def _load_previous_stats(self) -> Optional[Dict[str, Any]]:
        """Load previous session stats from cache"""
        try:
            if self.cache_file.exists():
                cache_age = time.time() - self.cache_file.stat().st_mtime
                if cache_age < CACHE_EXPIRY_SECONDS:
                    with open(self.cache_file, 'r') as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                        data = json.load(f)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        return data
        except (json.JSONDecodeError, OSError, IOError) as e:
            logging.debug(f"Failed to load previous stats: {e}")
        return None

    def _save_current_stats(self, lines_added: int, lines_removed: int):
        """Save current session stats to cache with file locking"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'lines_added': lines_added,
                'lines_removed': lines_removed,
                'timestamp': time.time()
            }

            # Use temp file + atomic rename for safety
            temp_file = self.cache_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            temp_file.rename(self.cache_file)

        except (OSError, IOError) as e:
            logging.debug(f"Failed to save stats: {e}")

    def calculate_trend(self, current_added: int, current_removed: int) -> str:
        """Calculate trend arrow (pure function, no side effects)"""
        prev = self._load_previous_stats()

        if not prev:
            return ' (new)'  # First session indicator

        current_total = current_added + current_removed
        prev_total = prev.get('lines_added', 0) + prev.get('lines_removed', 0)

        if prev_total == 0:
            return ' ↗' if current_total > 0 else ''

        ratio = current_total / prev_total
        if ratio > 1 + TREND_THRESHOLD:
            return ' ↗'
        elif ratio < 1 - TREND_THRESHOLD:
            return ' ↘'
        return ' →'

    def save_session_stats(self, lines_added: int, lines_removed: int):
        """Save current session stats (explicit side effect)"""
        self._save_current_stats(lines_added, lines_removed)

    def get_trend_and_save(self, current_added: int, current_removed: int) -> str:
        """Get trend arrow and save stats (combined operation with clear naming)"""
        trend = self.calculate_trend(current_added, current_removed)
        self.save_session_stats(current_added, current_removed)
        return trend

# ===================== Claude Context Parser =====================
def parse_claude_context() -> Dict[str, Any]:
    """Parse Claude Code context from stdin - enhanced with productivity metrics"""
    result = {
        'model': 'Claude',
        'dir': '.',
        'cwd': '.',
        'branch': '',
        'detached': False,  # True if in detached HEAD state
        'cost_usd': 0.0,
        'cost_str': None,
        'duration': None,
        'lines_added': 0,
        'lines_removed': 0,
        'api_duration_ms': 0
    }

    try:
        input_data = sys.stdin.read()
        if input_data:
            data = json.loads(input_data)

            # Parse model
            if 'model' in data:
                result['model'] = data['model'].get('display_name') or data['model'].get('id', 'Claude')

            # Parse directory
            if 'workspace' in data:
                cwd = data['workspace'].get('current_dir', '.')
                result['cwd'] = cwd
                result['dir'] = Path(cwd).name

                # Check for git branch (handle detached HEAD)
                git_head = Path(cwd) / '.git' / 'HEAD'
                if git_head.exists():
                    try:
                        content = git_head.read_text().strip()
                        if content.startswith('ref: '):
                            # Normal branch reference
                            result['branch'] = content.split('/')[-1]
                        else:
                            # Detached HEAD - show short commit hash
                            result['branch'] = content[:7]
                            result['detached'] = True
                    except (OSError, IOError):
                        pass

            # Parse cost metrics
            if 'cost' in data:
                # Cost in USD
                cost_usd = data['cost'].get('total_cost_usd') or data['cost'].get('usd')
                if cost_usd is not None:
                    result['cost_usd'] = float(cost_usd)
                    result['cost_str'] = f"${cost_usd:.3f}"

                # Parse duration (handle both ms and sec formats)
                duration_value = data['cost'].get('total_duration_ms') or data['cost'].get('duration_sec')
                if duration_value is not None and duration_value > 0:
                    # Convert to seconds if value was in milliseconds
                    if data['cost'].get('total_duration_ms'):
                        duration_seconds = duration_value / 1000
                    else:
                        duration_seconds = duration_value

                    minutes = int(duration_seconds // 60)
                    if minutes > 0:
                        result['duration'] = f"{minutes}m"
                    else:
                        seconds = int(duration_seconds)
                        result['duration'] = f"{seconds}s"

                # Parse code change stats
                lines_added = data['cost'].get('total_lines_added')
                if lines_added is not None:
                    result['lines_added'] = int(lines_added)

                lines_removed = data['cost'].get('total_lines_removed')
                if lines_removed is not None:
                    result['lines_removed'] = int(lines_removed)

                # Parse API performance (cumulative time)
                api_duration = data['cost'].get('total_api_duration_ms')
                if api_duration is not None:
                    result['api_duration_ms'] = int(api_duration)

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logging.debug(f"Failed to parse Claude context: {e}")

    return result

# ===================== Main Function =====================
def main():
    """Main entry point - Productivity-focused statusline"""
    # Initialize configuration
    config = Config()

    # Setup logging
    setup_logging(config)
    logging.info("Productivity StatusLine started")

    # Ensure directories exist and validate config
    config.ensure_directories()
    if not config.is_valid():
        print("ERROR: Configuration invalid")
        sys.exit(1)

    # Parse Claude context
    context = parse_claude_context()
    logging.debug(f"Context: {context}")

    # Check git dirty status
    is_dirty = GitStatusChecker.check_dirty_status(context['cwd'])

    # Get code change trend (using renamed method with clear semantics)
    tracker = StatsTracker(config)
    trend_arrow = tracker.get_trend_and_save(context['lines_added'], context['lines_removed'])

    # Build header with current time
    current_time = datetime.now().strftime('%H:%M')
    header = f"⏰ {current_time}"

    # Add model info
    header += f" | {Colors.ORANGE}{context['model']}{Colors.RESET}"

    # Add directory and branch with dirty indicator
    header += f" {Colors.DIM}{context['dir']}{Colors.RESET}"
    if context['branch']:
        if context.get('detached'):
            # Detached HEAD - show with @ prefix
            header += f":{Colors.DIM}@{context['branch']}{Colors.RESET}"
        else:
            header += f":{context['branch']}"
        if is_dirty:
            header += f"{Colors.RED}●{Colors.RESET}"  # Enhanced dirty indicator

    # Add cost metrics with alert if threshold exceeded
    metrics = []
    if context.get('cost_str'):
        cost_display = context['cost_str']
        if context['cost_usd'] > config.cost_threshold:
            cost_display += f" {Colors.RED}⚠️{Colors.RESET}"
        metrics.append(f"{Colors.CYAN}{cost_display}{Colors.RESET}")

    if context.get('duration'):
        metrics.append(f"{Colors.CYAN}{context['duration']}{Colors.RESET}")

    if metrics:
        header += f" [{' '.join(metrics)}]"

    # Build productivity metrics part
    productivity_parts = []

    # Code change statistics
    lines_added = context['lines_added']
    lines_removed = context['lines_removed']
    if lines_added > 0 or lines_removed > 0:
        code_stats = f"{Colors.GREEN}📝 +{lines_added}/-{lines_removed}{trend_arrow}{Colors.RESET}"
        productivity_parts.append(code_stats)
    else:
        # Simplified "no changes" display
        productivity_parts.append(f"{Colors.DIM}📝 0/0{trend_arrow}{Colors.RESET}")

    # API performance indicator (using cumulative thresholds)
    api_duration = context['api_duration_ms']
    if api_duration > 0:
        # Format API duration nicely
        if api_duration < 1000:
            api_str = f"{api_duration}ms"
        elif api_duration < 60000:
            api_str = f"{api_duration/1000:.1f}s"
        else:
            # Show minutes for very long sessions
            api_str = f"{api_duration/60000:.1f}m"

        # Color based on cumulative performance thresholds
        if api_duration < PERF_FAST_MS:
            perf_display = f"{Colors.GREEN}⚡{api_str}{Colors.RESET}"
        elif api_duration < PERF_MODERATE_MS:
            perf_display = f"{Colors.YELLOW}⚡{api_str}{Colors.RESET}"
        else:
            perf_display = f"{Colors.RED}⚡{api_str}{Colors.RESET}"

        productivity_parts.append(perf_display)

    # Combine all parts
    if productivity_parts:
        output = f"{header} | {' | '.join(productivity_parts)}"
    else:
        output = f"{header} | {Colors.DIM}Initializing...{Colors.RESET}"

    # Output (first line only, as per official docs)
    print(output)

    logging.info(f"Productivity status displayed: +{lines_added}/-{lines_removed}, API: {api_duration}ms")
    logging.info("Execution completed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"ERROR: {e}")
        sys.exit(1)