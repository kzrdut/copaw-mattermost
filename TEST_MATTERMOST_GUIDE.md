# Mattermost 集成测试脚本使用说明

## 📋 功能概述

`test_mattermost.py` 是一个完整的 Mattermost 集成测试工具，用于验证 CoPaw 与 Mattermost 的集成状态。

## 🎯 测试项目

### 1. **配置检查** (`--check-config`)
- ✅ 检查 Mattermost URL 是否配置
- ✅ 检查 Bot Token 是否配置
- ✅ 检查 Team ID 是否配置
- ✅ 检查 HTTP Proxy 配置

### 2. **连接测试** (`--test-connection`)
- ✅ Mattermost 服务器连接
- ✅ Bot Token 验证
- ✅ 登录功能
- ✅ 获取 Bot 信息

### 3. **权限测试** (`--test-permissions`)
- ✅ Bot 角色和权限
- ✅ 是否为系统管理员
- ✅ 团队成员资格检查

### 4. **团队测试** (`--test-teams`)
- ✅ 获取所有团队列表
- ✅ 显示团队 ID 和名称
- ✅ 标记当前配置的团队

### 5. **频道测试** (`--test-channels`)
- ✅ 获取团队中的所有频道
- ✅ 显示频道类型（公开/私有）
- ✅ 显示频道 ID 和名称

### 6. **发送消息测试** (`--test-send`)
- ✅ 发送测试消息到指定频道
- ✅ 自动选择第一个可用频道（如果不指定）
- ✅ 验证消息发送功能

### 7. **WebSocket 测试** (`--test-websocket`)
- ✅ WebSocket 连接
- ✅ 实时消息接收
- ✅ 消息事件解析
- ✅ 可配置超时时间

## 🚀 使用方法

### **快速开始：运行所有测试**
```bash
python test_mattermost.py
# 或
python test_mattermost.py --all
```

### **单独测试**

#### 1. 检查配置
```bash
python test_mattermost.py --check-config
```

#### 2. 测试连接
```bash
python test_mattermost.py --test-connection
```

#### 3. 测试权限
```bash
python test_mattermost.py --test-permissions
```

#### 4. 测试团队
```bash
python test_mattermost.py --test-teams
```

#### 5. 测试频道
```bash
python test_mattermost.py --test-channels
```

#### 6. 测试发送消息
```bash
# 自动选择频道
python test_mattermost.py --test-send

# 指定频道和消息
python test_mattermost.py --test-send --channel-id <channel_id> --message "Hello World"
```

#### 7. 测试 WebSocket
```bash
# 默认 30 秒超时
python test_mattermost.py --test-websocket

# 自定义超时时间
python test_mattermost.py --test-websocket --timeout 60
```

### **组合测试**

```bash
# 测试连接和权限
python test_mattermost.py --test-connection --test-permissions

# 测试团队和频道
python test_mattermost.py --test-teams --test-channels

# 测试发送和 WebSocket
python test_mattermost.py --test-send --test-websocket
```

### **JSON 输出**（用于自动化）
```bash
python test_mattermost.py --all --json > results.json
```

## 📊 输出示例

### **成功输出**
```
============================================================
📊 Configuration Status
============================================================
✅ Server URL     : http://127.0.0.1:8065/
✅ Bot Token      : 5p8nu1m3...ttdc
✅ Team ID        : pdnbbpgx...rafe
❌ HTTP Proxy     : 

============================================================
🔌 Testing Mattermost Connection
============================================================
📍 Server URL: http://127.0.0.1:8065/
🔍 Parsed: http://127.0.0.1:8065
🔑 Token: 5p8nu1m3...ttdc
👥 Team ID: pdnbbpgxzifjuycfpebrh9rafe
✅ Login successful!
🤖 Bot User ID: o3m65xbikffbmf7y3556muwdfc
📛 Bot Username: copaw-bot

============================================================
📊 Test Summary
============================================================
✅ Passed: 5/5
🎉 All tests passed! Mattermost is ready to use with CoPaw!
```

