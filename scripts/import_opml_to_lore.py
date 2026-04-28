from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import chromadb
import pymongo
from langchain_chroma import Chroma
from pymongo import UpdateOne

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.config_utils import get_config
from src.common.ollama_embeddings import OllamaEmbeddings


def parse_opml(path: Path, worldview_id: str) -> list[dict[str, Any]]:
    tree = ET.parse(path)
    body = tree.getroot().find("body")
    if body is None:
        return []

    records: list[dict[str, Any]] = []
    now = dt.datetime.now().isoformat()

    def walk(node: ET.Element, stack: list[str]) -> None:
        title = (node.get("text") or "").strip()
        children = list(node)
        current = stack + [title] if title else stack

        if not children:
            return

        leaf_texts = []
        for child in children:
            if not list(child):
                text = (child.get("text") or "").strip()
                if text:
                    leaf_texts.append(text)

        if leaf_texts and current:
            path_text = " > ".join(current)
            content = "[OPML层级]\n" + path_text + "\n\n" + "\n".join(f"- {text}" for text in leaf_texts)
            digest = hashlib.sha1(f"{worldview_id}|{path_text}|{content}".encode("utf-8")).hexdigest()
            records.append(
                {
                    "doc_id": f"opml_{digest[:20]}",
                    "name": current[-1],
                    "category": current[1] if len(current) > 1 else current[0],
                    "path": path_text,
                    "path_segments": current,
                    "parent_path": " > ".join(current[:-1]),
                    "root": current[0],
                    "depth": len(current),
                    "leaf_count": len(leaf_texts),
                    "content": content,
                    "source_file": path.name,
                    "source_type": "opml",
                    "content_sha1": digest,
                    "worldview_id": worldview_id,
                    "timestamp": now,
                }
            )

        for child in children:
            if list(child):
                walk(child, current)

    for outline in body:
        walk(outline, [])

    return records


def get_mongo_db() -> Any:
    config = get_config()
    uri = config.get("MONGO_URI", "mongodb://localhost:27017/")
    db_name = config.get("MONGO_DB_NAME", "pga_worldview")
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client[db_name]


def upsert_mongo(records: list[dict[str, Any]], worldview_id: str, worldview_name: str) -> int:
    db = get_mongo_db()
    db["worldviews"].update_one(
        {"worldview_id": worldview_id},
        {
            "$set": {
                "worldview_id": worldview_id,
                "name": worldview_name,
                "summary": f"Imported from {worldview_name}.opml with OPML hierarchy preserved.",
                "updated_at": dt.datetime.now().isoformat(),
            },
            "$setOnInsert": {"created_at": dt.datetime.now().isoformat()},
        },
        upsert=True,
    )

    operations = [
        UpdateOne(
            {"doc_id": record["doc_id"]},
            {"$set": record, "$setOnInsert": {"created_at": dt.datetime.now().isoformat()}},
            upsert=True,
        )
        for record in records
    ]
    if not operations:
        return 0
    result = db["lore"].bulk_write(operations, ordered=False)
    return int(result.upserted_count + result.modified_count + result.matched_count)


def get_chroma_collection_name(worldview_id: str) -> str:
    safe_id = worldview_id.replace("-", "_")
    return f"pga_wv_{safe_id}"


def get_chroma_path() -> Path:
    chroma_path = ROOT / "src" / "common" / "chroma_db"
    chroma_path.mkdir(parents=True, exist_ok=True)
    return chroma_path


def reset_chroma_collection(worldview_id: str) -> None:
    client = chromadb.PersistentClient(path=str(get_chroma_path()))
    collection_name = get_chroma_collection_name(worldview_id)
    try:
        client.delete_collection(collection_name)
        print(f"[Chroma] reset collection {collection_name}")
    except Exception:
        print(f"[Chroma] collection {collection_name} did not exist")


def build_vector_store(worldview_id: str, ollama_model: str, ollama_url: str) -> Chroma:
    client = chromadb.PersistentClient(path=str(get_chroma_path()))
    embeddings = OllamaEmbeddings(model=ollama_model, base_url=ollama_url)
    collection_name = get_chroma_collection_name(worldview_id)
    return Chroma(client=client, collection_name=collection_name, embedding_function=embeddings)


def chroma_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": record["doc_id"],
        "doc_type": "parent",
        "name": record["name"],
        "category": record["category"],
        "path": record["path"],
        "parent_path": record["parent_path"],
        "root": record["root"],
        "depth": record["depth"],
        "leaf_count": record["leaf_count"],
        "source_file": record["source_file"],
        "source_type": record["source_type"],
        "content_sha1": record["content_sha1"],
        "worldview_id": record["worldview_id"],
    }


def upsert_chroma(
    records: list[dict[str, Any]],
    worldview_id: str,
    batch_size: int,
    sleep_seconds: float,
    ollama_model: str,
    ollama_url: str,
) -> int:
    vector_store = build_vector_store(worldview_id, ollama_model, ollama_url)
    written = 0

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        ids = [record["doc_id"] for record in batch]
        texts = [record["content"] for record in batch]
        metadatas = [chroma_metadata(record) for record in batch]

        try:
            vector_store.delete(ids=ids)
        except Exception:
            pass
        vector_store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
        written += len(batch)
        print(f"[Chroma] {written}/{len(records)} records written")

        if sleep_seconds:
            time.sleep(sleep_seconds)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Import OPML hierarchy into MongoDB and ChromaDB lore stores.")
    parser.add_argument("opml", nargs="?", default="科幻.opml")
    parser.add_argument("--worldview-id", default="kehuan")
    parser.add_argument("--worldview-name", default="科幻")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--skip-mongo", action="store_true")
    parser.add_argument("--skip-chroma", action="store_true")
    parser.add_argument("--reset-chroma", action="store_true")
    parser.add_argument("--ollama-model", default=None)
    parser.add_argument("--ollama-url", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    opml_path = (ROOT / args.opml).resolve()
    records = parse_opml(opml_path, args.worldview_id)
    print(f"[Parse] {opml_path.name}: {len(records)} hierarchy records")
    if records:
        print(f"[Parse] sample: {records[0]['path']}")

    if args.dry_run:
        return

    if not args.skip_mongo:
        count = upsert_mongo(records, args.worldview_id, args.worldview_name)
        print(f"[Mongo] upserted/matched {count} lore records in worldview_id={args.worldview_id}")

    if not args.skip_chroma:
        config = get_config()
        ollama_model = args.ollama_model or config.get("OLLAMA_EMBEDDING_MODEL") or "embeddinggemma"
        ollama_url = args.ollama_url or config.get("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
        if args.reset_chroma:
            reset_chroma_collection(args.worldview_id)
        count = upsert_chroma(records, args.worldview_id, args.batch_size, args.sleep, ollama_model, ollama_url)
        print(f"[Chroma] upserted {count} vectors in collection {get_chroma_collection_name(args.worldview_id)}")


if __name__ == "__main__":
    main()
