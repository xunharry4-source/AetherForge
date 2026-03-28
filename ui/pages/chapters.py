from nicegui import ui
import os
import json
import httpx
import sys
import datetime

# Ensure backend imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_api import get_all_lore_items
from lore_utils import get_db_path
from ui.layout import page_layout

FLASK_API = 'http://localhost:5005'

async def get_chapters(oid=None, wid=None):
    async with httpx.AsyncClient() as client:
        params = {}
        if oid: params['outline_id'] = oid
        if wid: params['worldview_id'] = wid
        res = await client.get(f'{FLASK_API}/api/lore/list', params=params, timeout=10)
        items = res.json() if res.status_code == 200 else []
        return [item for item in items if item.get('type') == 'prose']

@ui.page('/chapters')
async def chapters_page():
    # Session state for current project
    state = {'outline_id': 'default'}
    
    # Fetch projects for the dropdown
    async def get_project_options():
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f'{FLASK_API}/api/outlines/list')
                if res.status_code == 200:
                    projects = res.json()
                    # Store full project object to access worldview_id
                    state['projects'] = {p['outline_id']: p for p in projects}
                    return {p['outline_id']: f"{p['title']} ({p.get('worldview_id', 'default_wv')})" for p in projects}
        except Exception:
            return {}
        return {}

    project_options = await get_project_options()
    
    with page_layout():
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column():
                ui.label('章节正文管理').classes('text-2xl font-bold text-white')
                ui.label('基于大纲细化场次并进行人工润色迭代。').classes('text-slate-400 text-sm')
            
            with ui.row().classes('items-center gap-4'):
                # Project Selector
                ui.label('当前项目:').classes('text-slate-500 text-xs uppercase font-bold')
                project_select = ui.select(project_options, value=state.get('outline_id'), on_change=lambda e: refresh_list(e.value)).classes('w-80')
                ui.button('辅助写作', icon='edit_note', on_click=lambda: open_write_dialog()).props('color="emerald" text-color="black"')

        container = ui.column().classes('w-full gap-4')

        async def refresh_list(oid):
            state['outline_id'] = oid
            project = state.get('projects', {}).get(oid, {})
            wid = project.get('worldview_id', 'default_wv')
            state['worldview_id'] = wid
            
            container.clear()
            chapters = await get_chapters(oid, wid)
            
            if not chapters:
                with container:
                    with ui.card().classes('w-full p-12 items-center justify-center bg-slate-800/20 border-dashed border-2 border-slate-700'):
                        ui.icon('menu_book', size='4rem').classes('text-slate-600 mb-4')
                        ui.label('该项目中尚未生成任何章节正文').classes('text-slate-400 italic')
                        ui.button('开启创作之旅', on_click=lambda: open_write_dialog()).props('flat color="emerald"')
            else:
                with container:
                    for chapter in reversed(chapters): # Newest first
                        with ui.card().classes('w-full bg-slate-800 border border-slate-700 hover:border-emerald-500/30 transition-all p-0'):
                            with ui.row().classes('w-full p-4 items-center gap-4'):
                                # Left: Icon/Type
                                with ui.column().classes('items-center justify-center w-16 h-16 bg-slate-900 rounded-lg'):
                                    ui.icon('article', size='2rem').classes('text-emerald-500')
                                    ui.label('PROSE').classes('text-[8px] font-bold text-slate-500')
                                
                                # Center: Title & Info
                                with ui.column().classes('flex-grow'):
                                    ui.label(chapter.get('name', '未命名场次')).classes('text-lg font-bold text-emerald-100')
                                    with ui.row().classes('gap-3'):
                                        ui.label(chapter.get('timestamp', 'N/A')).classes('text-[10px] text-slate-500')
                                        ui.label(f"ID: {chapter.get('id', 'N/A')}").classes('text-[10px] text-slate-600 font-mono')
                                
                                # Right: Actions
                                with ui.row().classes('gap-2'):
                                    ui.button(icon='visibility', on_click=lambda c=chapter: open_view_dialog(c)).props('flat round size="sm"').tooltip('阅读')
                                    ui.button(icon='edit', on_click=lambda c=chapter: open_edit_dialog(c)).props('flat round size="sm"').tooltip('润色')
                                    ui.button(icon='delete', on_click=lambda c=chapter: confirm_delete(c)).props('flat round color="negative" size="sm"').tooltip('废止')
        
        # Initial render
        if project_options:
            initial_oid = next(iter(project_options))
            await refresh_list(initial_oid)
        else:
            refresh_list(None)

    # --- Dialogs ---
    def open_write_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-[800px] bg-slate-900 border border-slate-700'):
            ui.label('辅助写作任务投放').classes('text-xl font-bold text-white mb-4')
            
            current_wid = state.get('worldview_id')
            current_oid = state.get('outline_id')
            
            if not current_oid:
                ui.label('⚠️ 请先在页面顶部选择一个项目。').classes('text-red-400 mb-4')
            else:
                ui.label(f"正在为项目 '{state['projects'][current_oid]['title']}' (世界观: {current_wid}) 创作正文").classes('text-slate-400 text-sm mb-4')
                chapter_input = ui.input('目标章节/幕', placeholder='例如：第一章、第五场：遭遇战...').classes('w-full mb-4')
                
                with ui.row().classes('w-full justify-end gap-3'):
                    ui.button('取消', on_click=dialog.close).props('flat')
                    ui.button('启动写作 Agent', on_click=lambda: start_writing(dialog, current_oid, current_wid, chapter_input.value)).props('color="emerald" text-color="black"')
        dialog.open()

    async def start_writing(dialog, outline_id, worldview_id, chapter_info):
        if not outline_id or not chapter_info:
            ui.notify('创作任务参数不全', type='warning')
            return
        dialog.close()
        try:
            ui.notify('正在加载语境并启动写作 Agent...', color='info', spinner=True)
            async with httpx.AsyncClient() as client:
                res = await client.post(f'{FLASK_API}/api/agent/query', json={
                    'agent_type': 'writing',
                    'query': outline_id,
                    'worldview_id': worldview_id,
                    'current_act': chapter_info
                }, timeout=60)
                if res.status_code == 200:
                    ui.notify('创作任务已启动', type='positive')
                else:
                    ui.notify(f'启动失败: {res.text}', type='negative')
        except Exception as e:
            ui.notify(f'错误: {e}', type='negative')

    def open_view_dialog(chapter):
        with ui.dialog() as dialog, ui.card().classes('w-[900px] max-h-[80vh] bg-slate-950 border border-slate-800'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label(chapter.get('name')).classes('text-xl font-bold text-emerald-400')
                ui.button(icon='close', on_click=dialog.close).props('flat round')
            ui.separator().classes('my-4')
            with ui.scroll_area().classes('w-full h-[500px]'):
                ui.markdown(chapter.get('content', '')).classes('text-slate-300 leading-relaxed')
        dialog.open()

    def open_edit_dialog(chapter):
        with ui.dialog() as dialog, ui.card().classes('w-[900px] bg-slate-900 border border-slate-700'):
            ui.label(f"润色正文: {chapter.get('name')}").classes('text-xl font-bold text-white mb-4')
            name_input = ui.input('场次标题', value=chapter.get('name')).classes('w-full mb-2')
            content_input = ui.textarea('正文内容', value=chapter.get('content')).classes('w-full h-80')
            
            with ui.row().classes('w-full justify-end gap-3 mt-4'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('确认润色', on_click=lambda: save_chapter(dialog, chapter.get('id'), name_input.value, content_input.value)).props('color="positive"')
        dialog.open()

    async def save_chapter(dialog, doc_id, name, content):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(f'{FLASK_API}/api/archive/update', json={
                    'id': doc_id,
                    'type': 'prose',
                    'name': name,
                    'content': content,
                    'outline_id': state['outline_id']
                }, timeout=10)
                if res.status_code == 200:
                    ui.notify('润色内容已保存', type='positive')
                    dialog.close()
                    await refresh_list(state['outline_id'])
                else:
                    ui.notify(f"保存失败: {res.text}", type='negative')
        except Exception as e:
            ui.notify(f'保存出错: {e}', type='negative')

    def confirm_delete(chapter):
        with ui.dialog() as dialog, ui.card().classes('bg-slate-900 border border-red-900'):
            ui.label(f"确认废止该段正文？").classes('text-lg font-bold text-red-500')
            ui.label('废止后该内容将从创作库中移除。').classes('text-slate-400 text-sm my-4')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('确认废止', on_click=lambda: do_delete(dialog, chapter.get('id'))).props('color="negative"')
        dialog.open()

    async def do_delete(dialog, doc_id):
        try:
            db_path = get_db_path('prose_db.json', outline_id=state['outline_id'], worldview_id=state.get('worldview_id'))
            remaining = []
            if os.path.exists(db_path):
                with open(db_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if not line.strip(): continue
                        entry = json.loads(line)
                        entry_id = entry.get('prose_id') or entry.get('id')
                        if str(entry_id) != str(doc_id):
                            remaining.append(entry)
                with open(db_path, 'w', encoding='utf-8') as f:
                    for entry in remaining:
                        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                
                ui.notify('内容已移除', type='warning')
                dialog.close()
                await refresh_list(state['outline_id'])
            else:
                ui.notify('数据库文件不存在', type='negative')
        except Exception as e:
            ui.notify(f'移除失败: {e}', type='negative')
