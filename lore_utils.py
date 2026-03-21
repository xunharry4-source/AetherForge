"""
资料与工具集 (Lore Utils) - PGA 小说创作引擎通用工具库

本模块集成了系统运行所需的底层工具，是 RAG (检索增强生成) 架构的核心支撑。
核心功能设计:
1. 双库协同检索: 
   - MongoDB: 存储权威的设定定义 (Canon)、分类模板和结构化元数据。
   - ChromaDB: 存储设定内容的向量索引，支持跨维度的语义相似度搜索。
2. 动态 Context 组装: 根据用户 Query 自动路由，从禁止项、分类规则和历史文献中提取最相关的上下文。
3. API Key 生命周期管理: 实现多 Key 自动轮询 (Rotation) 和 429 错误自愈。
4. 模型工厂: 统一初始化带 JSON 模式支持的生成模型和嵌入模型。
"""
import os
import pymongo
import chromadb
import json
import re
from typing import Dict, List, Optional, Any
import time
from chromadb.config import Settings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from config_utils import load_config
try:
    from langfuse.callback import CallbackHandler
    HAS_LANGFUSE = True
except ImportError:
    HAS_LANGFUSE = False
    print("[WARN] langfuse-python not installed, LLM tracing disabled.")

HAS_DOCX = False
try:
    import docx
    HAS_DOCX = True
except ImportError:
    pass

HAS_PDF = False
try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    pass

# ==========================================
# API Key Manager (Global Singleton for the module)
# ==========================================
class APIKeyManager:
    def __init__(self):
        config = load_config()
        self.keys = config.get("GOOGLE_API_KEYS", [])
        if not self.keys:
            # Fallback to single key if list is missing
            single_key = config.get("GOOGLE_API_KEY")
            if single_key:
                self.keys = [single_key]
        self.index = 0
        
    def get_key(self):
        if not self.keys:
            return None
        return self.keys[self.index]
    
    def rotate(self):
        if len(self.keys) <= 1:
            return False
        self.index = (self.index + 1) % len(self.keys)
        print(f"[lore_utils] API Key Rotated to Index {self.index}")
        return True

_key_manager = APIKeyManager()

# --- LangFuse Callback Helper ---
def get_langfuse_callback():
    """Returns a LangFuse CallbackHandler if keys are configured."""
    config = load_config()
    pk = config.get("LANGFUSE_PUBLIC_KEY")
    sk = config.get("LANGFUSE_SECRET_KEY")
    host = config.get("LANGFUSE_HOST")
    
    if HAS_LANGFUSE and pk and sk:
        return CallbackHandler(
            public_key=pk, 
            secret_key=sk, 
            host=host
        )
    return None

# --- Prometheus Global Counter (Imported from app_api if needed) ---
# We use a lazy reference to avoids circular imports
_token_counter = None

def report_token_usage(model: str, prompt_tokens: int, completion_tokens: int, agent_name: str = "unknown"):
    """Reports token usage to Prometheus."""
    global _token_counter
    if _token_counter is None:
        try:
            from app_api import TOKEN_USAGE_COUNTER
            _token_counter = TOKEN_USAGE_COUNTER
        except ImportError:
            return
            
    if _token_counter:
        _token_counter.labels(model=model, token_type='prompt', agent=agent_name).inc(prompt_tokens)
        _token_counter.labels(model=model, token_type='completion', agent=agent_name).inc(completion_tokens)


# --- Lore Extraction & Sync ---

def clean_text(text: str) -> str:
    """清理文本：规范化换行，移除冗余空格和噪声数据"""
    if not text:
        return ""
    
    import re
    # 1. 规范化换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # 2. 移除连续的空行 (保留最多两个)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 3. 移除行尾空格
    text = re.sub(r'[ \t]+\n', '\n', text)
    
    # 4. 移除 PDF/Word 中常见的页码噪声 (简单模式)
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    
    return text.strip()

