#!/usr/bin/env python3
"""
医疗助手 - 基于 RAG 的智能问答系统
所有功能集成在一个脚本中
支持云端 DeepSeek 和本地 Qwen 模型
"""

import os
import sys
import gc
import shutil
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# 设置环境变量（必须在导入其他库之前）
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

# 第三方库导入
import torch
from sentence_transformers import SentenceTransformer
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
import requests
import json


# ==================== 配置类 ====================
@dataclass
class Config:
    """系统配置"""
    # 模型选择
    MODEL_TYPE: str = "deepseek"  # "deepseek" 或 "qwen"
    
    # Milvus 配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: str = "19530"
    MILVUS_COLLECTION: str = "medical_knowledge"
    
    # Embedding 模型配置
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    EMBEDDING_DIM: int = 1024
    
    # DeepSeek API 配置
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    
    # Qwen 本地模型配置
    QWEN_MODEL_PATH: str = "./medical_llm_project/models/qwen/Qwen2___5-7B-Instruct"
    QWEN_LORA_PATH: str = "./medical_llm_project/output/qwen2_5_lora/checkpoint-5000"
    QWEN_OFFLOAD_DIR: str = "./offload_temp"
    
    # 检索配置
    TOP_K: int = 3
    
    # 设备配置
    DEVICE: str = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"


# ==================== Embedding 服务 ====================
class EmbeddingService:
    """文本向量化服务"""
    
    def __init__(self, model_name: str, device: str):
        print(f"🔄 正在加载 Embedding 模型: {model_name}")
        print(f"📱 使用设备: {device}")
        self.model = SentenceTransformer(model_name, device=device)
        print("✅ Embedding 模型加载完成")
    
    def encode(self, text: str) -> List[float]:
        """将文本转换为向量"""
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    
    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """批量转换文本为向量"""
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()


# ==================== Milvus 服务 ====================
class MilvusService:
    """Milvus 向量数据库服务"""
    
    def __init__(self, host: str, port: str, collection_name: str, dim: int):
        self.collection_name = collection_name
        self.dim = dim
        self.collection = None
        
        print(f"🔄 正在连接 Milvus: {host}:{port}")
        connections.connect(host=host, port=port)
        print("✅ Milvus 连接成功")
        
        self._init_collection()
    
    def _init_collection(self):
        """初始化或加载集合"""
        if utility.has_collection(self.collection_name):
            print(f"📚 加载已存在的集合: {self.collection_name}")
            self.collection = Collection(self.collection_name)
            self.collection.load()
        else:
            print(f"🆕 创建新集合: {self.collection_name}")
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dim)
            ]
            schema = CollectionSchema(fields, description="Medical knowledge base")
            self.collection = Collection(self.collection_name, schema)
            
            # 创建索引
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            self.collection.create_index("embedding", index_params)
            self.collection.load()
            print("✅ 集合创建完成")
    
    def insert(self, texts: List[str], embeddings: List[List[float]]):
        """插入数据"""
        data = [texts, embeddings]
        self.collection.insert(data)
        self.collection.flush()
        print(f"✅ 插入 {len(texts)} 条数据")
    
    def search(self, query_embedding: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
        """搜索相似文档"""
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        
        results = self.collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["text"]
        )
        
        documents = []
        for hits in results:
            for hit in hits:
                documents.append({
                    "text": hit.entity.get("text"),
                    "score": hit.score
                })
        
        return documents


