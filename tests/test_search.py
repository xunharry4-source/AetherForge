from src.common.config_utils import load_config
from src.common.lore_utils import get_embedding_function
import sys

# 1. Check Config
config = load_config()

import time
import datetime
def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

try:
    from langchain_chroma import Chroma
    import chromadb

    log(
        f"Testing search with embedding provider: {config.get('EMBEDDING_PROVIDER', 'ollama')} "
        f"({config.get('OLLAMA_EMBEDDING_MODEL', 'embeddinggemma')})"
    )
    
    log("Initializing Embeddings...")
    embeddings = get_embedding_function(task_type="retrieval_query")
    
    log("Connecting to ChromaDB Client...")
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    
    log("Accessing Collection 'pga_lore'...")
    vector_store = Chroma(client=chroma_client, collection_name="pga_lore", embedding_function=embeddings)
    
    # Perform Search
    query = sys.argv[1] if len(sys.argv) > 1 else "奥族圣所"
    log(f"Starting Similarity Search for: '{query}'...")
    
    start_t = time.time()
    results = vector_store.similarity_search(query, k=5)
    end_t = time.time()
    
    log(f"Search Finished in {end_t - start_t:.2f}s")
    
    if results:
        log(f"Found {len(results)} results.")
        for i, res in enumerate(results):
            meta = res.metadata
            print(f"--- Result {i+1} ---")
            print(f"Path: {meta.get('path', 'N/A')}")
            print(f"Name: {meta.get('name', 'N/A')}")
            print(f"Content Sample: {res.page_content[:200].replace('\n', ' ')}...")
    else:
        log("No results found.")

except Exception as e:
    log(f"CRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
