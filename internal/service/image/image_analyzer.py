"""
图片分析器
负责图片的 OCR 识别和多模态分析（LLaVA）
从原有的 image_service.py 迁移
"""
from typing import Dict, Any, AsyncGenerator
from PIL import Image, ImageEnhance
import io
import base64

from log import logger
from pkg.constants.constants import OLLAMA_BASE_URL, ENABLE_VISION, VISION_MODEL


class ImageAnalyzer:
    """图片分析器（单例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化图片分析器"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._vision_enabled = ENABLE_VISION
            self._vision_model = VISION_MODEL
    
    def ocr_image(self, image_bytes: bytes, filename: str) -> str:
        """
        OCR 文字识别
        
        Args:
            image_bytes: 图片字节流
            filename: 文件名
        
        Returns:
            识别出的文字
        """
        try:
            import pytesseract
            
            # 从字节流加载图片
            image = Image.open(io.BytesIO(image_bytes))
            
            # 图片预处理（提高 OCR 准确率）
            # 1. 转为灰度图
            if image.mode != 'L':
                image = image.convert('L')
            
            # 2. 增强对比度
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)
            
            # 3. 使用 Tesseract OCR 识别（中英文）
            text = pytesseract.image_to_string(
                image,
                lang='chi_sim+eng',  # 中文简体 + 英文
                config='--psm 3'     # 全自动页面分割
            )
            
            # 清理识别结果
            text = text.strip()
            
            if not text:
                logger.debug(f"图片 OCR 识别结果为空: {filename}")
                return "（图片中未识别到文字内容）"
            
            return text
            
        except ImportError:
            logger.warning("⚠️ pytesseract 未安装，跳过 OCR 识别")
            return "（系统未安装 OCR 组件）"
        except Exception as e:
            logger.error(f"❌ OCR 识别失败: {filename}, error={e}")
            return f"（OCR 识别失败：{str(e)}）"
    
    def llava_analyze_stream(self, image_bytes: bytes, filename: str):
        """
        使用 LLaVA (Ollama) 模型分析图片内容（流式）
        
        Args:
            image_bytes: 图片字节流
            filename: 文件名
        
        Yields:
            str: 图片内容描述片段
        """
        try:
            import ollama
            
            logger.info(f"🔍 使用 LLaVA 模型流式分析图片: {filename}")
            
            # 加载图片获取尺寸信息
            image = Image.open(io.BytesIO(image_bytes))
            image_width, image_height = image.size
            
            # 将图片转换为 base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # 构建综合提示词
            prompt = """请精简的描述这张图片，包括：
1. 图片的主要内容和场景
2. 能看到的物体和元素
3. 图片中正在发生的事情
4. 整体的风格和氛围

Please provide a simple description in Chinese."""
            
            # 调用 Ollama LLaVA（流式）
            full_description = ""
            for chunk in ollama.chat(
                model=self._vision_model,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [image_base64]
                }],
                stream=True
            ):
                content = chunk['message']['content']
                full_description += content
                yield content
            
            if not full_description.strip():
                yield self._simple_vision_analysis(image_bytes, filename)
            
        except ImportError:
            logger.error("❌ ollama 库未安装，请运行: pip install ollama")
            yield self._simple_vision_analysis(image_bytes, filename)
        except Exception as e:
            logger.error(f"❌ LLaVA 分析失败: {filename}, error={e}", exc_info=True)
            yield self._simple_vision_analysis(image_bytes, filename)
    
    def _simple_vision_analysis(self, image_bytes: bytes, filename: str) -> str:
        """
        简单的图片分析（基于 PIL 提取的图片特征）
        
        Args:
            image_bytes: 图片字节流
            filename: 文件名
        
        Returns:
            图片描述
        """
        try:
            import numpy as np
            
            # 加载图片
            image = Image.open(io.BytesIO(image_bytes))
            
            # 转换为RGB
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # 提取基本特征
            width, height = image.size
            aspect_ratio = width / height if height > 0 else 1
            
            # 分析主色调
            img_array = np.array(image.resize((100, 100)))
            avg_color = img_array.mean(axis=(0, 1))
            r, g, b = avg_color
            
            # 判断色调
            if r > 200 and g > 200 and b > 200:
                color_desc = "整体偏亮色调"
            elif r < 50 and g < 50 and b < 50:
                color_desc = "整体偏暗色调"
            elif r > g and r > b:
                color_desc = "整体偏暖色调（红色系）"
            elif b > r and b > g:
                color_desc = "整体偏冷色调（蓝色系）"
            elif g > r and g > b:
                color_desc = "整体偏绿色调"
            else:
                color_desc = "色调均衡"
            
            # 判断图片方向
            if aspect_ratio > 1.5:
                orientation = "横向构图"
            elif aspect_ratio < 0.66:
                orientation = "纵向构图"
            else:
                orientation = "方形构图"
            
            description = f"""这是一张 {width}x{height} 像素的{orientation}图片。
{color_desc}。