### **失败输出**
```
============================================================
📊 Test Summary
============================================================
✅ Passed: 3/5
❌ Failed: 2/5
   ✅ Connection
   ✅ Permissions
   ✅ Teams
   ❌ Channels
   ❌ Send Message

⚠️  Some tests failed. Please check the logs above.
```

## 🔧 常见问题排查

### **问题 1: Bot 不是团队成员**
```
👥 Team Member: ❌ No
⚠️  Bot is not a member of the configured team!
```

**解决方案**：
1. 在 Mattermost 中将 Bot 添加到团队
2. 或更新配置中的 Team ID

### **问题 2: 找不到频道**
```
⚠️  No channels found in this team!
```

**解决方案**：
1. 确认团队中有频道
2. 确认 Bot 已加入频道
3. 检查 Team ID 是否正确

### **问题 3: 连接失败**
```
❌ Login failed: Invalid parameters (check URL/port)
```

**解决方案**：
1. 检查 Mattermost 服务器是否运行
2. 验证 URL 格式正确
3. 确认端口配置正确

### **问题 4: WebSocket 测试失败**
```
❌ WebSocket test failed: ...
```

**解决方案**：
1. 确认 Bot 已加入至少一个频道
2. 在测试时发送消息到该频道
3. 检查 Bot 是否有读取消息的权限

## 💡 使用技巧

### **1. 定期测试**
建议在配置变更后立即运行测试：
```bash
python test_mattermost.py --all
```

### **2. 自动化集成**
使用 JSON 输出集成到 CI/CD：
```bash
python test_mattermost.py --all --json | jq '.results.connection'
```

### **3. 快速诊断**
只测试关键功能：
```bash
python test_mattermost.py --test-connection --test-permissions
```

### **4. 查看详细错误**
所有测试都会打印完整的错误堆栈，便于调试。

## 📝 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--check-config` | 仅检查配置 | - |
| `--test-connection` | 仅测试连接 | - |
| `--test-permissions` | 仅测试权限 | - |
| `--test-teams` | 仅测试团队 | - |
| `--test-channels` | 仅测试频道 | - |
| `--test-send` | 仅测试发送 | - |
| `--channel-id` | 指定频道 ID | 自动选择 |
| `--message` | 发送的消息 | "🤖 CoPaw test message" |
| `--test-websocket` | 仅测试 WebSocket | - |
| `--timeout` | WebSocket 超时（秒） | 30 |
| `--all` | 运行所有测试 | - |
| `--json` | JSON 格式输出 | - |

## 🎯 完整测试流程

```bash
# 1. 检查配置
python test_mattermost.py --check-config

# 2. 测试连接
python test_mattermost.py --test-connection

# 3. 测试权限
python test_mattermost.py --test-permissions

# 4. 查看团队
python test_mattermost.py --test-teams

# 5. 查看频道
python test_mattermost.py --test-channels

# 6. 测试发送
python test_mattermost.py --test-send

# 7. 测试 WebSocket（交互式）
python test_mattermost.py --test-websocket

# 或直接运行所有测试
python test_mattermost.py --all
```

## 📦 依赖要求

- Python 3.8+
- mattermostdriver 7.3.2+
- CoPaw 配置已正确设置

## 🔗 相关文件

- 配置文件：`~/.copaw/config.json`
- 环境变量：`MATTERMOST_URL`, `MATTERMOST_BOT_TOKEN`, `MATTERMOST_TEAM_ID`
- 日志文件：`~/.copaw/logs/copaw.log`

## 🆘 获取帮助

```bash
python test_mattermost.py --help
```

## ✅ 成功标志

当所有测试通过时，你应该看到：
```
🎉 All tests passed! Mattermost is ready to use with CoPaw!
```

此时可以：
1. 启动 CoPaw：`copaw app`
2. 在 Mattermost 中与 Bot 对话
3. 配置频道和自动化任务
