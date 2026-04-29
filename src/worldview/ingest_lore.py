import os
import json
import uuid
import datetime
import sys
import time
import xml.etree.ElementTree as ET

# 1. Use LangChain wrappers for Chroma and configured embeddings.
try:
    from langchain_chroma import Chroma
    import chromadb
except ImportError as e:
    print(f"[ERROR] Required libraries not found: {e}", flush=True)
    sys.exit(1)

# Configuration Helper
from src.common.config_utils import get_config
from src.common.lore_utils import get_embedding_function

CONFIG = get_config()
print(
    f"[DEBUG] Embedding provider: {CONFIG.get('EMBEDDING_PROVIDER', 'ollama')}, "
    f"Ollama model: {CONFIG.get('OLLAMA_EMBEDDING_MODEL', 'embeddinggemma')}",
    flush=True
)

# DB Connection
print("[DEBUG] Connecting to ChromaDB at ./chroma_db...", flush=True)
chroma_client = chromadb.PersistentClient(path="./chroma_db")
print("[DEBUG] ChromaDB Connected.", flush=True)

def get_opml_chunks(file_path):
    print(f"[START] OPML Structural Parsing {file_path}...", flush=True)
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        body = root.find('body')
        if body is None:
            return []
    except Exception as e:
        print(f"[ERROR] Failed to parse OPML: {e}")
        raise e

    chunks = []

    def walk(node, path_stack):
        title = node.get('text', '').strip()
        # Some OPML nodes might have text in '_note' or other attributes, 
        # but standard is 'text'.
        
        children = list(node)
        
        # Current node is a header if it has children
        if children:
            new_stack = path_stack + [title] if title else path_stack
            
            # Group all immediate leaf children as the "content" of this header
            leaf_texts = []
            for child in children:
                if len(list(child)) == 0:
                    t = child.get('text', '').strip()
                    if t:
                        leaf_texts.append(t)
            
            if leaf_texts:
                full_path = " > ".join(new_stack)
                content = "\n".join(leaf_texts)
                if len(content) > 10:
                    chunks.append({
                        "name": title or (path_stack[-1] if path_stack else "General"),
                        "category": new_stack[0] if new_stack else "General",
                        "path": full_path,
                        "content": f"[{full_path}]\n{content}"
                    })
            
            # Recurse into children that are headers themselves
            for child in children:
                if len(list(child)) > 0:
                    walk(child, new_stack)
        else:
            # This is a leaf node handled by the parent's grouping logic
            pass

    for outline in body:
        walk(outline, [])
        
    return chunks

class APIKeyManager:
    def __init__(self, keys):
        self.keys = keys
        self.index = 0
    
    def get_current_key(self):
        if not self.keys:
            return None
        return self.keys[self.index]
    
    def rotate(self):
        if not self.keys or len(self.keys) <= 1:
            return False
        self.index = (self.index + 1) % len(self.keys)
        print(f"[ROTATE] Switching to API Key #{self.index + 1}...", flush=True)
        return True

def ingest(opml_path):
    # 1. Load config and optional keys
    config = get_config()
    all_keys = config.get("GOOGLE_API_KEYS", [])
    key_manager = APIKeyManager(all_keys)
    
    # 2. Parse OPML
    if opml_path.endswith(".opml"):
        chunks = get_opml_chunks(opml_path)
    else:
        print(f"[WARN] Unsupported file type for structural ingestion: {opml_path}")
        return

    if not chunks:
        print("[ERROR] No chunks extracted from OPML.")
        return

    total = len(chunks)
    print(f"[INFO] Extracted {total} hierarchical chunks. Indexing into ChromaDB...", flush=True)
    
    # 3. Handle Vector Store with Rotation capability
    def init_vector_store():
        embeddings = get_embedding_function(task_type="retrieval_document")
        import chromadb
        client = chromadb.PersistentClient(path="./chroma_db")
        return Chroma(
            client=client, 
            collection_name="pga_lore", 
            embedding_function=embeddings
        )

    try:
        vector_store = init_vector_store()
        print("[DEBUG] Vector Store initialized.", flush=True)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Vector Store: {e}")
        raise e

    # 4. Handle resuming from previous state
    indexed_paths = set()
    if os.path.exists("worldview_db.json"):
        with open("worldview_db.json", "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    indexed_paths.add(data.get("path", "") + data.get("content", ""))
                except Exception as e:
                    print(f"[WARN] Failed to parse line in worldview_db: {e}")
                    continue
    
    for chunk in chunks:
        chunk["doc_id"] = str(uuid.uuid4())
        chunk["timestamp"] = datetime.datetime.now().isoformat()

    retry_budget = max(len(all_keys), 1) * 2
    print(f"[INFO] Ingesting {len(chunks)} chunks using configured embeddings (Skipping already indexed)...", flush=True)
    
    count = 0
    for i, chunk in enumerate(chunks):
        unique_key = chunk.get("path", "") + chunk.get("content", "")
        if unique_key in indexed_paths:
            continue

        success = False
        for attempt in range(retry_budget): # Retry across keys if using a key-backed provider
            try:
                vector_store.add_texts(
                    texts=[chunk['content']],
                    metadatas=[{
                        "name": chunk['name'],
                        "category": chunk['category'],
                        "path": chunk['path']
                    }],
                    ids=[chunk['doc_id']]
                )
                success = True
                break
            except Exception as e:
                err_msg = str(e).upper()
                if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "QUOTA" in err_msg:
                    print(f"[QUOTA EXCEEDED] Key #{key_manager.index + 1} exhausted.", flush=True)
                    if key_manager.rotate():
                        # Re-initialize vector store with NEW key
                        vector_store = init_vector_store()
                        continue # Retry immediately with new key
                    else:
                        print("[WAIT] All keys exhausted or only one key available. Waiting 70s...", flush=True)
                        time.sleep(70)
                else:
                    print(f"[RETRY {attempt+1}] '{chunk['path']}': {e}", flush=True)
                    time.sleep(5)
        
        if success:
            with open("worldview_db.json", "a", encoding="utf-8") as f:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            
            count += 1
            print(f"[{i+1}/{len(chunks)}] '{chunk['path']}' indexed... OK.", flush=True)
            time.sleep(1) # Faster with multi-keys (1s delay instead of 5s)
        else:
            print(f"[FAILED] '{chunk['path']}' after all key rotations.", flush=True)
            
    print(f"[SUCCESS] Ingestion process completed. New chunks: {count}", flush=True)

if __name__ == "__main__":
    # 1. Check for OPML file
    target_file = "科幻.opml"
    if not os.path.exists(target_file):
        print(f"[ERROR] Target file {target_file} not found.")
        sys.exit(1)

    # 2. Skip Cleanup to support Resuming
    # try:
    #     chroma_client.delete_collection("pga_lore")
    #     print("[CLEANUP] Deleted old pga_lore collection.")
    # except Exception as e:
    #     print(f"[CLEANUP] Collection pga_lore not found: {e}")
    # 
    # if os.path.exists("worldview_db.json"):
    #     os.remove("worldview_db.json")
    #     print("[CLEANUP] Deleted stale worldview_db.json.")
    
    ingest(target_file)