💡 提示：当前使用的是基础图片分析，仅能识别图片的基本特征。
如需更详细的物体识别、场景理解，建议启用 LLaVA 模型。"""
            
            return description
            
        except ImportError:
            logger.warning("⚠️ numpy 未安装，无法进行图片特征分析")
            return "（图片特征分析需要安装 numpy）"
        except Exception as e:
            logger.error(f"❌ 简单视觉分析失败: {filename}, error={e}")
            return f"（图片分析失败：{str(e)}）"
    
    async def analyze_image_stream(
        self,
        image_bytes: bytes,
        filename: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式分析图片内容（OCR + LLaVA）
        
        Args:
            image_bytes: 图片字节流
            filename: 文件名
        
        Yields:
            Dict: 分析进度事件
        """
        try:
            # 获取图片基本信息
            image = Image.open(io.BytesIO(image_bytes))
            image_info = {
                "width": image.width,
                "height": image.height,
                "format": image.format or "Unknown"
            }
            
            result = {
                "ocr_text": "",
                "vision_description": "",
                "image_info": image_info,
                "combined_content": ""
            }
            
            # 1. OCR 文字识别
            yield {
                "event": "thought",
                "data": {"content": "📝 正在识别图片中的文字（OCR）...\n"}
            }
            
            try:
                ocr_text = self.ocr_image(image_bytes, filename)
                result["ocr_text"] = ocr_text
                
                if ocr_text and ocr_text != "（图片中未识别到文字内容）":
                    yield {
                        "event": "thought",
                        "data": {"content": f"✅ OCR 识别完成，识别到文字：\n```\n{ocr_text}\n```\n\n"}
                    }
                else:
                    yield {
                        "event": "thought",
                        "data": {"content": "⚠️ 图片中未识别到文字内容\n\n"}
                    }
            except Exception as e:
                logger.error(f"OCR 识别失败: {e}")
                yield {
                    "event": "thought",
                    "data": {"content": f"⚠️ OCR 识别失败: {str(e)}\n\n"}
                }
            
            # 2. LLaVA 多模态图片内容识别（流式输出）
            yield {
                "event": "thought",
                "data": {"content": "🤖 正在使用 LLaVA 分析图片内容（物体、场景识别）...\n\n"}
            }
            
            try:
                vision_desc_full = ""
                
                for chunk in self.llava_analyze_stream(image_bytes, filename):
                    vision_desc_full += chunk
                    yield {
                        "event": "thought",
                        "data": {"content": chunk}
                    }
                
                result["vision_description"] = vision_desc_full
                
                yield {
                    "event": "thought",
                    "data": {"content": f"\n\n✅ 图片分析完成\n\n"}
                }
                
            except Exception as e:
                logger.error(f"LLaVA 分析失败: {e}")
                yield {
                    "event": "thought",
                    "data": {"content": f"⚠️ 图片内容识别失败: {str(e)}\n\n"}
                }
            
            # 3. 综合内容描述
            combined_parts = []
            
            if result["vision_description"]:
                combined_parts.append(f"【图片内容 - LLaVA 分析】\n{result['vision_description']}")
            
            if result["ocr_text"] and result["ocr_text"] != "（图片中未识别到文字内容）":
                combined_parts.append(f"【图片中的文字 - OCR 识别】\n{result['ocr_text']}")
            
            if not combined_parts:
                combined_parts.append("（图片分析未得到有效信息）")
            
            result["combined_content"] = "\n\n".join(combined_parts)
            
            # 返回完整结果
            yield {
                "event": "image_analysis_complete",
                "data": result
            }
            
        except Exception as e:
            logger.error(f"图片分析失败: {filename}, error={e}", exc_info=True)
            yield {
                "event": "thought",
                "data": {"content": f"❌ 图片分析失败：{str(e)}"}
            }
            yield {
                "event": "image_analysis_complete",
                "data": {"combined_content": f"（图片分析失败：{str(e)}）"}
            }


# 创建全局单例
image_analyzer = ImageAnalyzer()
