# Hangzhou Statusline for Claude Code

A Python-based weather statusline for [Claude Code](https://docs.anthropic.com/en/docs/claude-code/statusline) that displays comprehensive weather information in your terminal.

## Features

* **智能地点切换**: 工作时间自动显示西湖区天气，其他时间显示下沙大学城
* **全面天气信息**: 实时温度、体感温度、天气现象、风向风速、分钟级降水预报、空气质量、明日预报
* **QWeather v7 API**: 使用 [QWeather](https://dev.qweather.com/docs) 最新 API 与 JWT 认证
* **Claude Code 集成**: 专为 [Claude Code statusline](https://docs.anthropic.com/en/docs/claude-code/statusline) 设计

## Sample Output

```
Sonnet 4  statusline | 西湖区 | 32°C（体感35°） 多云 | 东南风 12km/h | 25分钟后下雨 | AQI 87 良 | 明日 27~33°C 多云转小雨 | 东南风 14km/h | 降水1.2mm
```

## Key Features

* **智能位置切换**: 工作日 08:00–19:00 显示西湖区，其他时间显示下沙大学城
* **JWT 认证**: 支持 QWeather JWT 自动生成或使用预设 token
* **并行数据获取**: 使用 ThreadPoolExecutor 同时获取多个 API 数据
* **智能缓存**: 不同数据类型独立缓存，减少 API 调用
* **详细日志**: 支持多级日志记录和自动轮转
* **手动切换**: 支持环境变量或文件方式手动指定地点
* **颜色支持**: 遵循 `NO_COLOR` 标准的彩色输出

## Requirements

* **Python 3.7+**
* **QWeather 开发者账号**: 获取 [QWeather](https://dev.qweather.com/docs) JWT 认证信息
* **Optional**: `PyJWT` library for JWT generation (fallback to OpenSSL if not available)
* **macOS/Linux**: Tested on both platforms

### QWeather Setup

参考 [QWeather JWT 认证文档](https://dev.qweather.com/docs/authentication/jwt/)：
1. 注册 QWeather 开发者账号
2. 创建项目获取 Project ID 和 Key ID  
3. 生成 Ed25519 私钥对
4. 获取专属 API Host

### Python Dependencies

```bash
# 可选安装 PyJWT (推荐)
pip install PyJWT

# 或使用内置 OpenSSL fallback (需要 openssl 命令)
```

## Installation

1. **下载脚本**
   ```bash
   # 将 statusline-hz.py 保存到 ~/.claude/
   chmod +x ~/.claude/statusline-hz.py
   ```

2. **配置 Claude Code**
   
   在 Claude Code 的 `settings.json` 中配置（参考 [Claude Code 设置文档](https://docs.anthropic.com/en/docs/claude-code/settings)）：

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "~/.claude/statusline-hz.py",
       "padding": 0
     },
     "env": {
       "QWEATHER_API_HOST": "https://your-api-host.qweatherapi.com",
       "QWEATHER_KEY_ID": "YOUR_KEY_ID",
       "QWEATHER_PROJECT_ID": "YOUR_PROJECT_ID",
       "QWEATHER_PRIVATE_KEY": "~/.ssh/your-private-key.pem",
       "QWEATHER_JWT_TTL_SEC": "900",
       "STATUSLINE_TZ": "Asia/Shanghai",
       "WORK_START": "8",
       "WORK_END": "19",
       "WORK_DAYS": "1-5",
       "QWEATHER_TTL_NOW_SEC": "600",
       "QWEATHER_TTL_MIN_SEC": "300",
       "QWEATHER_TTL_AQI_SEC": "900",
       "QWEATHER_TTL_DAILY_SEC": "3600",
       "STATUSLINE_DEBUG": "1",
       "STATUSLINE_LOG_LEVEL": "DEBUG"
     }
   }
   ```

   > **注意**: 将示例中的占位符替换为你的实际 QWeather 认证信息

3. **生成私钥**（如果还没有）
   ```bash
   # 生成 Ed25519 私钥对
   ssh-keygen -t ed25519 -f ~/.ssh/qweather-private -N ""
   ```

## Configuration Details

### JWT Authentication

本脚本支持两种 JWT 生成方式：

1. **自动生成**（推荐）：使用 Project ID、Key ID 和私钥自动生成 JWT
2. **预设 Token**：直接使用预先生成的 JWT token

参考 [QWeather JWT 认证文档](https://dev.qweather.com/docs/authentication/jwt/) 了解详细认证流程。

### Environment Variables

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `QWEATHER_API_HOST` | ✓ | QWeather 专属 API Host |
| `QWEATHER_KEY_ID` | ✓ | QWeather Key ID |
| `QWEATHER_PROJECT_ID` | ✓ | QWeather Project ID |
| `QWEATHER_PRIVATE_KEY` | ✓ | Ed25519 私钥文件路径 |
| `QWEATHER_JWT_TTL_SEC` | - | JWT 有效期，默认 900 秒 |
| `QWEATHER_JWT` | - | 预设 JWT token（可选，优先级高于自动生成） |
| `STATUSLINE_TZ` | - | 时区，默认 Asia/Shanghai |
| `WORK_START` | - | 工作开始时间，默认 8 |
| `WORK_END` | - | 工作结束时间，默认 19 |
| `WORK_DAYS` | - | 工作日，默认 1-5（周一到周五） |
| `QWEATHER_TTL_*` | - | 各类数据缓存时间（秒） |
| `STATUSLINE_DEBUG` | - | 调试模式，设为 1 启用 |
| `STATUSLINE_LOG_LEVEL` | - | 日志级别：DEBUG/INFO/WARNING/ERROR |

## Usage

启用后，Claude Code 会在终端底部自动显示天气信息。

### Manual Location Override

**方式 1: 环境变量**
```bash
STATUSLINE_FORCE_LOCATION="下沙" claude
```

**方式 2: 本地文件**（推荐）
```bash
echo "下沙" > ~/.cache/statusline_location
```

可选值：`西湖`、`下沙`

### Debugging

启用调试模式查看详细日志：
```bash
export STATUSLINE_DEBUG=1
export STATUSLINE_LOG_LEVEL=DEBUG
```

日志文件位置：`~/.cache/statusline.log`

## API Details

本脚本使用以下 QWeather API：

* **实时天气** `/v7/weather/now` - 温度、体感、天气现象、风向风速
* **分钟级降水** `/v7/minutely/5m` - 降水预报摘要和详细数据
* **空气质量** `/airquality/v1/current` - AQI 指数（优先使用中国标准 cn-mee）
* **3日预报** `/v7/weather/3d` - 明日天气预报（温度范围、天气现象、风力、降水）

所有 API 调用使用 JWT 认证，支持并行请求以提高响应速度。

## Testing

Claude Code 通过 stdin 传递上下文 JSON。本地测试：

```bash
echo '{}' | ~/.claude/statusline-hz.py
```

成功运行会输出一行状态文本。

## References

* **[QWeather API Documentation](https://dev.qweather.com/docs)** - 和风天气开发文档
* **[Claude Code Statusline Documentation](https://docs.anthropic.com/en/docs/claude-code/statusline)** - Claude Code 状态栏配置指南
* **[QWeather JWT Authentication](https://dev.qweather.com/docs/authentication/jwt/)** - JWT 认证详细说明

## Troubleshooting

### Common Issues

1. **JWT 生成失败**
   - 检查私钥文件路径和格式
   - 确认 Project ID 和 Key ID 正确
   - 尝试安装 PyJWT: `pip install PyJWT`

2. **API 请求失败**
   - 验证 API Host 格式正确
   - 检查网络连接
   - 查看调试日志了解详细错误

3. **位置信息不准确**
   - 使用手动位置覆盖功能
   - 检查时区设置是否正确

## License

MIT License

---

*本项目部分代码由 Claude 协助生成和优化。*