def extract_text_from_file(file_path: str) -> str:
    """从不同格式文件中提取文本"""
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    
    if ext == ".md" or ext == ".txt":
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    elif ext == ".json":
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            text = json.dumps(data, ensure_ascii=False, indent=2)
    elif ext == ".opml":
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read() # 简化处理，暂时直接读原始文本
    elif ext == ".docx":
        if not HAS_DOCX:
            raise RuntimeError("Missing docx dependency: pip install python-docx")
        doc = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs])
    elif ext == ".pdf":
        if not HAS_PDF:
            raise RuntimeError("PyPDF2 is not installed. Please install it to support .pdf files.")
        text = ""
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
    else:
        # 尝试作为纯文本读取
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except:
            raise ValueError(f"Unsupported file format: {ext}")
            
    if not text:
        return ""
        
    return clean_text(text)

def get_lore_by_doc_id(doc_id: str) -> Optional[Dict[str, Any]]:
    """通过 doc_id 快速获取完整实体"""
    # 优先尝试 MongoDB
    try:
        mongo_client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=1000)
        coll = mongo_client["pga_worldview"]["lore"]
        doc = coll.find_one({"doc_id": doc_id})
        if doc: 
            if "_id" in doc: del doc["_id"]
            return doc
    except Exception:
        pass
        
    # 后备尝试本地 JSON (JSONL 格式)
    try:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worldview_db.json")
        if not os.path.exists(db_path):
            db_path = "worldview_db.json"
            
        if os.path.exists(db_path):
            with open(db_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        data = json.loads(line)
                        if data.get("doc_id") == doc_id:
                            return data
                    except Exception:
                        continue
    except Exception:
        pass
    return None

def sync_lore_to_db(entity: Dict[str, Any]):
    """
    同步设定实体：
    1. 写入主库 (MongoDB/JSON) 存储完整父节点。
    2. 生成精细化子片段 (Children) 同步至 ChromaDB 进行索引。
    """
    # 1. 准备元数据
    if 'doc_id' not in entity:
        import uuid
        entity['doc_id'] = str(uuid.uuid4())
    if 'timestamp' not in entity:
        import datetime
        entity['timestamp'] = datetime.datetime.now().isoformat()
        
    # 2. 写入主库 (存储完整 Parent)
    try:
        mongo_client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
        db = mongo_client["pga_worldview"]
        coll = db["lore"]
        coll.update_one({"doc_id": entity["doc_id"]}, {"$set": entity}, upsert=True)
    except Exception:
        # Fallback to worldview_db.json
        with open("worldview_db.json", "a", encoding="utf-8") as f:
            f.write(json.dumps(entity, ensure_ascii=False) + "\n")

    # 3. 同步至 ChromaDB (父子结构)
    try:
        config = load_config()
        key = config.get("GOOGLE_API_KEY") or (config.get("GOOGLE_API_KEYS")[0] if config.get("GOOGLE_API_KEYS") else None)
            
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", 
            google_api_key=key,
            task_type="retrieval_document"
        )
        client = chromadb.PersistentClient(path="./chroma_db")
        vector_store = Chroma(
            client=client, 
            collection_name="pga_worldview_v1", 
            embedding_function=embeddings
        )
        
        # --- 实现父子切片逻辑 ---
        texts_to_index = []
        metadatas = []
        ids = []
        
        content = entity["content"]
        
        # A. 首先存储 Parent 节点本身 (用于兜底匹配)
        texts_to_index.append(content)
        metadatas.append({
            "name": entity["name"],
            "category": entity["category"],
            "doc_id": entity["doc_id"],
            "doc_type": "parent"
        })
        ids.append(entity["doc_id"])
        
        # B. 如果内容较长，生成子片段 (Children) 以提升检索精度
        if len(content) > 500:
            chunk_size = 200
            overlap = 50
            for i in range(0, len(content), chunk_size - overlap):
                chunk = content[i:i + chunk_size]
                if len(chunk) < 50: continue # 太短的片段略过
                
                texts_to_index.append(chunk)
                metadatas.append({
                    "name": entity["name"],
                    "parent_id": entity["doc_id"],
                    "category": entity["category"],
                    "doc_type": "child",
                    "chunk_index": i
                })
                ids.append(f"{entity['doc_id']}_chunk_{i}")
        
        # 执行批量写入
        vector_store.add_texts(
            texts=texts_to_index,
            metadatas=metadatas,
            ids=ids
        )
        print(f"[SYNC] Lore '{entity['name']}' synced with {len(texts_to_index)} indices (Parent-Child).")
        
    except Exception as e:
        print(f"[SYNC ERROR] ChromaDB sync failed for {entity['name']}: {e}")

