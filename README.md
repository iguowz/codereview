[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

# Git增量代码智能审查与测试用例生成系统

## 🚀 项目简介

这是一个基于AI的Git增量代码智能审查与测试用例生成系统，能够：

- 🔍 **智能代码审查**：分析代码变更，识别潜在问题
- 🧪 **自动生成测试用例**：根据代码变更自动生成单元测试和场景测试
- 🌐 **支持多种Git平台**：GitHub、GitLab等
- ⚙️ **内存任务队列**：使用MockCelery模式
- 📧 **多种通知方式**：支持邮件、企业微信群机器人通知
- 🚀 **性能优化**：异步处理、连接池、内存缓存优化
- 🎯 **跨平台支持**：Windows、Linux、macOS一键启动

## 📁 项目结构

```
codeReview/
├── app/                    # 后端应用
│   ├── __init__.py        # Flask应用初始化
│   ├── routes.py          # API路由
│   ├── tasks.py           # Celery任务
│   ├── task_processor.py  # 任务处理器
│   ├── task_state.py      # 任务状态管理
│   ├── statistics.py      # 统计功能
│   ├── models.py          # 数据模型
│   ├── logger.py          # 日志系统
│   ├── config_manager.py  # 配置管理
│   ├── exceptions.py      # 异常定义
│   └── utils/             # 工具模块
│       ├── git_api.py     # Git API客户端
│       ├── llm_api.py     # LLM API客户端
│       ├── async_llm_api.py # 异步LLM API
│       └── crypto.py      # 加密工具
├── config/                # 配置文件
│   ├── systems.yaml       # 系统配置
│   └── prompts.yaml       # 提示词模板
├── static/                # 静态资源
│   ├── css/               # 样式文件
│   └── js/                # JavaScript文件
├── templates/             # 前端模板
│   └── index.html         # 主页面
├── scripts/               # 启动脚本
│   ├── start.py           # 跨平台Python启动脚本
│   └── start.sh           # Linux/Mac Shell启动脚本
├── main.py                # 主程序
├── requirements.txt       # Python依赖
└── README.md              # 项目说明
```

## 🚀 快速启动

### 方法1：使用Python启动脚本（推荐）
```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export DEEPSEEK_API_KEY='your-api-key'

# 启动应用
python scripts/start.py
```

### 方法2：使用Shell脚本（Linux/Mac）
```bash
# 给脚本执行权限
chmod +x scripts/start.sh

# 运行启动脚本
./scripts/start.sh
```

### 方法3：手动启动
```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置环境变量
export DEEPSEEK_API_KEY='your-api-key'

# 3. 可选：自定义端口
export PORT=8080

# 4. 启动应用
python main.py
```

## ⚙️ 配置说明

### 环境变量
- `DEEPSEEK_API_KEY`: DeepSeek API密钥（必需）
- `PORT`: 服务器端口（可选，默认5001）
- `HOST`: 服务器主机（可选，默认0.0.0.0）
- `SECRET_KEY`: Flask密钥（可选，默认dev-secret-key）

### 通知配置（可选）
支持邮件和企业微信群机器人通知。通知系统采用前后端分离的配置方式：
- 私密信息（如密码、Webhook URL）通过环境变量配置
- 公开配置（如收件人列表、开关状态）通过前端界面管理

#### 邮件通知环境变量
```bash
export NOTIFICATION_EMAIL_SMTP_SERVER=smtp.gmail.com
export NOTIFICATION_EMAIL_SMTP_PORT=587
export NOTIFICATION_EMAIL_USERNAME=your-email@gmail.com
export NOTIFICATION_EMAIL_PASSWORD=your-app-password
export NOTIFICATION_EMAIL_USE_SSL=true
export NOTIFICATION_EMAIL_FROM_NAME="Code Review System"
```

#### 企业微信群机器人环境变量
```bash
export NOTIFICATION_WECHAT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key
```

#### 前端界面配置
启动应用后，点击右上角的"通知配置"按钮可以：
- 启用/禁用邮件和企业微信通知
- 管理邮件收件人列表（添加/删除/展示）
- 设置企业微信@提醒用户
- 测试通知发送功能

**注意**：环境变量配置完成后需要重启应用才能生效。

### 配置文件
1. 编辑 `config/systems.yaml`，配置你的Git系统信息：
   ```yaml
   systems:
     - id: "your-system-id"
       name: "你的系统名称"
       git_provider: "github"  # 或 "gitlab"
       git_provider_url: "https://api.github.com"
       git_provider_token: "your-git-token"
       projects:
         - name: "你的项目名称"
           repo_url: "https://github.com/owner/repo"
   ```

## 🔧 任务队列配置

### MockCelery模式（默认）
```bash
python scripts/start.py
```

**特点**：
- ✅ 无需安装额外依赖
- ✅ 任务在后台线程中执行
- ✅ 支持任务状态查询
- ✅ 完全兼容Celery API

## 📝 日志系统

项目采用统一的日志管理系统，提供专业级的日志记录功能：

- 自动日志轮转
- 多级别日志记录
- 任务专用日志器
- 性能监控

## 🎯 主要功能

### 1. 代码审查
- 增量代码分析
- 潜在问题识别
- 代码质量评估
- 安全漏洞检测

### 2. 测试用例生成
- 单元测试生成
- 集成测试生成
- 边界条件测试
- 异常场景测试

### 3. Git集成
- 多平台支持（GitHub、GitLab）
- 增量变更检测
- 分支管理
- 提交历史分析

### 4. 通知系统
- 任务完成/失败自动通知
- 支持邮件和企业微信群机器人
- 灵活的收件人配置
- 美观的HTML邮件模板

### 5. 性能优化
- HTTP连接池和重试机制
- 异步处理和并发控制
- 内存缓存和LRU缓存
- 优化的超时和连接配置

## 🚨 故障排除

### 常见问题

1. **Python版本问题**
   - 确保Python版本 >= 3.8
   - 使用 `python3` 命令

2. **依赖安装失败**
   - 检查网络连接
   - 使用国内镜像：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple/ -r requirements.txt`

3. **配置文件问题**
   - 确保 `config/systems.yaml` 存在
   - 检查YAML语法格式

4. **API密钥问题**
   - 设置正确的 `DEEPSEEK_API_KEY`
   - 检查API密钥是否有效

5. **端口占用问题**
   - 使用 `export PORT=8080` 指定其他端口
   - 检查端口是否被其他服务占用


## 🔄 更新日志

- **v1.0.0**: 初始版本，支持基础代码审查功能
- **v1.1.0**: 添加测试用例生成功能
- **v1.2.0**: 支持多Git平台
- **v1.3.0**: 添加MockCelery模式，优化开发体验
- **v1.4.0**: 项目结构优化，文档整合，启动脚本改进

## 📞 技术支持

如果遇到问题，请：

1. 查看日志文件获取详细错误信息
2. 检查环境变量和配置文件
3. 确保所有依赖已正确安装
4. 参考文档的故障排除部分

## 🤝 贡献指南

欢迎提交Issue和Pull Request来改进项目！

## 许可证

本项目采用Apache 2.0 许可证。
