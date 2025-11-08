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
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import subprocess

# ===================== Configuration =====================
class Config:
    """Configuration management for statusline"""
    
    def __init__(self):
        # Cost Alert Configuration - with error handling
        try:
            self.cost_threshold = float(os.environ.get('STATUSLINE_COST_THRESHOLD', '0.50'))
        except (ValueError, TypeError):
            self.cost_threshold = 0.50  # Fallback to default

        # Cache directory for trends
        self.cache_dir_base = Path.home() / '.cache' / 'claude-statusline'
        self.stats_cache_file = self.cache_dir_base / 'session_stats.json'

        # Logging - default to WARNING for better performance
        log_level_str = os.environ.get('STATUSLINE_LOG_LEVEL', 'WARNING').upper()
        # Validate log level
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'OFF']
        self.log_level = log_level_str if log_level_str in valid_levels else 'WARNING'
        self.log_dir = Path.home() / '.cache' / 'claude-statusline' / 'logs'

        # Debug Mode
        self.debug = os.environ.get('STATUSLINE_DEBUG', '0') == '1'

        # Color Output
        self.no_color = 'NO_COLOR' in os.environ

    def validate(self) -> bool:
        """Validate configuration"""
        # Ensure cache directory exists
        try:
            self.cache_dir_base.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            # If we can't create cache dir, continue without it
            logging.warning(f"Failed to create cache directory: {e}")
        return True

# ===================== Logging Setup =====================
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

        # Log rotation (simple version - delete old logs)
        for old_log in config.log_dir.glob("statusline-*.log*"):
            try:
                if old_log.stat().st_mtime < time.time() - (7 * 86400):  # 7 days
                    old_log.unlink()
            except (OSError, PermissionError):
                pass  # Ignore errors deleting old logs

    except (OSError, PermissionError):
        # If logging setup fails, disable logging but continue
        logging.disable(logging.CRITICAL)

# ===================== Git Status Checker =====================
class GitStatusChecker:
    """Check git repository status"""

    @staticmethod
    def check_dirty_status(cwd: str) -> bool:
        """Check if git repo has uncommitted changes"""
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
                timeout=1
            )

            # If output is not empty, there are uncommitted changes
            return bool(result.stdout.strip())

        except FileNotFoundError:
            # Git is not installed or not in PATH
            logging.debug("Git command not found")
            return False
        except subprocess.TimeoutExpired:
            # Git command took too long
            logging.debug("Git status check timed out")
            return False
        except Exception as e:
            logging.debug(f"Failed to check git status: {e}")
            return False

