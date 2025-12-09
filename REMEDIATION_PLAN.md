# 多阶段修复计划

**基于代码审查报告 & Claude Code 官方最佳实践**

---

## 官方最佳实践要点

根据 [Claude Code 官方文档](https://code.claude.com/docs/en/statusline)：

| 要求 | 说明 |
|------|------|
| **简洁性** | 只使用第一行输出 |
| **视觉辅助** | 使用表情符号和颜色增强可读性 |
| **性能** | 更新频率 300ms，需缓存昂贵操作 |
| **可靠性** | 使用 stdout 输出，stderr 可能干扰 |
| **可测试性** | 支持本地 mock JSON 测试 |

---

## 修复阶段概览

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: 关键功能修复 (Critical)                                │
│  ├── 1.1 修复 API Duration 阈值逻辑                              │
│  ├── 1.2 处理 Git Detached HEAD 状态                            │
│  └── 1.3 修复 get_trend_arrow 副作用问题                         │
├─────────────────────────────────────────────────────────────────┤
│  Phase 2: 性能优化 (Performance)                                 │
│  ├── 2.1 优化日志清理逻辑（每日一次）                              │
│  ├── 2.2 添加 Git 状态缓存                                       │
│  └── 2.3 添加文件锁防止竞争条件                                   │
├─────────────────────────────────────────────────────────────────┤
│  Phase 3: 代码质量提升 (Quality)                                 │
│  ├── 3.1 提取魔法数字为命名常量                                   │
│  ├── 3.2 重构颜色代码到模块级                                     │
│  ├── 3.3 改进异常处理                                            │
│  └── 3.4 修复 validate() 方法语义                                │
├─────────────────────────────────────────────────────────────────┤
│  Phase 4: 用户体验改进 (UX)                                      │
│  ├── 4.1 优化首次使用体验                                        │
│  ├── 4.2 简化 "No changes yet" 显示                             │
│  └── 4.3 增强脏状态指示器可见性                                   │
├─────────────────────────────────────────────────────────────────┤
│  Phase 5: 工程完善 (Engineering)                                 │
│  ├── 5.1 添加单元测试                                            │
│  ├── 5.2 添加 LICENSE 文件                                       │
│  └── 5.3 更新文档                                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: 关键功能修复

### 1.1 修复 API Duration 阈值逻辑

**问题**: `total_api_duration_ms` 是累计时间，当前阈值 (500ms/2s) 不适用

**修复方案**:
```python
# 方案 A: 计算平均响应时间（推荐）
# 需要追踪 API 调用次数，计算平均值

# 方案 B: 调整累计时间阈值
PERF_FAST_CUMULATIVE_MS = 10000    # < 10s = 绿色
PERF_MODERATE_CUMULATIVE_MS = 60000  # < 60s = 黄色
# > 60s = 红色
```

**实施**:
```python
# 在 parse_claude_context() 中添加 API 调用计数
api_calls = data['cost'].get('total_api_calls', 1)
avg_api_duration = api_duration_ms / max(api_calls, 1)

# 使用平均值进行颜色判断
if avg_api_duration < 500:
    perf_display = f"{GREEN}⚡{api_str}{RESET}"
```

---

### 1.2 处理 Git Detached HEAD 状态

**问题**: Detached HEAD 时分支名为空

**修复方案**:
```python
# 在 parse_claude_context() 中
git_head = Path(cwd) / '.git' / 'HEAD'
if git_head.exists():
    content = git_head.read_text().strip()
    if content.startswith('ref: '):
        result['branch'] = content.split('/')[-1]
    else:
        # Detached HEAD - 显示短 commit hash
        result['branch'] = content[:7]
        result['detached'] = True  # 标记为 detached 状态
```

**显示优化**:
```python
# 在 main() 中
if context.get('detached'):
    header += f":{DIM}@{context['branch']}{RESET}"  # 用 @ 前缀表示 commit
else:
    header += f":{context['branch']}"
```

---

### 1.3 修复 get_trend_arrow 副作用问题

**问题**: 函数名暗示只获取数据，但实际有保存副作用

**修复方案**: 重命名并拆分职责

```python
class StatsTracker:
    def calculate_trend(self, current_added: int, current_removed: int) -> str:
        """计算趋势箭头（纯函数，无副作用）"""
        prev = self._load_previous_stats()

        if not prev:
            return ''

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
        """保存当前会话统计（明确的副作用操作）"""
        self._save_current_stats(lines_added, lines_removed)

    def get_trend_and_save(self, current_added: int, current_removed: int) -> str:
        """获取趋势并保存统计（组合操作，名称明确）"""
        trend = self.calculate_trend(current_added, current_removed)
        self.save_session_stats(current_added, current_removed)
        return trend
```

---

## Phase 2: 性能优化

### 2.1 优化日志清理逻辑

**问题**: 每次执行都扫描日志目录

**修复方案**: 每日执行一次清理

```python
def _should_run_cleanup(self) -> bool:
    """检查是否需要执行清理（每日一次）"""
    marker_file = self.log_dir / '.last_cleanup'
    try:
        if marker_file.exists():
            last_cleanup = marker_file.stat().st_mtime
            if time.time() - last_cleanup < 86400:  # 24 hours
                return False
        return True
    except OSError:
        return True

def _mark_cleanup_done(self):
    """标记清理完成"""
    marker_file = self.log_dir / '.last_cleanup'
    try:
        marker_file.touch()
    except OSError:
        pass

def setup_logging(config: Config):
    # ... 现有逻辑 ...

    # 仅在需要时执行清理
    if _should_run_cleanup():
        for old_log in config.log_dir.glob("statusline-*.log*"):
            # ... 清理逻辑 ...
        _mark_cleanup_done()
```

---

### 2.2 添加 Git 状态缓存

**问题**: 每次执行都运行 git status 命令

**修复方案**: 短期缓存 Git 状态（符合官方 300ms 更新周期）

```python
class GitStatusChecker:
    _cache: Dict[str, Tuple[bool, float]] = {}  # {cwd: (is_dirty, timestamp)}
    CACHE_TTL = 5.0  # 5秒缓存，平衡实时性和性能

    @classmethod
    def check_dirty_status(cls, cwd: str) -> bool:
        """检查 git 状态（带缓存）"""
        now = time.time()

        # 检查缓存
        if cwd in cls._cache:
            is_dirty, cached_at = cls._cache[cwd]
            if now - cached_at < cls.CACHE_TTL:
                return is_dirty

        # 执行实际检查
        is_dirty = cls._check_dirty_impl(cwd)
        cls._cache[cwd] = (is_dirty, now)
        return is_dirty

    @staticmethod
    def _check_dirty_impl(cwd: str) -> bool:
        """实际的 git 状态检查"""
        # ... 现有实现 ...
```

---

### 2.3 添加文件锁防止竞争条件

**问题**: 多实例同时运行可能导致缓存文件损坏

**修复方案**: 使用文件锁

```python
import fcntl

class StatsTracker:
    def _save_current_stats(self, lines_added: int, lines_removed: int):
        """保存统计（带文件锁）"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'lines_added': lines_added,
                'lines_removed': lines_removed,
                'timestamp': time.time()
            }

            # 使用临时文件 + 原子重命名
            temp_file = self.cache_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(data, f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            temp_file.rename(self.cache_file)

        except Exception as e:
            logging.debug(f"Failed to save stats: {e}")
```

---

## Phase 3: 代码质量提升

### 3.1 提取魔法数字为命名常量

```python
# ==================== Constants ====================

# Time constants
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400

# Cache settings
CACHE_EXPIRY_SECONDS = SECONDS_PER_DAY  # 24 hours
LOG_RETENTION_DAYS = 7
GIT_CACHE_TTL_SECONDS = 5.0

# Performance thresholds (for average API response time)
PERF_FAST_MS = 500
PERF_MODERATE_MS = 2000

# Trend analysis
TREND_THRESHOLD = 0.2  # 20% change threshold

# Git settings
GIT_TIMEOUT_SECONDS = 1
```

---

### 3.2 重构颜色代码到模块级

```python
# ==================== Color Palette ====================
# Eye-friendly colors optimized for terminal readability

class Colors:
    """ANSI color codes for terminal output"""

    # Check NO_COLOR environment variable
    _enabled = 'NO_COLOR' not in os.environ

    # Color definitions
    ORANGE = '\033[38;5;173m' if _enabled else ''
    CYAN = '\033[38;5;87m' if _enabled else ''
    DIM = '\033[2m' if _enabled else ''
    GREEN = '\033[38;5;78m' if _enabled else ''
    YELLOW = '\033[38;5;185m' if _enabled else ''
    RED = '\033[38;5;167m' if _enabled else ''
    RESET = '\033[0m' if _enabled else ''

    @classmethod
    def disable(cls):
        """Disable all colors"""
        cls.ORANGE = cls.CYAN = cls.DIM = ''
        cls.GREEN = cls.YELLOW = cls.RED = cls.RESET = ''
```

---

### 3.3 改进异常处理

```python
# 替换宽泛的 Exception 捕获为具体异常

# Before:
except Exception as e:
    logging.debug(f"Failed to parse: {e}")

# After:
except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
    logging.debug(f"Failed to parse context: {e}")
except OSError as e:
    logging.debug(f"File operation failed: {e}")
```

---

### 3.4 修复 validate() 方法语义

```python
class Config:
    def ensure_directories(self) -> bool:
        """确保必要目录存在（初始化操作）"""
        success = True
        try:
            self.cache_dir_base.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            logging.warning(f"Cache directory unavailable: {e}")
            success = False
        return success

    def is_valid(self) -> bool:
        """验证配置是否有效"""
        # 真正的验证逻辑
        if self.cost_threshold < 0:
            return False
        if self.log_level not in self.VALID_LOG_LEVELS:
            return False
        return True
```

---

## Phase 4: 用户体验改进

### 4.1 优化首次使用体验

```python
def calculate_trend(self, current_added: int, current_removed: int) -> str:
    prev = self._load_previous_stats()

    if not prev:
        # 首次使用时显示提示
        return ' (new)'  # 或 ' ●' 表示新会话

    # ... 正常趋势计算 ...
```

---

### 4.2 简化 "No changes yet" 显示

```python
# Before:
productivity_parts.append(f"{DIM}📝 No changes yet{RESET}")

# After:
productivity_parts.append(f"{DIM}📝 0/0{RESET}")  # 更简洁
```

---

### 4.3 增强脏状态指示器可见性

```python
# Before:
if is_dirty:
    header += f"{RED}*{RESET}"

# After - 选项 A: 使用更醒目的符号
if is_dirty:
    header += f"{RED}●{RESET}"

# After - 选项 B: 整个分支名变色
if context['branch']:
    branch_color = RED if is_dirty else ''
    branch_end = RESET if is_dirty else ''
    header += f":{branch_color}{context['branch']}{branch_end}"
    if is_dirty:
        header += "*"
```

---

## Phase 5: 工程完善

### 5.1 添加单元测试

创建 `tests/test_statusline.py`:

```python
import unittest
import json
from io import StringIO
from unittest.mock import patch, MagicMock
from statusline_hz import Config, StatsTracker, GitStatusChecker, parse_claude_context

class TestConfig(unittest.TestCase):
    def test_default_values(self):
        config = Config()
        self.assertEqual(config.cost_threshold, 0.50)
        self.assertEqual(config.log_level, 'WARNING')

    def test_invalid_cost_threshold_fallback(self):
        with patch.dict('os.environ', {'STATUSLINE_COST_THRESHOLD': 'invalid'}):
            config = Config()
            self.assertEqual(config.cost_threshold, 0.50)

class TestParseContext(unittest.TestCase):
    def test_parse_valid_json(self):
        mock_input = json.dumps({
            'model': {'display_name': 'Sonnet 4.5'},
            'workspace': {'current_dir': '/test/path'},
            'cost': {
                'total_cost_usd': 0.125,
                'total_lines_added': 100,
                'total_lines_removed': 50
            }
        })
        with patch('sys.stdin', StringIO(mock_input)):
            result = parse_claude_context()
            self.assertEqual(result['model'], 'Sonnet 4.5')
            self.assertEqual(result['lines_added'], 100)

class TestStatsTracker(unittest.TestCase):
    def test_trend_calculation(self):
        # ... 测试趋势计算逻辑 ...
        pass

if __name__ == '__main__':
    unittest.main()
```

---

### 5.2 添加 LICENSE 文件

创建 `LICENSE`:

```
MIT License

Copyright (c) 2025 statusline contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

### 5.3 更新文档

更新 README.md 添加:
- 性能说明（300ms 更新周期）
- 测试运行方法
- 贡献指南

---

## 实施时间表

| 阶段 | 优先级 | 复杂度 | 依赖 |
|------|--------|--------|------|
| Phase 1 | 🔴 关键 | 中等 | 无 |
| Phase 2 | 🟠 高 | 中等 | Phase 1 |
| Phase 3 | 🟡 中 | 低 | 无 |
| Phase 4 | 🟢 低 | 低 | Phase 3 |
| Phase 5 | 🟢 低 | 中等 | Phase 1-4 |

---

## 验收标准

### Phase 1 完成标准
- [ ] API 性能指示器在长会话中显示合理颜色
- [ ] Detached HEAD 状态正确显示 commit hash
- [ ] `get_trend_arrow` 重命名为明确表达副作用的名称

### Phase 2 完成标准
- [ ] 日志清理每日最多执行一次
- [ ] Git 状态检查有 5 秒缓存
- [ ] 缓存文件操作使用文件锁

### Phase 3 完成标准
- [ ] 所有魔法数字替换为命名常量
- [ ] 颜色代码移至模块级 Colors 类
- [ ] 异常处理使用具体异常类型

### Phase 4 完成标准
- [ ] 首次使用显示 "(new)" 提示
- [ ] 无更改时显示 "📝 0/0"
- [ ] 脏状态使用 "●" 符号

### Phase 5 完成标准
- [ ] 单元测试覆盖核心功能
- [ ] LICENSE 文件存在
- [ ] README 包含性能说明

---

## 回滚计划

每个阶段完成后创建 Git tag：
```bash
git tag -a v1.1.0-phase1 -m "Phase 1: Critical fixes"
git tag -a v1.2.0-phase2 -m "Phase 2: Performance optimization"
# ...
```

如有问题可快速回滚：
```bash
git checkout v1.1.0-phase1
```