def get_llm(json_mode=False):
    key = _key_manager.get_key()
    if not key:
        raise ValueError("GOOGLE_API_KEY missing. Please check config.json.")
    
    config = load_config()
    model_name = config.get("DEFAULT_MODEL", "gemini-2.0-flash")
    
    if json_mode:
        return ChatGoogleGenerativeAI(
            model=model_name, 
            google_api_key=key,
            model_kwargs={"response_mime_type": "application/json"}
        )
    return ChatGoogleGenerativeAI(model=model_name, google_api_key=key)

def parse_json_safely(text: str) -> Any:
    """
    更鲁棒地解析 LLM 返回的 JSON 字符串。
    1. 移除 Markdown 代码块标记 (```json ... ```)
    2. 自动修正尾部逗号 (Trailing Commas)
    3. 提取包含在文本中的 JSON 对象
    """
    if not text:
        return None
    
    # 清理 markdown 代码块
    cleaned = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()
    
    # 尝试提取第一个 { 或 [ 之后的内容
    if not (cleaned.startswith('{') or cleaned.startswith('[')):
        match = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
            
    # 修正尾部逗号 (匹配 , 后面跟着 } 或 ])
    cleaned = re.sub(r',\s*([\]}])', r'\1', cleaned)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[JSON Error] Failed to parse: {e}")
        print(f"[JSON Content] {cleaned[:200]}...")
        # 最后的尝试：ast.literal_eval (能处理单引号等)
        try:
            import ast
            return ast.literal_eval(cleaned)
        except Exception:
            return None

def get_vector_store():
    key = _key_manager.get_key()
    if not key:
        raise ValueError("GOOGLE_API_KEY missing for embeddings.")
    
    # 注意：搜索时使用 retrieval_query 以获得更高相关性
    emb = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001", 
        google_api_key=key, 
        task_type="retrieval_query"
    )
    client = chromadb.PersistentClient(path="./chroma_db")
    return Chroma(client=client, collection_name="pga_worldview_v1", embedding_function=emb)

def get_lore_collection_name():
    return "pga_worldview_v1"

def rotate_api_key():
    """暴露给外部的旋转接口"""
    return _key_manager.rotate()

def get_mongodb_db():
    try:
        mongo_client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
        mongo_client.server_info()
        return mongo_client["pga_worldview"]
    except Exception:
        return None

# --- Core Context Retrieval Logic ---

