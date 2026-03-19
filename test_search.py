from config_utils import load_config
import sys
import os

# 1. Check Config
config = load_config()
google_key = config.get("GOOGLE_API_KEY")

if not google_key:
    print("[ERROR] No API key found in config.json")
    sys.exit(1)

import time
import datetime
def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

try:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    from langchain_chroma import Chroma
    import chromadb

    log(f"Testing search with key: {google_key[:8]}...")
    
    log("Initializing Embeddings...")
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001", 
        google_api_key=google_key, 
        task_type="retrieval_query"
    )
    
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
