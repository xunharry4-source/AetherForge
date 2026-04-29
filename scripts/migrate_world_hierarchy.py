"""Idempotently migrate MongoDB data to world -> [worldview, novel] -> outline -> chapter links."""
import datetime
import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.common.lore_utils import get_mongodb_db


DEFAULT_WORLD_ID = "world_default"
DEFAULT_WORLDVIEW_ID = "default_wv"
DEFAULT_NOVEL_ID = "novel_default"


def now_iso() -> str:
    return datetime.datetime.now().isoformat()


def migrate_world_hierarchy() -> dict:
    db = get_mongodb_db()
    migration_timestamp = now_iso()
    result = {
        "worlds_upserted": 0,
        "worldviews_updated": 0,
        "novels_upserted": 0,
        "outlines_updated": 0,
        "prose_updated": 0,
        "lore_updated": 0,
        "default_timestamps_updated": 0,
    }

    world_res = db["worlds"].update_one(
        {"world_id": DEFAULT_WORLD_ID},
        {
            "$setOnInsert": {
                "world_id": DEFAULT_WORLD_ID,
                "name": "默认世界",
                "summary": "迁移前的世界观、小说、大纲和章节默认归属到这里。",
                "timestamp": migration_timestamp,
            }
        },
        upsert=True,
    )
    result["worlds_upserted"] += int(bool(world_res.upserted_id))

    worldview_res = db["worldviews"].update_one(
        {"worldview_id": DEFAULT_WORLDVIEW_ID},
        {
            "$setOnInsert": {
                "worldview_id": DEFAULT_WORLDVIEW_ID,
                "world_id": DEFAULT_WORLD_ID,
                "name": "默认世界观 (Default Worldview)",
                "summary": "系统的初始宇宙设定。",
                "timestamp": migration_timestamp,
            }
        },
        upsert=True,
    )
    result["worldviews_updated"] += worldview_res.modified_count + int(bool(worldview_res.upserted_id))

    result["worldviews_updated"] += db["worldviews"].update_many(
        {"world_id": {"$exists": False}},
        {"$set": {"world_id": DEFAULT_WORLD_ID}},
    ).modified_count

    default_novel_res = db["novels"].update_one(
        {"novel_id": DEFAULT_NOVEL_ID},
        {
            "$setOnInsert": {
                "novel_id": DEFAULT_NOVEL_ID,
                "world_id": DEFAULT_WORLD_ID,
                "name": "默认小说",
                "summary": "迁移前未归属大纲和章节的默认小说容器。",
                "timestamp": migration_timestamp,
            }
        },
        upsert=True,
    )
    result["novels_upserted"] += int(bool(default_novel_res.upserted_id))
    result["default_timestamps_updated"] += db["worldviews"].update_many(
        {"worldview_id": DEFAULT_WORLDVIEW_ID, "timestamp": "N/A"},
        {"$set": {"timestamp": migration_timestamp}},
    ).modified_count
    result["default_timestamps_updated"] += db["novels"].update_many(
        {"novel_id": DEFAULT_NOVEL_ID, "timestamp": "N/A"},
        {"$set": {"timestamp": migration_timestamp}},
    ).modified_count
    result["default_timestamps_updated"] += db["worlds"].update_many(
        {"world_id": DEFAULT_WORLD_ID, "timestamp": "N/A"},
        {"$set": {"timestamp": migration_timestamp}},
    ).modified_count

    for outline in db["outlines"].find({}):
        outline_id = outline.get("outline_id") or outline.get("id")
        if not outline_id:
            continue
        world_id = outline.get("world_id") or DEFAULT_WORLD_ID
        novel_id = outline.get("novel_id") or f"novel_for_{outline_id}"
        novel_res = db["novels"].update_one(
            {"novel_id": novel_id},
            {
                "$setOnInsert": {
                    "novel_id": novel_id,
                    "world_id": world_id,
                    "name": outline.get("name") or outline.get("title") or f"小说 {outline_id}",
                    "summary": outline.get("summary") or outline.get("content") or "",
                    "timestamp": outline.get("timestamp") or now_iso(),
                }
            },
            upsert=True,
        )
        result["novels_upserted"] += int(bool(novel_res.upserted_id))
        outline_res = db["outlines"].update_one(
            {"_id": outline["_id"]},
            {"$set": {"novel_id": novel_id, "worldview_id": outline.get("worldview_id") or DEFAULT_WORLDVIEW_ID, "world_id": world_id}},
        )
        result["outlines_updated"] += outline_res.modified_count

    db["novels"].update_many({"worldview_id": {"$exists": True}}, {"$unset": {"worldview_id": ""}})

    for prose in db["prose"].find({}):
        outline_id = prose.get("outline_id")
        outline = db["outlines"].find_one({"$or": [{"outline_id": outline_id}, {"id": outline_id}]}) if outline_id else None
        novel_id = prose.get("novel_id") or (outline or {}).get("novel_id") or DEFAULT_NOVEL_ID
        worldview_id = prose.get("worldview_id") or (outline or {}).get("worldview_id") or DEFAULT_WORLDVIEW_ID
        world_id = prose.get("world_id") or (outline or {}).get("world_id") or DEFAULT_WORLD_ID
        prose_res = db["prose"].update_one(
            {"_id": prose["_id"]},
            {"$set": {"novel_id": novel_id, "worldview_id": worldview_id, "world_id": world_id}},
        )
        result["prose_updated"] += prose_res.modified_count

    result["lore_updated"] += db["lore"].update_many(
        {"world_id": {"$exists": False}},
        {"$set": {"world_id": DEFAULT_WORLD_ID}},
    ).modified_count

    return result


if __name__ == "__main__":
    print(migrate_world_hierarchy())