def get_prohibited_rules():
    """从数据库或本地文件动态获取禁止项目"""
    db = get_mongodb_db()
    try:
        if db is not None:
            rule_doc = db["prohibited_rules"].find_one({"name": "PGA核心禁令"})
            if rule_doc:
                return rule_doc["content"]
        
        # Fallback to local JSON
        if os.path.exists("worldview_db.json"):
            with open("worldview_db.json", "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        if data.get("category") == "prohibited_rules":
                            return data.get("content")
    except Exception:
        pass
    
    return "【最高禁令】禁止控制时间、禁止高维神明、禁止预测未来、禁止现实修改、禁止无限能量。"

def get_worldview_context_by_category(query):
    """
    根据查询内容识别涉及的世界观分类，并从 MongoDB/JSON 中检索“权威定义”。
    特别优先处理：种族 (Races) 和 势力 (Factions)。
    """
    category_map = {
        "race": ["种族", "智械", "机器", "生命", "熵族", "奥族", "秦族", "生物", "族群", "演化", "物种"],
        "geography": ["地理", "星域", "恒星", "行星", "戴森球", "环境", "坐标", "星区", "星系", "地形"],
        "faction": ["势力", "国家", "组织", "军团", "公约", "强国", "联邦", "帝国", "派系", "阵营"],
        "mechanism_tech": ["机制", "协议", "技术", "代偿", "热力学", "规则", "引擎", "武器", "装置", "科技", "原理"],
        "history": ["历史", "记录", "演变", "纪元", "战争", "变迁", "编年史", "事件"]
    }

    
    detected_categories = []
    potential_names = []
    for cat, keys in category_map.items():
        for k in keys:
            if k in query:
                detected_categories.append(cat)
                if len(k) >= 2: potential_names.append(k)
            
    if not detected_categories:
        return ""
        
    context_blocks = []
    try:
        if os.path.exists("worldview_db.json"):
            with open("worldview_db.json", "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    data = json.loads(line)
                    res_name = data.get("name", "")
                    res_path = data.get("path", "")
                    res_content = data.get("content", "")
                    
                    is_authority = False
                    if any(pn in res_name for pn in potential_names):
                        is_authority = True
                    
                    if not is_authority:
                        for cat in detected_categories:
                            if cat == "race" and ("种族" in res_path or "生命" in res_path):
                                is_authority = True
                            if cat == "faction" and ("势力" in res_path or "国家" in res_path or "组织" in res_path):
                                is_authority = True
                            if cat == "geography" and ("地理" in res_path or "星域" in res_path):
                                is_authority = True
                            if cat == "mechanism_tech" and ("机制" in res_path or "科技" in res_path or "技术" in res_path):
                                is_authority = True
                            if cat == "history" and ("历史" in res_path or "事件" in res_path):
                                is_authority = True

                                
                    if is_authority:
                        if any(pn in res_content for pn in potential_names) or any(pn in res_name for pn in potential_names):
                            context_blocks.append(f"【权威定义 - {res_path}】:\n{res_content}")
    except Exception:
        pass
        
def get_category_template(category):
    """从 MongoDB 或本地 JSON 获取分类模板及参考例子"""
    db = get_mongodb_db()
    try:
        if db is not None:
            template_doc = db["worldview_templates"].find_one({"category": category.lower()})
            if template_doc:
                template_doc.pop("_id", None)
                return template_doc
    except Exception:
        pass
        
    # Fallback to local JSON
    if os.path.exists("worldview_templates.json"):
        with open("worldview_templates.json", "r", encoding="utf-8") as f:
            templates = json.load(f)
            for t in templates:
                if t.get("category") == category.lower():
                    return t
    return None

def upsert_category_template(category, template_data):
    """保存或更新分类模板"""
    db = get_mongodb_db()
    data = template_data.copy()
    data["category"] = category.lower()
    
    # Try MongoDB
    try:
        if db is not None:
            db["worldview_templates"].update_one(
                {"category": category.lower()},
                {"$set": data},
                upsert=True
            )
            return True
    except Exception:
        pass
        
    # Fallback/Sync to local JSON
    all_templates = []
    if os.path.exists("worldview_templates.json"):
        with open("worldview_templates.json", "r", encoding="utf-8") as f:
            all_templates = json.load(f)
            
    # Update existing or append
    found = False
    for i, t in enumerate(all_templates):
        if t.get("category") == category.lower():
            all_templates[i] = data
            found = True
            break
    if not found:
        all_templates.append(data)
        
    with open("worldview_templates.json", "w", encoding="utf-8") as f:
        json.dump(all_templates, f, ensure_ascii=False, indent=2)
    return True

def delete_category_template(category):
    """删除指定分类模板"""
    cat_lower = category.lower()
    db = get_mongodb_db()
    
    # Delete from MongoDB
    try:
        if db is not None:
            db["worldview_templates"].delete_one({"category": cat_lower})
    except Exception:
        pass
    
    # Delete from local JSON
    if os.path.exists("worldview_templates.json"):
        with open("worldview_templates.json", "r", encoding="utf-8") as f:
            all_templates = json.load(f)
        
        original_len = len(all_templates)
        all_templates = [t for t in all_templates if t.get("category") != cat_lower]
        
        if len(all_templates) < original_len:
            with open("worldview_templates.json", "w", encoding="utf-8") as f:
                json.dump(all_templates, f, ensure_ascii=False, indent=2)
            return True
    return False

def add_new_category(category, name_zh, template_fields=None, example_fields=None):
    """新建一个完整的分类模板"""
    cat_lower = category.lower()
    
    # 检查是否已存在
    existing = get_category_template(cat_lower)
    if existing:
        return False, f"分类 '{category}' 已存在"
    
    data = {
        "category": cat_lower,
        "name_zh": name_zh,
        "template": template_fields or {"name": f"[{name_zh}名称]"},
        "example": example_fields or {"name": f"示例{name_zh}"}
    }
    
    success = upsert_category_template(cat_lower, data)
    return success, "创建成功" if success else "创建失败"

def get_all_templates():
    """获取所有分类模板，合并 MongoDB 和本地 JSON 数据"""
    db = get_mongodb_db()
    templates_dict = {}
    
    # 1. 首先加载本地 JSON 作为基准 (Fallback)
    if os.path.exists("worldview_templates.json"):
        try:
            with open("worldview_templates.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        cat = item.get("category")
                        if cat:
                            templates_dict[cat] = item
                elif isinstance(data, dict):
                    templates_dict.update(data)
        except Exception as e:
            print(f"Error loading local templates: {e}")
            
    # 2. 然后用 MongoDB 的数据覆盖/补充 (优先使用数据库中的自定义修改)
    try:
        if db is not None:
            cursor = db["worldview_templates"].find({})
            for doc in cursor:
                doc.pop("_id", None)
                cat = doc.get("category")
                if cat:
                    templates_dict[cat] = doc
    except Exception as e:
        print(f"Error loading MongoDB templates: {e}")
        
    return templates_dict



def get_unified_context(query, retry_on_429=True):
    """
    智能路由检索：自动处理 429 错误并尝试 Key 轮换
    """
    context_blocks = []
    
    # 1. 尝试从 MongoDB 检索权威定义 (Entity Design 意图)
    db = get_mongodb_db()
    if db is not None:
        try:
            # 简单文本匹配，优先找名称一致的
            cursor = db["lore"].find({"name": {"$regex": query, "$options": "i"}}).limit(3)
            for doc in cursor:
                context_blocks.append(f"【权威设定: {doc['name']}】\n{doc['content']}")
        except Exception:
            pass

    # 2. 尝试从 ChromaDB 检索背景资料 (Supportive Lore 意图)
    try:
        vector_store = get_vector_store()
        if vector_store:
            results = vector_store.similarity_search(query, k=5)
            for res in results:
                context_blocks.append(f"【背景资料: {res.metadata.get('name', '未命名')}】\n{res.page_content}")
    except Exception as e:
        if "429" in str(e) and retry_on_429:
            if rotate_api_key():
                print(f"[lore_utils] API Key Rotated. Retrying context retrieval...")
                return get_unified_context(query, retry_on_429=False)
        print(f"[lore_utils] ChromaDB Search Error: {e}")

    if context_blocks:
        unique_blocks = list(dict.fromkeys(context_blocks))
        return "\n\n".join(unique_blocks[:8])
    return ""

def get_grounded_context(query) -> List[Dict[str, str]]:
    """
    获取带索引的素材块，用于 NotebookLM 模式的强制锚定。
    返回: [{"id": "S1", "title": "...", "content": "..."}, ...]
    """
    sources = []
    
    # 1. MongoDB 权威设定
    db = get_mongodb_db()
    if db is not None:
        try:
            cursor = db["lore"].find({"name": {"$regex": query, "$options": "i"}}).limit(3)
            for doc in cursor:
                sources.append({
                    "id": f"S{len(sources)+1}",
                    "title": f"权威设定: {doc['name']}",
                    "content": doc['content']
                })
        except Exception:
            pass

    # 2. ChromaDB 背景资料
    try:
        vector_store = get_vector_store()
        if vector_store:
            results = vector_store.similarity_search(query, k=5)
            for res in results:
                sources.append({
                    "id": f"S{len(sources)+1}",
                    "title": f"背景资料: {res.metadata.get('name', '未命名')}",
                    "content": res.page_content
                })
    except Exception:
        pass
        
    return sources[:10]

def format_grounded_context_for_prompt(sources: List[Dict[str, str]]) -> str:
    """将素材块格式化为 Prompt 引用段落"""
    if not sources:
        return "【无相关源素材】"
    
    formatted = "### 可用源素材 (Sources):\n"
    for s in sources:
        formatted += f"[{s['id']}] {s['title']}\n{s['content']}\n\n"
    return formatted

def get_latest_book_outline():
    """获取最近一次保存的全局大纲"""
    if not os.path.exists('outlines_db.json'):
        return None
    try:
        with open('outlines_db.json', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if not lines: return None
            # 返回最后一行（最新记录）
            return json.loads(lines[-1].strip())
    except Exception as e:
        print(f"[lore_utils] Error reading outlines_db.json: {e}")
        return None

def get_outline_by_id(outline_id):
    """根据 ID 获取特定大纲内容"""
    if not os.path.exists('outlines_db.json'):
        return None
    try:
        with open('outlines_db.json', 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line.strip())
                if str(data.get('id')) == str(outline_id):
                    return data
    except Exception as e:
        print(f"[lore_utils] Error searching outline {outline_id}: {e}")
    return None


# ==========================================
# Entity Sentinel (实体哨兵) Utilities
# ==========================================

def get_entity_registry() -> Dict[str, List[str]]:
    """
    从 worldview_db.json 中扫描所有已注册实体的名称，按分类分组。
    返回格式: {"race": ["熵族", "奥族", ...], "faction": ["联邦", ...], ...}
    用于 A 层 - 在 Prompt 中注入已知实体清单，约束 LLM 优先复用。
    """
    registry: Dict[str, List[str]] = {}
    
    # 从本地 JSON 扫描
    if os.path.exists("worldview_db.json"):
        try:
            with open("worldview_db.json", "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    cat = data.get("category", "general")
                    name = data.get("name", "")
                    if name:
                        if cat not in registry:
                            registry[cat] = []
                        if name not in registry[cat]:
                            registry[cat].append(name)
        except Exception as e:
            print(f"[Entity Sentinel] Error scanning worldview_db.json: {e}")
    
    # 从 MongoDB 补充
    db = get_mongodb_db()
    if db is not None:
        try:
            cursor = db["lore"].find({}, {"name": 1, "category": 1})
            for doc in cursor:
                cat = doc.get("category", "general")
                name = doc.get("name", "")
                if name:
                    if cat not in registry:
                        registry[cat] = []
                    if name not in registry[cat]:
                        registry[cat].append(name)
        except Exception:
            pass
    
    return registry


def format_entity_registry_for_prompt(registry: Dict[str, List[str]]) -> str:
    """
    将实体注册表格式化为 Prompt 可注入的文本块。
    """
    if not registry:
        return "【已注册实体清单】暂无已注册实体。你可以自由创建，但请在输出中标注 new_entities。"
    
    lines = ["【已注册实体清单 — 优先使用以下实体，如需创建新实体请在 JSON 中增加 \"new_entities\": [{\"name\": \"...\", \"type\": \"...\", \"reason\": \"...\"}] 数组】"]
    for cat, names in registry.items():
        cat_label = {
            "race": "种族", "faction": "势力", "geography": "地理",
            "mechanism_tech": "科技/机制", "history": "历史事件",
            "planet": "星球", "creature": "生物", "weapon": "武器装备",
            "organization": "组织", "religion": "宗教", "crisis": "危机事件",
        }.get(cat, cat)
        lines.append(f"  - {cat_label}: {', '.join(names)}")
    
    return "\n".join(lines)


def register_draft_entity(entity_name: str, entity_type: str, source_context: str, 
                          source_agent: str = "unknown", entity_card: Optional[Dict] = None) -> bool:
    """
    将新发现的实体写入"待审区" entity_drafts_db.json。
    C 层 - 不直接入正式库，等待用户审批。
    
    Args:
        entity_name: 实体名称 (如 "凯恩")
        entity_type: 实体分类 (如 "character", "faction", "tech")
        source_context: 实体出现的上下文描述
        source_agent: 来源 Agent (如 "outline", "writing")
        entity_card: 完整的实体设定卡 (基于分类模板生成)
    """
    import datetime as _dt
    record = {
        "name": entity_name,
        "type": entity_type,
        "source_context": source_context,
        "source_agent": source_agent,
        "entity_card": entity_card or {},
        "status": "pending",  # pending / approved / rejected
        "created_at": _dt.datetime.now().isoformat()
    }
    try:
        with open("entity_drafts_db.json", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[Entity Sentinel] 新实体草案已登记: {entity_name} ({entity_type})")
        return True
    except Exception as e:
        print(f"[Entity Sentinel] 登记失败: {e}")
        return False



def get_draft_entities(status_filter: Optional[str] = "pending") -> List[Dict]:
    """获取待审实体列表。C 层 API 使用。"""
    drafts = []
    if not os.path.exists("entity_drafts_db.json"):
        return drafts
    try:
        with open("entity_drafts_db.json", "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                if status_filter is None or data.get("status") == status_filter:
                    drafts.append(data)
    except Exception as e:
        print(f"[Entity Sentinel] 读取草案库失败: {e}")
    return drafts


def approve_draft_entity(entity_name: str) -> bool:
    """
    批准待审实体 → 写入正式世界观库 (worldview_db.json)。
    C 层 - 用户在仪表盘上点"批准"后触发。
    如果草案包含完整的 entity_card（基于分类模板生成），则将其完整写入。
    """
    if not os.path.exists("entity_drafts_db.json"):
        return False
    
    all_drafts = []
    target = None
    try:
        with open("entity_drafts_db.json", "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("name") == entity_name and data.get("status") == "pending":
                    data["status"] = "approved"
                    target = data
                all_drafts.append(data)
    except Exception:
        return False
    
    if not target:
        return False
    
    # 更新草案库状态
    with open("entity_drafts_db.json", "w", encoding="utf-8") as f:
        for d in all_drafts:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    
    # 写入正式库 — 包含完整的实体设定卡
    entity_card = target.get("entity_card", {})
    if entity_card:
        content = json.dumps(entity_card, ensure_ascii=False, indent=2)
    else:
        content = f"[自动注册] {target.get('source_context', '')}"
    
    canon_record = {
        "name": target["name"],
        "category": target.get("type", "general"),
        "content": content,
        "path": f"自动注册/{target.get('type', 'general')}/{target['name']}"
    }
    with open("worldview_db.json", "a", encoding="utf-8") as f:
        f.write(json.dumps(canon_record, ensure_ascii=False) + "\n")
    
def sync_archive_to_all_stores(item_id: str, item_type: str, content: str, name: str = None) -> bool:
    """
    将修改后的条目同步到 MongoDB, ChromaDB 和技能系统 (SKILL)。
    """
    print(f"[lore_utils] Syncing {item_type} ID: {item_id} to all stores...")
    
    # 1. MongoDB Sync (For Worldview)
    if item_type == 'worldview':
        db = get_mongodb_db()
        if db is not None:
            try:
                # 统一更新到 lore 集合
                db["lore"].update_one(
                    {"doc_id": item_id},
                    {"$set": {"content": content, "name": name, "timestamp": datetime.now().isoformat()}},
                    upsert=True
                )
                print(f"[lore_utils] MongoDB sync success for {item_id}")
            except Exception as e:
                print(f"[lore_utils] MongoDB sync error: {e}")

    # 2. ChromaDB Sync (Vector Re-indexing)
    try:
        vector_store = get_vector_store()
        if vector_store:
            # 在 ChromaDB 中，我们通常使用 doc_id 作为 metadata 的一部分
            # 这里采取：先删除旧的，再插入新的（最简单的同步方式）
            # 注意：这需要 item_id 在 ChromaDB 中是唯一的标识符
            
            # 由于 LangChain Chroma 封装的原因，直接按 metadata 删除比较慢
            # 如果我们在存储时将 doc_id 设置为 Chroma ID，则可以直接 update
            
            # 获取 embedding 函数
            emb = vector_store.embeddings
            
            # 使用原生 client 进行操作以获得更好控制
            client = chromadb.PersistentClient(path="./chroma_db")
            collection = client.get_collection("pga_lore")
            
            # 尝试删除旧记录 (如果存在)
            # 注意：item_id 必须与存储时的 ID 一致
            try:
                collection.delete(ids=[item_id])
            except:
                pass
            
            # 生成新 embedding 并插入
            collection.add(
                ids=[item_id],
                documents=[content],
                metadatas=[{"name": name or "未命名", "type": item_type, "doc_id": item_id, "timestamp": datetime.now().isoformat()}]
            )
            print(f"[lore_utils] ChromaDB sync success for {item_id}")
    except Exception as e:
        print(f"[lore_utils] ChromaDB sync error: {e}")

    # 3. SKILL Sync (For Outlines)
    if item_type == 'outline':
        try:
            from lore_skill_converter import generate_modular_skills
            generate_modular_skills()
            print(f"[lore_utils] SKILL (ANCHORS) sync success for {item_id}")
        except Exception as e:
            print(f"[lore_utils] SKILL sync error: {e}")
            
    return True

from datetime import datetime
import datetime as _dt