# ==================== DeepSeek LLM 服务 ====================
class DeepSeekService:
    """DeepSeek LLM 服务"""
    
    def __init__(self, api_key: str, api_url: str, model: str):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        print("✅ DeepSeek 云端服务初始化完成")
    
    def chat_stream(self, messages: List[Dict[str, str]]) -> str:
        """流式对话"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=60
            )
            response.raise_for_status()
            
            full_response = ""
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if 'choices' in data and len(data['choices']) > 0:
                                delta = data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    print(content, end='', flush=True)
                                    full_response += content
                        except json.JSONDecodeError:
                            continue
            
            print()  # 换行
            return full_response
            
        except Exception as e:
            print(f"\n❌ API 调用失败: {e}")
            return ""


# ==================== Qwen 本地模型服务 ====================
class QwenService:
    """Qwen 本地模型服务"""
    
    def __init__(self, model_path: str, lora_path: str, offload_dir: str):
        print("🔄 正在初始化 Qwen 本地模型...")
        
        # 动态导入（避免没有安装时报错）
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer, BitsAndBytesConfig
            from peft import PeftModel
        except ImportError:
            print("❌ 缺少依赖: pip install transformers peft bitsandbytes")
            sys.exit(1)
        
        self.model_path = model_path
        self.lora_path = lora_path
        self.offload_dir = offload_dir
        
        # 硬件配置
        hw_config = self._setup_hardware()
        
        # 加载 Tokenizer
        print("📦 正在加载 Tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        
        # 加载基础模型
        print("🧠 正在加载基础模型 (可能需要几分钟)...")
        base_model = AutoModelForCausalLM.from_pretrained(
            model_path,
            quantization_config=hw_config["quantization_config"],
            torch_dtype=hw_config["torch_dtype"],
            device_map=hw_config["device_map"],
            offload_folder=hw_config["offload_folder"],
            max_memory=hw_config["max_memory"],
            trust_remote_code=True,
            low_cpu_mem_usage=True
        )
        
        # 挂载 LoRA
        print("🔗 正在挂载 LoRA 适配器...")
        self.model = PeftModel.from_pretrained(
            base_model, 
            lora_path,
            offload_folder=hw_config["offload_folder"]
        )
        self.model.eval()
        
        print("✅ Qwen 本地模型加载完成")
    
    def _setup_hardware(self):
        """硬件配置"""
        print("="*50)
        print("请选择当前运行环境:")
        print("1. 服务器 (NVIDIA A800/A100 80GB)")
        print("2. 个人电脑 (NVIDIA RTX 4060 8GB)")
        print("3. MacBook (Apple Silicon M1/M2/M3)")
        print("="*50)
        
        choice = input("请输入编号 (1/2/3): ")
        
        from transformers import BitsAndBytesConfig
        
        config = {
            "device_map": "auto",
            "quantization_config": None,
            "torch_dtype": torch.bfloat16,
            "offload_folder": None,
            "max_memory": None
        }
        
        if choice == "1":
            print("🚀 检测到高性能服务器，开启全量 BF16 加载...")
            config["device_map"] = "cuda:0"
        
        elif choice == "2":
            print("⚡ 检测到消费级显卡 (8G)，开启 Int4 量化与磁盘分流...")
            config["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True
            )
            config["torch_dtype"] = torch.float16
            config["offload_folder"] = self.offload_dir
            config["max_memory"] = {0: "6GiB", "cpu": "16GiB"}
        
        elif choice == "3":
            print("🍏 检测到 MacBook，开启 MPS 三级分流模式...")
            if os.path.exists(self.offload_dir):
                shutil.rmtree(self.offload_dir)
            os.makedirs(self.offload_dir)
            
            config["device_map"] = "auto"
            config["torch_dtype"] = torch.float16
            config["offload_folder"] = self.offload_dir
            config["max_memory"] = {0: "7GiB", "cpu": "10GiB"}
            
            # 清理 Mac 内存
            gc.collect()
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        
        else:
            print("❌ 输入错误，默认使用 CPU 基础模式。")
            config["device_map"] = "cpu"
        
        return config
    
    def chat_stream(self, messages: List[Dict[str, str]]) -> str:
        """流式对话"""
        from transformers import TextIteratorStreamer
        
        # 应用聊天模板
        input_text = self.tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )
        
        # 准备输入
        inputs = self.tokenizer([input_text], return_tensors="pt").to(self.model.device)
        
        # 创建流式处理器
        streamer = TextIteratorStreamer(
            self.tokenizer, 
            skip_prompt=True, 
            skip_special_tokens=True
        )
        
        # 生成参数
        generation_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=512,
            do_sample=True,
            top_p=0.8,
            temperature=0.7,
            repetition_penalty=1.1,
            eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=self.tokenizer.pad_token_id
        )
        
        # 在独立线程中运行生成
        thread = threading.Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()
        
        # 流式输出
        full_response = ""
        for new_text in streamer:
            print(new_text, end="", flush=True)
            full_response += new_text
        
        print()  # 换行
        return full_response


# ==================== ReAct Agent ====================
class MedicalAgent:
    """医疗助手 Agent"""
    
    def __init__(self, llm_service, embedding_service: EmbeddingService, 
                 milvus_service: MilvusService, top_k: int = 3):
        self.llm = llm_service  # 可以是 DeepSeekService 或 QwenService
        self.embedding = embedding_service
        self.milvus = milvus_service
        self.top_k = top_k
        self.history = []
        
        # 系统提示词
        self.system_prompt = """你是一位专业的医生助手，负责回答患者的医疗健康问题。

你有一个工具可以使用：
- knowledge_search(query: str): 在医疗知识库中搜索相关信息

当遇到不确定的问题时，你应该使用 knowledge_search 工具查询知识库。

请按照以下格式思考和回答：

Thought: 我需要思考如何回答这个问题
Action: knowledge_search
Action Input: 搜索的关键词
Observation: [工具返回的结果]
... (可以重复 Thought/Action/Observation 多次)
Thought: 我现在知道最终答案了
Answer: 最终的回答内容

