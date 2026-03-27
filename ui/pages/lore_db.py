from nicegui import ui
import json
import os
import sys
import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_api import get_all_lore_items
from lore_utils import get_db_path
from ui.layout import page_layout

FLASK_API = 'http://localhost:5005'


def _save_draft_direct(doc_id, new_name, new_content):
    """Directly update a draft entry in entity_drafts_db.json."""
    draft_name = str(doc_id).replace('draft_', '', 1)
    if not os.path.exists(get_db_path("entity_drafts_db.json")):
        raise FileNotFoundError('entity_drafts_db.json not found')

    all_drafts = []
    found = False
    with open(get_db_path("entity_drafts_db.json"), 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get('name') == draft_name and not found:
                # Update matching draft
                # Strip the [DRAFT] prefix if present in the new name
                clean_name = new_name.replace('[DRAFT] ', '')
                entry['name'] = clean_name
                entry['description'] = new_content
                entry['proposal'] = new_content
                found = True
            all_drafts.append(entry)

    if not found:
        raise ValueError(f'Draft "{draft_name}" not found')

    with open(get_db_path("entity_drafts_db.json"), 'w', encoding='utf-8') as f:
        for d in all_drafts:
            f.write(json.dumps(d, ensure_ascii=False) + '\n')


def build_tree_data(docs):
    """从扁平的文档数据构建分层树结构。"""
    tree_data = {"id": "root", "label": "全部知识条目", "children": [], "icon": "folder"}

    def get_or_create_child(parent, label, node_id):
        for child in parent["children"]:
            if child["label"] == label:
                return child
        new_node = {"id": node_id, "label": label, "children": [], "icon": "folder"}
        parent["children"].append(new_node)
        return new_node

    for doc in docs:
        cat_path = doc.get("category", "未分类")
        parts = [p.strip() for p in cat_path.split(">")]

        curr = tree_data
        curr_id = "root"
        for part in parts:
            curr_id = f"{curr_id}/{part}"
            curr = get_or_create_child(curr, part, curr_id)

        doc_id = doc.get('id', doc.get('name', 'unknown'))
        leaf_id = f"leaf::{doc_id}"
        type_label = doc.get('type', 'entry').upper()
        # Translate type label if possible
        type_map = {'WORLDVIEW': '世界观', 'OUTLINE': '大纲', 'PROSE': '正文', 'DRAFT': '草案'}
        display_type = type_map.get(type_label, type_label)
        
        name = doc.get('name', '未命名')
        curr["children"].append({
            "id": leaf_id,
            "label": f"[{display_type}] {name}",
            "icon": "description",
        })
    return [tree_data]


def _find_doc_by_id(docs, doc_id):
    for d in docs:
        if d.get('id') == doc_id:
            return d
    return None


@ui.page('/lore')
def lore_db_page():
    # 状态
    all_docs = get_all_lore_items()
    tree_format = build_tree_data(all_docs)
    state = {'selected_doc': None}

    with page_layout():
        ui.label('世界观知识库浏览器').classes('text-2xl font-bold text-white mb-2')
        ui.label('浏览、编辑或删除设定库中的条目。').classes('text-slate-400 text-sm mb-6')

        with ui.tabs().classes('w-full') as tabs:
            tab_tree = ui.tab('分类浏览', icon='account_tree')
            tab_graph = ui.tab('实体关系图', icon='hub')
            tab_mindmap = ui.tab('知识思维导图', icon='psychology')

        with ui.tab_panels(tabs, value=tab_tree).classes('w-full bg-transparent'):
            # --- Tab 1: Tree View with Search ---
            with ui.tab_panel(tab_tree).classes('p-0'):
                with ui.row().classes('w-full items-center gap-4 mb-4 bg-slate-800/40 p-3 rounded-lg border border-slate-700'):
                    ui.icon('search', size='sm').classes('text-slate-500')
                    ui.icon('search', size='sm').classes('text-slate-500')
                    search_input = ui.input(placeholder='搜索实体名称、内容或标签...', on_change=lambda e: filter_tree(e.value)).props('borderless clearable').classes('flex-grow text-white pb-0')
                    semantic_toggle = ui.switch('语义搜索').props('color="cyan" size="sm"').classes('text-[10px] text-slate-400')
                    ui.label('快速检索控制台').classes('text-[10px] text-slate-500 uppercase font-bold px-2 py-1 bg-black/50 rounded')

                with ui.splitter(value=35).classes('w-full h-[600px]') as splitter:
                    with splitter.before:
                        with ui.column().classes('w-full h-full'):
                            ui.label('分类树').classes('text-sm font-bold text-slate-400 mb-2')

                            def on_select(e):
                                node_id = e.value
                                if not node_id or not str(node_id).startswith('leaf::'):
                                    detail_container.refresh(None)
                                    return
                                real_id = str(node_id).replace('leaf::', '')
                                doc = _find_doc_by_id(all_docs, real_id)
                                state['selected_doc'] = doc
                                detail_container.refresh(doc)

                            tree = ui.tree(
                                tree_format,
                                label_key='label',
                                on_select=on_select
                            ).classes('w-full text-white')

                            async def filter_tree(query):
                                if not query:
                                    tree.nodes = tree_format
                                    return
                                query = query.lower()
                                
                                if semantic_toggle.value:
                                    # Use Backend Semantic Search
                                    try:
                                        async with httpx.AsyncClient() as client:
                                            res = await client.post(f'{FLASK_API}/api/search', json={'query': query}, timeout=10)
                                            if res.status_code == 200:
                                                filtered = res.json()
                                            else:
                                                ui.notify(f"语义搜索失败: {res.status_code}", type='negative')
                                                return
                                    except Exception as ex:
                                        ui.notify(f"搜索请求出错: {ex}", type='negative')
                                        return
                                else:
                                    # Use Client-side Keyword Filter
                                    filtered = [d for d in all_docs if 
                                                query in (d.get('name') or '').lower() or 
                                                query in (d.get('content') or '').lower() or
                                                query in (d.get('category') or '').lower()]
                                                
                                tree.nodes = build_tree_data(filtered)
                                detail_container.refresh(None)

                    with splitter.after:
                        @ui.refreshable
                        def detail_container(doc=None):
                            if doc is None:
                                with ui.column().classes('w-full h-full items-center justify-center'):
                                    ui.icon('arrow_back', size='3rem').classes('text-slate-600 mb-2')
                                    ui.label('从树中选择一个条目以查看详细信息。').classes('text-slate-500 text-sm')
                                return

                            name = doc.get('name') or doc.get('query') or '未命名'
                            content = doc.get('content') or '(无内容)'
                            doc_type = doc.get('type', 'unknown').upper()
                            type_map = {'WORLDVIEW': '世界观', 'OUTLINE': '大纲', 'PROSE': '正文', 'DRAFT': '草案'}
                            display_type = type_map.get(doc_type, doc_type)
                            
                            doc_id = doc.get('id', '')
                            timestamp = doc.get('timestamp', '无')

                            with ui.column().classes('w-full gap-4 p-2'):
                                # 头部
                                with ui.row().classes('w-full items-center justify-between'):
                                    with ui.column().classes('gap-0'):
                                        ui.label(name).classes('text-xl font-bold text-white')
                                        with ui.row().classes('gap-2 items-center'):
                                            ui.badge(display_type, color='blue').classes('text-[10px]')
                                            ui.label(f'ID: {doc_id}').classes('text-[10px] text-slate-500 font-mono')
                                            ui.label(f'更新于: {timestamp}').classes('text-[10px] text-slate-500')

                                    with ui.row().classes('gap-2'):
                                        ui.button(icon='edit', on_click=lambda: open_edit_dialog(doc)).props('flat color="primary" size="sm"').tooltip('编辑')
                                        ui.button(icon='delete', on_click=lambda: confirm_delete(doc)).props('flat color="negative" size="sm"').tooltip('删除')

                                ui.separator()

                                # 内容展示
                                ui.label('详细内容').classes('text-xs font-bold text-slate-400 uppercase')
                                with ui.scroll_area().classes('w-full h-[400px] bg-black/30 rounded-lg border border-slate-800 p-4'):
                                    ui.markdown(content).classes('text-slate-300 text-sm')

                        detail_container()

        # ---- 编辑对话框 ----
        def open_edit_dialog(doc):
            name = doc.get('name') or doc.get('query') or '未命名'
            content = doc.get('content') or ''
            doc_id = doc.get('id', '')
            doc_type = doc.get('type', '')

            with ui.dialog() as dialog, ui.card().classes('w-[700px] bg-slate-900 border border-slate-700'):
                ui.label(f'编辑: {name}').classes('text-lg font-bold text-white mb-2')
                name_input = ui.input('条目名称', value=name).classes('w-full')
                content_input = ui.textarea('条目内容', value=content).classes('w-full h-64')

                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('取消', on_click=dialog.close).props('flat')
                    ui.button('保存', on_click=lambda: save_edit(dialog, doc_id, doc_type, name_input.value, content_input.value)).props('color="positive"')
            dialog.open()

        async def save_edit(dialog, doc_id, doc_type, new_name, new_content):
            try:
                if doc_type == 'draft':
                    # 直接通过 entity_drafts_db.json 处理草案
                    _save_draft_direct(doc_id, new_name, new_content)
                    ui.notify(f'"{new_name}" 保存成功！', type='positive')
                    dialog.close()
                    nonlocal all_docs
                    all_docs = get_all_lore_items()
                    doc = _find_doc_by_id(all_docs, doc_id)
                    if doc:
                        detail_container.refresh(doc)
                    return

                async with httpx.AsyncClient() as client:
                    res = await client.post(f'{FLASK_API}/api/archive/update', json={
                        'id': doc_id,
                        'type': doc_type,
                        'content': new_content,
                        'name': new_name,
                    }, timeout=10)
                    data = res.json()
                    if res.status_code == 200:
                        ui.notify(f'"{new_name}" 保存成功！', type='positive')
                        dialog.close()
                        all_docs = get_all_lore_items()
                        doc = _find_doc_by_id(all_docs, doc_id)
                        if doc:
                            detail_container.refresh(doc)
                    else:
                        ui.notify(f"保存失败: {data.get('error', '未知错误')}", type='negative')
            except Exception as ex:
                ui.notify(f'保存出错: {ex}', type='negative')

        # ---- 删除确认 ----
        def confirm_delete(doc):
            name = doc.get('name') or '未命名'
            doc_id = doc.get('id', '')
            doc_type = doc.get('type', '')

            with ui.dialog() as dialog, ui.card().classes('bg-slate-900 border border-red-800'):
                ui.label(f'确认删除 "{name}"？').classes('text-lg font-bold text-red-400')
                ui.label('此操作不可撤销。该条目将从数据库中永久移除。').classes('text-slate-400 text-sm my-4')
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('取消', on_click=dialog.close).props('flat')
                    ui.button('删除', on_click=lambda: do_delete(dialog, doc_id, doc_type, name)).props('color="negative"')
            dialog.open()

        async def do_delete(dialog, doc_id, doc_type, name):
            """从对应的 JSONL / JSON 数据库文件中删除条目。"""
            try:
                filename = {
                    'worldview': get_db_path("worldview_db.json"),
                    'outline': get_db_path("outlines_db.json"),
                    'prose': get_db_path("prose_db.json"),
                    'draft': get_db_path("entity_drafts_db.json"),
                }.get(doc_type)

                if not filename or not os.path.exists(filename):
                    ui.notify(f'无法删除：未知类型 "{doc_type}"', type='negative')
                    dialog.close()
                    return

                if doc_type in ['outline', 'worldview', 'prose']:
                    # JSONL — match by ID
                    remaining = []
                    with open(filename, 'r', encoding='utf-8') as f:
                        for line in f:
                            if not line.strip(): continue
                            entry = json.loads(line)
                            curr_id = entry.get('doc_id') or entry.get('id') or entry.get('outline_id') or entry.get('scene_id')
                            if str(curr_id) != str(doc_id):
                                remaining.append(line)
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.writelines(remaining)
                elif doc_type == 'draft':
                    # 草案 JSONL — 通过从 draft_ID 中提取的名称进行匹配
                    draft_name = str(doc_id).replace('draft_', '', 1)
                    remaining = []
                    with open(filename, 'r', encoding='utf-8') as f:
                        for line in f:
                            if not line.strip():
                                continue
                            entry = json.loads(line)
                            if entry.get('name') != draft_name:
                                remaining.append(entry)
                    with open(filename, 'w', encoding='utf-8') as f:
                        for entry in remaining:
                            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                else:
                    # JSONL (worldview, prose)
                    remaining = []
                    with open(filename, 'r', encoding='utf-8') as f:
                        for line in f:
                            if not line.strip():
                                continue
                            entry = json.loads(line)
                            entry_id = entry.get('doc_id') or entry.get('id')
                            if str(entry_id) != str(doc_id):
                                remaining.append(entry)
                    with open(filename, 'w', encoding='utf-8') as f:
                        for entry in remaining:
                            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

                ui.notify(f'已删除 "{name}"', type='warning')
                dialog.close()
                # 刷新
                nonlocal all_docs
                all_docs = get_all_lore_items()
                detail_container.refresh(None)

            except Exception as ex:
                ui.notify(f'删除失败: {ex}', type='negative')
