from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import chromadb
import pymongo
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pymongo import UpdateOne

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.config_utils import get_config


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


def get_api_keys() -> list[str]:
    config = get_config()
    keys = config.get("GOOGLE_API_KEYS") or []
    if not keys and config.get("GOOGLE_API_KEY"):
        keys = [config["GOOGLE_API_KEY"]]
    return [key for key in keys if key]


def build_vector_store(worldview_id: str, api_key: str) -> Chroma:
    safe_id = worldview_id.replace("-", "_")
    collection_name = f"pga_wv_{safe_id}"
    chroma_path = ROOT / "src" / "common" / "chroma_db"
    chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=api_key,
        task_type="retrieval_document",
    )
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


def upsert_chroma(records: list[dict[str, Any]], worldview_id: str, batch_size: int, sleep_seconds: float) -> int:
    keys = get_api_keys()
    if not keys:
        raise RuntimeError("GOOGLE_API_KEY/GOOGLE_API_KEYS is required for Chroma embeddings.")

    key_index = 0
    vector_store = build_vector_store(worldview_id, keys[key_index])
    written = 0

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        ids = [record["doc_id"] for record in batch]
        texts = [record["content"] for record in batch]
        metadatas = [chroma_metadata(record) for record in batch]

        while True:
            try:
                try:
                    vector_store.delete(ids=ids)
                except Exception:
                    pass
                vector_store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
                written += len(batch)
                print(f"[Chroma] {written}/{len(records)} records written")
                break
            except Exception as exc:
                message = str(exc).upper()
                if any(token in message for token in ("429", "RESOURCE_EXHAUSTED", "QUOTA")) and len(keys) > 1:
                    key_index = (key_index + 1) % len(keys)
                    print(f"[Chroma] quota hit, rotating to key #{key_index + 1}")
                    vector_store = build_vector_store(worldview_id, keys[key_index])
                    continue
                if any(token in message for token in ("429", "RESOURCE_EXHAUSTED", "QUOTA")):
                    print("[Chroma] quota hit, sleeping before retry")
                    time.sleep(max(30.0, sleep_seconds))
                    continue
                raise

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
        count = upsert_chroma(records, args.worldview_id, args.batch_size, args.sleep)
        print(f"[Chroma] upserted {count} vectors in collection pga_wv_{args.worldview_id.replace('-', '_')}")


if __name__ == "__main__":
    main()
