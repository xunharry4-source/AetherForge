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

def get_chapters():
    all_items = get_all_lore_items()
    # Prose items are stored with type 'prose'
    return [item for item in all_items if item.get('type') == 'prose']

@ui.page('/chapters')
def chapters_page():
    chapters = get_chapters()
    
    with page_layout():
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column():
                ui.label('章节正文创作').classes('text-2xl font-bold text-white')
                ui.label('基于大纲细化场次并生成高质量小说正文。').classes('text-slate-400 text-sm')
            ui.button('辅助写作', icon='edit_note', on_click=lambda: open_write_dialog()).props('color="emerald" text-color="black"')

        if not chapters:
            with ui.card().classes('w-full p-12 items-center justify-center bg-slate-800/20 border-dashed border-2 border-slate-700'):
                ui.icon('menu_book', size='4rem').classes('text-slate-600 mb-4')
                ui.label('尚未生成任何章节正文').classes('text-slate-400 italic')
                ui.button('开启创作之旅', on_click=lambda: open_write_dialog()).props('flat color="emerald"')
        else:
            with ui.column().classes('w-full gap-4'):
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

    # --- Dialogs ---
    def open_write_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-[800px] bg-slate-900 border border-slate-700'):
            ui.label('辅助写作任务投放').classes('text-xl font-bold text-white mb-4')
            
            # Fetch outlines for selection
            outlines = [o for o in get_all_lore_items() if o.get('type') == 'outline']
            outline_options = {o['id']: f"{o['name']} ({o['id']})" for o in outlines}
            
            if not outline_options:
                ui.label('⚠️ 需要先创建一个大纲才能开始写作。').classes('text-red-400 mb-4')
            else:
                outline_select = ui.select(outline_options, label='选择参考大纲').classes('w-full mb-4')
                chapter_input = ui.input('目标章节/幕', placeholder='例如：第一章、第五场：遭遇战...').classes('w-full mb-4')
                
                with ui.row().classes('w-full justify-end gap-3'):
                    ui.button('取消', on_click=dialog.close).props('flat')
                    ui.button('启动写作 Agent', on_click=lambda: start_writing(dialog, outline_select.value, chapter_input.value)).props('color="emerald" text-color="black"')
        dialog.open()

    async def start_writing(dialog, outline_id, chapter_info):
        if not outline_id or not chapter_info:
            ui.notify('请选择大纲并输入章节信息', type='warning')
            return
        dialog.close()
        try:
            ui.notify('正在加载语境并启动写作 Agent...', color='info', spinner=True)
            async with httpx.AsyncClient() as client:
                res = await client.post(f'{FLASK_API}/api/agent/query', json={
                    'agent_type': 'writing',
                    'query': outline_id,
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
                    'content': content
                }, timeout=10)
                if res.status_code == 200:
                    ui.notify('润色内容已保存', type='positive')
                    dialog.close()
                    ui.navigate.to('/chapters')
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
            db_path = get_db_path('prose_db.json')
            remaining = []
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
            ui.navigate.to('/chapters')
        except Exception as e:
            ui.notify(f'移除失败: {e}', type='negative')
