# 医疗助手 - 使用说明

## 📋 简介

这是一个基于 RAG（检索增强生成）技术的医疗智能问答系统，所有功能集成在单个脚本中。

## ✨ 特性

- 🤖 **ReAct Agent**: 智能推理和工具调用
- 📚 **向量检索**: 基于 Milvus 的语义搜索
- 🧠 **Embedding**: BGE-large-zh-v1.5 中文向量模型
- 💬 **流式对话**: DeepSeek API 实时流式输出
- 🏥 **医疗知识库**: 预置常见医疗健康知识

## 🚀 快速开始

### 1. 环境要求

```bash
# Python 3.9+
# Milvus 向量数据库（Docker 部署）
```

### 2. 安装依赖

```bash
pip install torch sentence-transformers pymilvus requests
```

### 3. 启动 Milvus

```bash
cd milvus
docker-compose up -d
```

### 4. 设置 API Key

```bash
export DEEPSEEK_API_KEY='your-deepseek-api-key'
```

### 5. 运行脚本

```bash
python medical_assistant.py
```

## 📖 使用示例

### 启动界面

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║              🏥 医疗助手 - 智能问答系统 🏥                    ║
║                                                              ║
║              基于 RAG 技术的医疗知识问答                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

🚀 正在初始化系统...
🔄 正在加载 Embedding 模型: BAAI/bge-large-zh-v1.5
📱 使用设备: mps
✅ Embedding 模型加载完成
🔄 正在连接 Milvus: localhost:19530
✅ Milvus 连接成功
📚 加载已存在的集合: medical_knowledge
✅ DeepSeek 服务初始化完成
✅ 知识库已有 10 条数据

💡 使用说明:
  - 输入您的医疗健康问题
  - 输入 'exit' 或 'quit' 退出
  - 输入 'clear' 清空对话历史
```

### 对话示例

```
🤔 ============================================================================
您的问题: 我最近总是头痛，应该怎么办？

================================================================================
💭 AI 思考过程:
================================================================================
Thought: 患者询问头痛的处理方法，我需要查询知识库获取相关信息
Action: knowledge_search
Action Input: 头痛的原因和处理方法

🔍 正在搜索知识库: 头痛的原因和处理方法
✅ 找到 3 条相关信息

================================================================================
💡 最终回答:
================================================================================
Answer: 根据医疗知识库的信息，头痛主要分为以下几种类型：

1. **紧张性头痛**（最常见）
2. **偏头痛**
3. **丛集性头痛**

**处理建议：**
- 如果是轻度头痛，可以休息、放松、按摩太阳穴
- 保持规律作息，避免压力过大
- 适量运动，保持良好心态

**⚠️ 重要提醒：**
如果头痛伴随以下症状，应立即就医：
- 呕吐
- 视力模糊
- 意识改变
- 持续加重

建议您先观察症状，如果持续不缓解或出现上述严重症状，请及时到医院就诊。
```

## 🔧 配置说明

### 修改配置

编辑 `medical_assistant.py` 中的 `Config` 类：

```python
@dataclass
class Config:
    # Milvus 配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: str = "19530"
    MILVUS_COLLECTION: str = "medical_knowledge"
    
    # Embedding 模型
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    EMBEDDING_DIM: int = 1024
    
    # DeepSeek API
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = "deepseek-chat"
    
    # 检索配置
    TOP_K: int = 3  # 返回前 K 个相关文档
```

### 添加自定义医疗知识

修改 `init_sample_data()` 函数中的 `sample_data` 列表：

```python
sample_data = [
    "你的医疗知识1",
    "你的医疗知识2",
    # ... 更多知识
]
```

## 🎯 核心功能

### 1. Embedding 服务

```python
class EmbeddingService:
    """将文本转换为 1024 维向量"""
    def encode(self, text: str) -> List[float]
    def encode_batch(self, texts: List[str]) -> List[List[float]]
```

### 2. Milvus 服务

```python
class MilvusService:
    """向量数据库操作"""
    def insert(self, texts: List[str], embeddings: List[List[float]])
    def search(self, query_embedding: List[float], top_k: int = 3)
```

### 3. DeepSeek 服务

```python
class DeepSeekService:
    """LLM 流式对话"""
    def chat_stream(self, messages: List[Dict[str, str]]) -> str
```

### 4. Medical Agent

```python
class MedicalAgent:
    """ReAct Agent 智能推理"""
    def knowledge_search(self, query: str) -> str  # 工具函数
    def run(self, user_question: str) -> str       # 主逻辑
```

## 🔍 工作流程

```
用户输入问题
    ↓
Agent 分析问题
    ↓
判断是否需要查询知识库
    ↓ (需要)
Embedding 将查询转换为向量
    ↓
Milvus 搜索相似文档（Top 3）
    ↓
返回相关知识
    ↓
LLM 基于知识生成回答（流式输出）
    ↓
显示最终答案
```

## 📊 系统架构

```
┌─────────────────────────────────────────────────┐
│                 用户交互层                        │
│              (Terminal Interface)               │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│              Medical Agent                      │
│           (ReAct 推理引擎)                       │
└─────┬──────────────────────────┬────────────────┘
      │                          │
      │                          │
┌─────▼──────────┐    ┌──────────▼─────────────┐
│ DeepSeek LLM   │    │  Knowledge Search Tool │
│  (流式对话)     │    │   (知识库检索工具)      │
└────────────────┘    └──────────┬─────────────┘
                                 │
                      ┌──────────▼──────────┐
                      │  Embedding Service  │
                      │   (文本向量化)       │
                      └──────────┬──────────┘
                                 │
                      ┌──────────▼──────────┐
                      │   Milvus Service    │
                      │   (向量数据库)       │
                      └─────────────────────┘
```

## 💡 命令说明

| 命令 | 说明 |
|------|------|
| 输入问题 | 向医疗助手提问 |
| `exit` / `quit` | 退出程序 |
| `clear` | 清空对话历史 |

## ⚠️ 注意事项

1. **医疗免责声明**: 本系统仅供参考，不能替代专业医疗诊断
2. **API 费用**: DeepSeek API 调用会产生费用
3. **数据隐私**: 不要输入个人敏感信息
4. **网络要求**: 需要访问 DeepSeek API

## 🐛 常见问题

### Q1: 提示 "未设置 DEEPSEEK_API_KEY"

```bash
export DEEPSEEK_API_KEY='your-api-key'
```

### Q2: Milvus 连接失败

```bash
# 检查 Milvus 是否运行
docker ps | grep milvus

# 重启 Milvus
cd milvus && docker-compose restart
```

### Q3: Embedding 模型下载慢

```bash
# 使用国内镜像
export HF_ENDPOINT=https://hf-mirror.com
```

### Q4: 显示 "知识库中未找到相关信息"

- 检查知识库是否有数据
- 尝试换个问法
- 添加更多相关知识到 `sample_data`

## 📝 扩展建议

1. **添加更多医疗知识**: 修改 `init_sample_data()` 函数
2. **支持文档上传**: 添加 PDF/Word 文档解析功能
3. **多轮对话优化**: 增强上下文理解能力
4. **Web 界面**: 使用 Gradio 或 Streamlit 创建 UI
5. **日志记录**: 添加对话日志和错误追踪

## 📄 许可证

MIT License

## 🙏 致谢

- DeepSeek - LLM API
- Milvus - 向量数据库
- BGE - Embedding 模型
