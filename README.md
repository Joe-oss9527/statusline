# Claude Code Productivity Statusline

A productivity-focused statusline for [Claude Code](https://code.claude.com/docs/en/statusline) that replaces weather data with actual coding metrics and performance indicators.

## Features

### 🎯 Core Metrics

- **📝 Code Change Statistics** - Real-time tracking of lines added/removed (`+127/-43`)
- **⚡ API Performance** - Response time monitoring with color-coded indicators
- **💰 Cost Tracking** - Session cost with threshold alerts
- **⏱️ Session Duration** - Time spent in current session
- **🌲 Git Status** - Branch name with dirty state indicator (`*`)

### ✨ Extra Features

- **📈 Trend Arrows** - Compare activity with previous session (`↗` `→` `↘`)
- **🚨 Cost Alerts** - Warning emoji when cost exceeds threshold
- **🎨 Color Coding** - Visual hierarchy for better readability
  - Orange: Model name
  - Cyan: Cost/metrics
  - Green: High productivity/fast performance
  - Yellow: Moderate performance
  - Red: Warnings/slow performance

## Example Output

```
⏰ 14:30 | Sonnet 4.5 statusline:main* [$0.125 5m] | 📝 +127/-43 ↗ | ⚡230ms
```

**Breakdown:**
- `⏰ 14:30` - Current time
- `Sonnet 4.5` - AI model
- `statusline:main*` - Directory:branch (with dirty indicator)
- `[$0.125 5m]` - Cost and duration
- `📝 +127/-43 ↗` - Code changes with upward trend
- `⚡230ms` - Fast API response (green)

## Configuration

Edit `.claude/settings.json`:

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

### Environment Variables

- `STATUSLINE_COST_THRESHOLD` - Alert threshold in USD (default: 0.50)
- `STATUSLINE_LOG_LEVEL` - Log level: DEBUG, INFO, WARNING, ERROR (default: WARNING)
- `STATUSLINE_DEBUG` - Enable debug mode: 0 or 1 (default: 0)

## Performance Indicators

### API Response Time Colors

- 🟢 **Green** (`<500ms`) - Fast, excellent performance
- 🟡 **Yellow** (`500ms-2s`) - Moderate, acceptable performance
- 🔴 **Red** (`>2s`) - Slow, may need attention

### Trend Arrows

- `↗` - Activity increased (>20% more changes than previous session)
- `→` - Similar activity level
- `↘` - Activity decreased (>20% fewer changes)

## Installation

1. Copy `statusline-hz.py` to `~/.claude/`
2. Make it executable: `chmod +x ~/.claude/statusline-hz.py`
3. Update `.claude/settings.json` with the configuration above
4. Restart Claude Code

## Why Productivity Metrics Instead of Weather?

This statusline focuses on what matters for coding:

✅ **Code productivity** - Track your actual work output
✅ **Performance awareness** - Know when APIs are slow
✅ **Cost management** - Stay within budget
✅ **Development context** - Git status at a glance

❌ **Weather** - Nice to have, but not relevant to coding

## Data Sources

All metrics come from Claude Code's built-in session data:
- `cost.total_lines_added` - Lines added in session
- `cost.total_lines_removed` - Lines removed in session
- `cost.total_api_duration_ms` - Total API response time
- `cost.total_cost_usd` - Session cost in USD
- `cost.total_duration_ms` - Total session duration
- `workspace.current_dir` - Working directory
- `model.display_name` - AI model name

## Troubleshooting

### No metrics showing?

- Make sure you're using Claude Code v1.2.0+ with cost tracking enabled
- Check logs in `~/.cache/claude-statusline/logs/`

### Colors not working?

- Check if `NO_COLOR` environment variable is set
- Try setting `STATUSLINE_DEBUG=1` to see raw output

### Trend arrows not appearing?

- Arrows only show after second session
- Cache is stored in `~/.cache/claude-statusline/session_stats.json`

## License

MIT

---

*This project transforms the original weather-based statusline into a developer productivity dashboard.*