# ===================== Stats Tracker =====================
class StatsTracker:
    """Track code change trends across sessions"""

    def __init__(self, config: Config):
        self.config = config
        self.cache_file = config.stats_cache_file

    def _load_previous_stats(self) -> Optional[Dict[str, int]]:
        """Load previous session stats from cache"""
        try:
            if self.cache_file.exists():
                # Check if cache is from today
                cache_age = time.time() - self.cache_file.stat().st_mtime
                if cache_age < 86400:  # 24 hours
                    data = json.loads(self.cache_file.read_text())
                    return data
        except Exception as e:
            logging.debug(f"Failed to load previous stats: {e}")
        return None

    def _save_current_stats(self, lines_added: int, lines_removed: int):
        """Save current session stats to cache"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'lines_added': lines_added,
                'lines_removed': lines_removed,
                'timestamp': time.time()
            }
            self.cache_file.write_text(json.dumps(data))
        except Exception as e:
            logging.debug(f"Failed to save stats: {e}")

    def get_trend_arrow(self, current_added: int, current_removed: int) -> str:
        """Calculate trend arrow based on comparison with previous session"""
        prev = self._load_previous_stats()

        # Save current stats for next time
        self._save_current_stats(current_added, current_removed)

        if not prev:
            return ''  # No previous data to compare

        # Calculate total lines changed
        current_total = current_added + current_removed
        prev_total = prev.get('lines_added', 0) + prev.get('lines_removed', 0)

        if current_total > prev_total * 1.2:  # 20% more changes
            return ' ↗'
        elif current_total < prev_total * 0.8:  # 20% fewer changes
            return ' ↘'
        else:
            return ' →'  # Similar activity level

# ===================== Claude Context Parser =====================
def parse_claude_context() -> Dict[str, Any]:
    """Parse Claude Code context from stdin - enhanced with productivity metrics"""
    result = {
        'model': 'Claude',
        'dir': '.',
        'cwd': '.',
        'branch': '',
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

                # Check for git branch
                git_head = Path(cwd) / '.git' / 'HEAD'
                if git_head.exists():
                    content = git_head.read_text().strip()
                    if content.startswith('ref: '):
                        result['branch'] = content.split('/')[-1]

            # Parse cost metrics (important for tracking usage)
            if 'cost' in data:
                # Cost in USD
                cost_usd = data['cost'].get('total_cost_usd') or data['cost'].get('usd')
                if cost_usd is not None:
                    result['cost_usd'] = float(cost_usd)
                    result['cost_str'] = f"${cost_usd:.3f}"

                # Parse duration - show seconds if less than 1 minute
                duration_sec = data['cost'].get('total_duration_ms') or data['cost'].get('duration_sec')
                if duration_sec is not None and duration_sec > 0:
                    # Handle both ms and sec
                    if data['cost'].get('total_duration_ms'):
                        duration_sec = duration_sec / 1000

                    minutes = int(duration_sec // 60)
                    if minutes > 0:
                        result['duration'] = f"{minutes}m"
                    else:
                        # Show seconds for sessions under 1 minute
                        seconds = int(duration_sec)
                        result['duration'] = f"{seconds}s"

                # Parse code change stats (THE COOLEST METRICS!)
                lines_added = data['cost'].get('total_lines_added')
                if lines_added is not None:
                    result['lines_added'] = int(lines_added)

                lines_removed = data['cost'].get('total_lines_removed')
                if lines_removed is not None:
                    result['lines_removed'] = int(lines_removed)

                # Parse API performance
                api_duration = data['cost'].get('total_api_duration_ms')
                if api_duration is not None:
                    result['api_duration_ms'] = int(api_duration)

    except Exception as e:
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

    # Validate configuration
    if not config.validate():
        print("ERROR: Configuration invalid")
        sys.exit(1)

    # Parse Claude context
    context = parse_claude_context()
    logging.debug(f"Context: {context}")

    # Check git dirty status
    is_dirty = GitStatusChecker.check_dirty_status(context['cwd'])

    # Get code change trend
    tracker = StatsTracker(config)
    trend_arrow = tracker.get_trend_arrow(context['lines_added'], context['lines_removed'])

    # Format output with colors
    if not config.no_color:
        ORANGE = '\033[38;5;208m'    # Model name
        CYAN = '\033[38;5;51m'       # Cost/metrics
        DIM = '\033[2m'              # Directory
        GREEN = '\033[38;5;46m'      # Code stats
        YELLOW = '\033[38;5;226m'    # Performance
        RED = '\033[38;5;196m'       # Warning
        RESET = '\033[0m'
    else:
        ORANGE = CYAN = DIM = GREEN = YELLOW = RED = RESET = ''

    # Build header with current time
    current_time = datetime.now().strftime('%H:%M')
    header = f"⏰ {current_time}"

    # Add model info
    header += f" | {ORANGE}{context['model']}{RESET}"

    # Add directory and branch with dirty indicator
    header += f" {DIM}{context['dir']}{RESET}"
    if context['branch']:
        header += f":{context['branch']}"
        if is_dirty:
            header += f"{RED}*{RESET}"  # Dirty indicator

    # Add cost metrics with alert if threshold exceeded
    metrics = []
    if context.get('cost_str'):
        cost_display = context['cost_str']
        # Add warning if cost exceeds threshold
        if context['cost_usd'] > config.cost_threshold:
            cost_display += f" {RED}⚠️{RESET}"
        metrics.append(f"{CYAN}{cost_display}{RESET}")

    if context.get('duration'):
        metrics.append(f"{CYAN}{context['duration']}{RESET}")

    if metrics:
        header += f" [{' '.join(metrics)}]"

    # Build productivity metrics part
    productivity_parts = []

    # Code change statistics (THE STAR OF THE SHOW!)
    lines_added = context['lines_added']
    lines_removed = context['lines_removed']
    if lines_added > 0 or lines_removed > 0:
        code_stats = f"{GREEN}📝 +{lines_added}/-{lines_removed}{trend_arrow}{RESET}"
        productivity_parts.append(code_stats)
    else:
        productivity_parts.append(f"{DIM}📝 No changes yet{RESET}")

    # API performance indicator
    api_duration = context['api_duration_ms']
    if api_duration > 0:
        # Format API duration nicely
        if api_duration < 1000:
            api_str = f"{api_duration}ms"
        else:
            api_str = f"{api_duration/1000:.1f}s"

        # Color based on performance (green=fast, yellow=ok, red=slow)
        if api_duration < 500:
            perf_display = f"{GREEN}⚡{api_str}{RESET}"
        elif api_duration < 2000:
            perf_display = f"{YELLOW}⚡{api_str}{RESET}"
        else:
            perf_display = f"{RED}⚡{api_str}{RESET}"

        productivity_parts.append(perf_display)

    # Combine all parts
    if productivity_parts:
        output = f"{header} | {' | '.join(productivity_parts)}"
    else:
        output = f"{header} | {DIM}Initializing...{RESET}"

    # Output (first line only, as per official docs)
    print(output)

    logging.info(f"Productivity status displayed: +{lines_added}/-{lines_removed}, API: {api_duration}ms")
    logging.info("Execution completed")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"ERROR: {e}")
        sys.exit(1)