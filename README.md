# Claude Code Productivity Statusline

A productivity-focused statusline for [Claude Code](https://code.claude.com/docs/en/statusline) that displays coding metrics, performance statistics, and development context.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)

## Overview

This statusline transforms Claude Code's status bar into a developer productivity dashboard, showing real-time metrics that matter for coding: code changes, API performance, cost tracking, and git status.

## Quick Start

```bash
# 1. Copy the script
cp statusline-hz.py ~/.claude/

# 2. Make it executable
chmod +x ~/.claude/statusline-hz.py

# 3. Configure Claude Code (see Configuration section)

# 4. Restart Claude Code
```

## Example Output

```
⏰ 14:30 | Sonnet 4.5 statusline:main* [$0.125 5m] | 📝 +127/-43 ↗ | ⚡230ms
```

**Output Breakdown:**

| Element | Description |
|---------|-------------|
| `⏰ 14:30` | Current time |
| `Sonnet 4.5` | AI model name (color: orange) |
| `statusline:main*` | Directory:branch (dirty indicator `*`) |
| `[$0.125 5m]` | Session cost and duration (color: cyan) |
| `📝 +127/-43 ↗` | Lines added/removed with trend arrow (color: green) |
| `⚡230ms` | API response time (color-coded by speed) |

## Features

### Core Metrics

- **Code Change Statistics** - Real-time tracking of lines added/removed
- **API Performance Monitoring** - Response time with color-coded indicators
- **Cost Tracking** - Session cost with configurable threshold alerts
- **Session Duration** - Time spent in current session (shows seconds if < 1 minute)
- **Git Status** - Branch name with uncommitted changes indicator

### Advanced Features

- **Trend Analysis** - Compare current session with previous (`↗` increased, `→` similar, `↘` decreased)
- **Cost Alerts** - Warning emoji `⚠️` when cost exceeds threshold
- **Smart Color Coding** - Visual hierarchy for quick information parsing
- **Graceful Degradation** - Works even without git or with invalid configuration

## Requirements

- **Python**: 3.7 or higher
- **Claude Code**: Latest version (tested on v1.2.0+)
- **Git** (optional): For branch and dirty status display
- **Dependencies**: Standard library only (no external packages required)

## Installation

### Step 1: Copy Script

```bash
cp statusline-hz.py ~/.claude/
chmod +x ~/.claude/statusline-hz.py
```

### Step 2: Configure Claude Code

Edit your `.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline-hz.py",
    "padding": 0
  },
  "env": {
    "STATUSLINE_COST_THRESHOLD": "0.50",
    "STATUSLINE_LOG_LEVEL": "WARNING",
    "STATUSLINE_DEBUG": "0"
  }
}
```

### Step 3: Restart Claude Code

The statusline will appear at the bottom of your Claude Code interface.

## Configuration

### Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `STATUSLINE_COST_THRESHOLD` | float | `0.50` | USD threshold for cost alerts |
| `STATUSLINE_LOG_LEVEL` | string | `WARNING` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL, OFF) |
| `STATUSLINE_DEBUG` | boolean | `0` | Enable debug mode (0 or 1) |
| `NO_COLOR` | any | - | Disable color output (standard) |

### Performance Indicators

#### API Response Time Colors

| Color | Range | Meaning |
|-------|-------|---------|
| 🟢 Green | < 500ms | Fast, excellent performance |
| 🟡 Yellow | 500ms - 2s | Moderate, acceptable performance |
| 🔴 Red | > 2s | Slow, may need attention |

#### Trend Arrows

| Arrow | Meaning |
|-------|---------|
| `↗` | Activity increased (>20% more changes) |
| `→` | Similar activity level (±20%) |
| `↘` | Activity decreased (>20% fewer changes) |

## Design Philosophy

This statusline prioritizes **developer productivity** by displaying actionable metrics:

- **Code Productivity** - Track actual work output with line change statistics
- **Performance Awareness** - Monitor API response times to identify slowdowns
- **Cost Management** - Stay within budget with real-time cost tracking
- **Development Context** - Git branch and status at a glance

All metrics are derived from Claude Code's built-in session data, requiring no external APIs or dependencies.

## Data Sources

The statusline extracts data from Claude Code's session context (passed via stdin):

| Metric | Source Field |
|--------|--------------|
| Lines Added | `cost.total_lines_added` |
| Lines Removed | `cost.total_lines_removed` |
| API Duration | `cost.total_api_duration_ms` |
| Session Cost | `cost.total_cost_usd` |
| Session Duration | `cost.total_duration_ms` |
| Working Directory | `workspace.current_dir` |
| AI Model | `model.display_name` |

## Troubleshooting

### No metrics showing?

- Ensure you're using Claude Code v1.2.0 or higher
- Verify cost tracking is enabled in Claude Code
- Check logs: `~/.cache/claude-statusline/logs/`

### Colors not working?

- Check if `NO_COLOR` environment variable is set
- Enable debug mode: `STATUSLINE_DEBUG=1`
- Verify terminal supports ANSI colors

### Trend arrows not appearing?

- Arrows require at least two sessions for comparison
- Cache location: `~/.cache/claude-statusline/session_stats.json`
- Cache lifetime: 24 hours

### Git dirty status not showing?

- Ensure `git` is installed and in PATH
- Check that working directory is a git repository
- Verify git permissions

### Invalid configuration values?

The statusline gracefully handles invalid configuration:
- Invalid `STATUSLINE_COST_THRESHOLD` → defaults to `0.50`
- Invalid `STATUSLINE_LOG_LEVEL` → defaults to `WARNING`
- Missing cache directory → continues without trend tracking

## Development

### Testing Locally

```bash
# Test with mock data
echo '{
  "model": {"display_name": "Sonnet 4.5"},
  "workspace": {"current_dir": "/path/to/project"},
  "cost": {
    "total_cost_usd": 0.125,
    "total_duration_ms": 300000,
    "total_lines_added": 127,
    "total_lines_removed": 43,
    "total_api_duration_ms": 230
  }
}' | python3 statusline-hz.py
```

### Enable Debug Logging

```bash
export STATUSLINE_LOG_LEVEL=DEBUG
export STATUSLINE_DEBUG=1
```

Logs are written to: `~/.cache/claude-statusline/logs/statusline-YYYYMMDD.log`

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with insights from:
- [Claude Code Official Documentation](https://code.claude.com/docs/en/statusline)
- Terminal statusline best practices
- Developer productivity metrics research

---

**Note**: This is an independent project and is not officially affiliated with Anthropic or Claude Code.