重要规则：
1. 必须严格按照上述格式输出
2. 如果不确定，一定要使用 knowledge_search 工具
3. 基于 Observation 的内容回答，不要编造信息
4. 回答要专业、准确、易懂
5. 如果知识库中没有相关信息，诚实告知患者

现在开始回答患者的问题。"""
    
    def knowledge_search(self, query: str) -> str:
        """知识库搜索工具"""
        print(f"\n🔍 正在搜索知识库: {query}")
        
        # 1. 将查询转换为向量
        query_embedding = self.embedding.encode(query)
        
        # 2. 在 Milvus 中搜索
        results = self.milvus.search(query_embedding, top_k=self.top_k)
        
        # 3. 格式化结果
        if not results:
            return "知识库中未找到相关信息"
        
        context = "找到以下相关信息：\n\n"
        for i, doc in enumerate(results, 1):
            context += f"{i}. {doc['text']}\n(相关度: {doc['score']:.2f})\n\n"
        
        print(f"✅ 找到 {len(results)} 条相关信息")
        return context
    
    def run(self, user_question: str) -> str:
        """运行 Agent"""
        print("\n" + "="*80)
        print("💭 AI 思考过程:")
        print("="*80)
        
        # 构建消息
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_question}
        ]
        
        # 添加历史记录
        for msg in self.history[-6:]:  # 只保留最近3轮对话
            messages.append(msg)
        
        messages.append({"role": "user", "content": user_question})
        
        # 调用 LLM
        response = self.llm.chat_stream(messages)
        
        # 解析响应
        if "Action: knowledge_search" in response:
            # 提取 Action Input
            try:
                action_input_start = response.find("Action Input:") + len("Action Input:")
                action_input_end = response.find("\n", action_input_start)
                if action_input_end == -1:
                    action_input_end = len(response)
                query = response[action_input_start:action_input_end].strip()
                
                # 执行工具调用
                observation = self.knowledge_search(query)
                
                # 继续对话，加入 Observation
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {observation}\n\n请基于以上信息给出最终答案。"})
                
                print("\n" + "="*80)
                print("💡 最终回答:")
                print("="*80)
                
                final_response = self.llm.chat_stream(messages)
                
                # 提取 Answer
                if "Answer:" in final_response:
                    answer = final_response.split("Answer:")[-1].strip()
                else:
                    answer = final_response
                
                # 保存历史
                self.history.append({"role": "user", "content": user_question})
                self.history.append({"role": "assistant", "content": answer})
                
                return answer
            except Exception as e:
                print(f"\n❌ 解析失败: {e}")
                return response
        else:
            # 直接回答
            if "Answer:" in response:
                answer = response.split("Answer:")[-1].strip()
            else:
                answer = response
            
            # 保存历史
            self.history.append({"role": "user", "content": user_question})
            self.history.append({"role": "assistant", "content": answer})
            
            return answer


# ==================== 主程序 ====================
def init_sample_data(milvus: MilvusService, embedding: EmbeddingService):
    """初始化示例医疗数据"""
    print("\n📚 检查知识库数据...")
    
    # 检查是否已有数据
    if milvus.collection.num_entities > 0:
        print(f"✅ 知识库已有 {milvus.collection.num_entities} 条数据")
        return
    
    print("🔄 正在初始化示例医疗数据...")
    
    sample_data = [
        "感冒的常见症状包括：流鼻涕、打喷嚏、咳嗽、喉咙痛、轻度发热、头痛、肌肉酸痛。普通感冒通常在7-10天内自愈。",
        "高血压的诊断标准：收缩压≥140mmHg 或舒张压≥90mmHg。高血压患者应该低盐饮食、适量运动、戒烟限酒、保持良好心态。",
        "糖尿病的典型症状是'三多一少'：多饮、多食、多尿、体重减少。空腹血糖≥7.0mmol/L 或餐后2小时血糖≥11.1mmol/L 可诊断为糖尿病。",
        "发烧的处理方法：体温38.5℃以下可物理降温（温水擦浴、冰敷），38.5℃以上可服用退烧药（布洛芬、对乙酰氨基酚）。持续高热应及时就医。",
        "胃痛的常见原因：胃炎、胃溃疡、消化不良、胃食管反流。建议规律饮食、避免辛辣刺激食物、戒烟戒酒。持续疼痛应做胃镜检查。",
        "失眠的改善方法：保持规律作息、睡前避免使用电子设备、创造舒适睡眠环境、适量运动、避免咖啡因。严重失眠可考虑认知行为疗法。",
        "头痛的分类：紧张性头痛（最常见）、偏头痛、丛集性头痛。如果头痛伴随呕吐、视力模糊、意识改变，应立即就医。",
        "咳嗽的类型：干咳（无痰）和湿咳（有痰）。持续咳嗽超过3周应就医检查，排除肺炎、结核、肿瘤等疾病。",
        "腹泻的处理：轻度腹泻注意补充水分和电解质，可服用蒙脱石散。如果出现血便、高热、严重脱水，应立即就医。",
        "过敏性鼻炎症状：打喷嚏、流清涕、鼻塞、鼻痒。治疗包括避免过敏原、使用抗组胺药、鼻用激素喷雾剂。"
    ]
    
    # 生成向量
    embeddings = embedding.encode_batch(sample_data)
    
    # 插入数据库
    milvus.insert(sample_data, embeddings)
    print(f"✅ 成功插入 {len(sample_data)} 条医疗知识")


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║                               ║
║                                                              ║
║              基于 RAG 技术的医疗知识问答                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def select_model_type():
    """选择模型类型"""
    print("\n" + "="*60)
    print("请选择 LLM 模型:")
    print("1. DeepSeek (云端 API，需要网络和 API Key)")
    print("2. Qwen (本地模型，需要下载模型文件)")
    print("="*60)
    
    choice = input("请输入编号 (1/2): ").strip()
    
    if choice == "1":
        return "deepseek"
    elif choice == "2":
        return "qwen"
    else:
        print("❌ 输入错误，默认使用 DeepSeek")
        return "deepseek"


def main():
    """主函数"""
    print_banner()
    
    # 选择模型类型
    model_type = select_model_type()
    
    # 加载配置
    config = Config()
    config.MODEL_TYPE = model_type
    
    # 检查配置
    if model_type == "deepseek" and not config.DEEPSEEK_API_KEY:
        print("❌ 错误: 未设置 DEEPSEEK_API_KEY 环境变量")
        print("请运行: export DEEPSEEK_API_KEY='your-api-key'")
        sys.exit(1)
    
    if model_type == "qwen" and not os.path.exists(config.QWEN_MODEL_PATH):
        print(f"❌ 错误: Qwen 模型路径不存在: {config.QWEN_MODEL_PATH}")
        print("请确保已下载 Qwen 模型到指定路径")
        sys.exit(1)
    
    try:
        # 初始化服务
        print("\n🚀 正在初始化系统...")
        print("-" * 80)
        
        # 1. Embedding 服务
        embedding_service = EmbeddingService(config.EMBEDDING_MODEL, config.DEVICE)
        
        # 2. Milvus 服务
        milvus_service = MilvusService(
            config.MILVUS_HOST, 
            config.MILVUS_PORT, 
            config.MILVUS_COLLECTION,
            config.EMBEDDING_DIM
        )
        
        # 3. LLM 服务（根据选择初始化）
        if model_type == "deepseek":
            llm_service = DeepSeekService(
                config.DEEPSEEK_API_KEY,
                config.DEEPSEEK_API_URL,
                config.DEEPSEEK_MODEL
            )
        else:  # qwen
            llm_service = QwenService(
                config.QWEN_MODEL_PATH,
                config.QWEN_LORA_PATH,
                config.QWEN_OFFLOAD_DIR
            )
        
        # 初始化示例数据
        init_sample_data(milvus_service, embedding_service)
        
        # 创建 Agent
        agent = MedicalAgent(llm_service, embedding_service, milvus_service, config.TOP_K)
        
        print("\n" + "="*80)
        print("✅ 系统初始化完成！")
        print(f"📌 当前使用模型: {'DeepSeek (云端)' if model_type == 'deepseek' else 'Qwen (本地)'}")
        print("="*80)
        print("\n💡 使用说明:")
        print("  - 输入您的医疗健康问题")
        print("  - 输入 'exit' 或 'quit' 退出")
        print("  - 输入 'clear' 清空对话历史")
        print("="*80)
        
        # 交互循环
        while True:
            try:
                print("\n" + "🤔 " + "="*76)
                user_input = input("您的问题: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ['exit', 'quit', '退出']:
                    print("\n👋 感谢使用医疗助手，祝您健康！")
                    break
                
                if user_input.lower() in ['clear', '清空']:
                    agent.history = []
                    print("✅ 对话历史已清空")
                    continue
                
                # 运行 Agent
                answer = agent.run(user_input)
                
            except KeyboardInterrupt:
                print("\n\n👋 感谢使用医疗助手，祝您健康！")
                break
            except Exception as e:
                print(f"\n❌ 发生错误: {e}")
                import traceback
                traceback.print_exc()
    
    except Exception as e:
        print(f"\n❌ 系统初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
