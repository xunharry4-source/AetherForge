import os
import json
import uuid
import datetime
import sys
import time

# 1. Add local libs to path
LIB_PATH = os.path.join(os.getcwd(), "libs")
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)
sys.setrecursionlimit(50000)

try:
    import marko
    from marko.block import Heading, Paragraph, List, ListItem
    import google.generativeai as genai
    import chromadb
except ImportError as e:
    print(f"[ERROR] Required libraries not found in ./libs: {e}")
    sys.exit(1)

# Configuration
# Configuration Helper
def load_config():
    config = {}
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"[CONFIG ERROR] Failed to load config.json: {e}")
    key = config.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return {"GOOGLE_API_KEY": key}

CONFIG = load_config()
GOOGLE_API_KEY = CONFIG.get("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("[ERROR] GOOGLE_API_KEY missing. Please fill it in config.json or set it as an env var.")
    sys.exit(1)

genai.configure(api_key=GOOGLE_API_KEY)

# DB Connection
chroma_client = chromadb.PersistentClient(path="./chroma_db")

def get_text_content(node):
    """Recursively extract text from a Marko node."""
    if hasattr(node, 'children'):
        if isinstance(node.children, list):
            return "".join([get_text_content(c) for c in node.children])
        return str(node.children)
    return ""

class LoreExtractor:
    def __init__(self):
        self.chunks = []
        self.header_stack = [] # (level, title)

    def process_node(self, node):
        # 1. Update Context (Headers)
        if isinstance(node, Heading):
            level = node.level
            title = get_text_content(node).strip()
            while self.header_stack and self.header_stack[-1][0] >= level:
                self.header_stack.pop()
            self.header_stack.append((level, title))
            
        # 2. Extract Content (From Paragraphs within headers/lists)
        elif isinstance(node, Paragraph):
            content = get_text_content(node).strip()
            if content and len(content) > 10:
                path = " > ".join([h[1] for h in self.header_stack]) or "Root"
                self.chunks.append({
                    "name": self.header_stack[-1][1] if self.header_stack else "General",
                    "category": self.header_stack[0][1] if self.header_stack else "General",
                    "path": path,
                    "content": f"[{path}]\n{content}"
                })
        
        # 3. Recurse into children
        if hasattr(node, 'children') and isinstance(node.children, list):
            for child in node.children:
                self.process_node(child)

def ingest(file_path):
    print(f"[START] Tree-Aware Parsing {file_path}...", flush=True)
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()

    doc = marko.parse(text)
    extractor = LoreExtractor()
    extractor.process_node(doc)
    
    total = len(extractor.chunks)
    print(f"[INFO] Extracted {total} context-rich chunks. Indexing into ChromaDB...", flush=True)
    
    # 4. Use native chromadb for stability
    try:
        # We need an embedding function for Chroma
        from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction
        emb_fn = GoogleGenerativeAiEmbeddingFunction(api_key=GOOGLE_API_KEY)
        collection = chroma_client.get_or_create_collection(name="pga_lore", embedding_function=emb_fn)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Chroma collection: {e}")
        return

    for i, chunk in enumerate(extractor.chunks):
        doc_id = str(uuid.uuid4())
        print(f"[{i+1}/{total}] {chunk['path']}... ", end="", flush=True)
        try:
            collection.add(
                documents=[chunk["content"]],
                metadatas=[{"name": chunk["name"], "path": chunk["path"], "category": chunk["category"]}],
                ids=[doc_id]
            )
            # Log to JSONL
            with open("worldview_db.json", "a", encoding="utf-8") as f:
                payload = {"doc_id": doc_id, **chunk, "timestamp": datetime.datetime.now().isoformat()}
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            print("OK.", flush=True)
            time.sleep(0.2) # Rate limit safety
        except Exception as e:
            print(f"FAIL: {e}", flush=True)
            
    print(f"[SUCCESS] Ingestion Finished. Total: {total}", flush=True)

if __name__ == "__main__":
    # Optional: Clear old collection
    try:
        chroma_client.delete_collection("pga_lore")
        print("[CLEANUP] Deleted old pga_lore collection.")
    except: pass
    
    ingest("科幻.md")
