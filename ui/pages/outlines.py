from nicegui import ui
import os
import json
import httpx
import sys

# Ensure backend imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_api import get_all_lore_items
from lore_utils import get_db_path
from ui.layout import page_layout

FLASK_API = 'http://localhost:5005'

def get_outlines():
    all_items = get_all_lore_items()
    return [item for item in all_items if item.get('type') == 'outline']

@ui.page('/outlines')
def outlines_page():
    outlines = get_outlines()
    
    with page_layout():
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column():
                ui.label('小说大纲管理').classes('text-2xl font-bold text-white')
                ui.label('创建、编辑并同步你的小说全局框架。').classes('text-slate-400 text-sm')
            ui.button('新建大纲', icon='add', on_click=lambda: open_create_dialog()).props('color="cyan" text-color="black"')

        if not outlines:
            with ui.card().classes('w-full p-12 items-center justify-center bg-slate-800/20 border-dashed border-2 border-slate-700'):
                ui.icon('assignment_late', size='4rem').classes('text-slate-600 mb-4')
                ui.label('尚未创建任何大纲').classes('text-slate-400 italic')
                ui.button('立即开始创作', on_click=lambda: open_create_dialog()).props('flat color="cyan"')
        else:
            with ui.grid(columns=3).classes('w-full gap-4'):
                for outline in outlines:
                    with ui.card().classes('bg-slate-800 border border-slate-700 hover:border-cyan-500/50 transition-all cursor-pointer p-0 overflow-hidden') as card:
                        with ui.column().classes('p-4 w-full'):
                            with ui.row().classes('w-full items-start justify-between'):
                                ui.label(outline.get('name', '未命名')).classes('text-lg font-bold text-cyan-100 line-clamp-1')
                                ui.badge('OUTLINE', color='cyan-9').classes('text-[10px]')
                            
                            ui.label(outline.get('timestamp', 'N/A')).classes('text-[10px] text-slate-500 mb-2')
                            
                            content_preview = outline.get('content', '')[:100] + '...'
                            ui.label(content_preview).classes('text-slate-400 text-sm line-clamp-3 mb-4 h-15')
                            
                            with ui.row().classes('w-full justify-end gap-2 pt-2 border-t border-slate-700'):
                                ui.button(icon='visibility', on_click=lambda o=outline: open_view_dialog(o)).props('flat round size="sm"').tooltip('查看')
                                ui.button(icon='edit', on_click=lambda o=outline: open_edit_dialog(o)).props('flat round size="sm"').tooltip('编辑')
                                ui.button(icon='delete', on_click=lambda o=outline: confirm_delete(o)).props('flat round color="negative" size="sm"').tooltip('删除')

    # --- Dialogs ---
    def open_create_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-[800px] bg-slate-900 border border-slate-700'):
            ui.label('创作新大纲').classes('text-xl font-bold text-white mb-4')
            query_input = ui.input('你的创作灵感', placeholder='例如：写一个关于星际赏金猎人在废土行星发现古文明遗迹的故事...').classes('w-full mb-4')
            ui.label('大纲 Agent 将根据此灵感及世界观设定生成结构化大纲。').classes('text-slate-500 text-xs mb-6')
            
            with ui.row().classes('w-full justify-end gap-3'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('启动 Agent 生成', on_click=lambda: start_generation(dialog, query_input.value)).props('color="cyan" text-color="black"')
        dialog.open()

    async def start_generation(dialog, query):
        if not query:
            ui.notify('请输入创作灵感', type='warning')
            return
        dialog.close()
        
        thread_id = f"outline_gen_{os.urandom(4).hex()}"
        
        # 进度显示弹窗
        with ui.dialog().props('persistent') as progress_dialog, ui.card().classes('w-96 bg-slate-900 border border-slate-700'):
            ui.label('大纲 Agent 正在构思...').classes('text-lg font-bold text-cyan-400')
            progress_status = ui.label('正在初始化工作流...').classes('text-slate-400 text-sm italic')
            progress_spinner = ui.spinner(size='lg', color='cyan').classes('self-center my-4')
            with ui.row().classes('w-full justify-end'):
                ui.button('取消任务', on_click=progress_dialog.close).props('flat color="negative"')
        progress_dialog.open()

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream('POST', f'{FLASK_API}/api/agent/query', json={
                    'agent_type': 'outline',
                    'query': query,
                    'thread_id': thread_id
                }, timeout=120) as response:
                    
                    async for line in response.aiter_lines():
                        if not line: continue
                        try:
                            data = json.loads(line)
                        except Exception as e:
                            print(f"Failed to parse line: {line}. Error: {e}")
                            continue
                        
                        if data.get('type') == 'error':
                            ui.notify(f"Agent 错误: {data.get('error')}", type='negative')
                            progress_dialog.close()
                            return

                        if data.get('type') == 'node_update':
                            msg = data.get('status_message', '进展中...')
                            progress_status.set_text(msg)
                            # 如果有诊断信息，显示在 console (如果需要)
                            if data.get('diagnostics'):
                                print(f"Node {data['node']} diag: {data['diagnostics']}")
                        
                        elif 'proposal' in data and not data.get('is_approved'):
                            # 触发人工审核
                            progress_dialog.close()
                            open_review_dialog(thread_id, data)
                            return
                        
                        elif data.get('type') == 'final_state' or data.get('status_message') == '大纲已确立并导出为分布式 SKILL 协议。':
                             ui.notify('大纲生成并保存成功！', type='positive')
                             progress_dialog.close()
                             ui.navigate.to('/outlines')
                             return

        except Exception as e:
            progress_dialog.close()
            ui.notify(f'生成出错: {e}', type='negative')

    def open_review_dialog(thread_id, agent_state):
        with ui.dialog().props('persistent') as review_dialog:
            with ui.card().classes('w-[1000px] max-h-[90vh] bg-slate-900 border-2 border-cyan-900/50'):
                ui.label('Agent 大纲提案审核').classes('text-2xl font-bold text-cyan-100 mb-2')
                ui.label('请根据以下提案决定批准或提出修改意见。').classes('text-slate-400 text-sm mb-4')
                
                with ui.scroll_area().classes('w-full h-[500px] bg-black/40 p-4 rounded border border-slate-800 mb-4'):
                    proposal_content = agent_state.get('proposal', '')
                    # 尝试美化 JSON 提案
                    try:
                        proposal_obj = json.loads(proposal_content)
                        ui.json_editor({'content': {'json': proposal_obj}}).props('readonly')
                    except:
                        ui.markdown(proposal_content).classes('text-slate-300')
                
                feedback_input = ui.input('修改意见', placeholder='例如：增加一些冲突，或者让主角更早登场...').classes('w-full mb-4')
                
                with ui.row().classes('w-full justify-end gap-3'):
                    ui.button('终止', on_click=review_dialog.close).props('flat color="negative"')
                    ui.button('提出修改意见', on_click=lambda: resume_agent(review_dialog, thread_id, feedback_input.value)).props('outline color="cyan"')
                    ui.button('批准并应用', on_click=lambda: resume_agent(review_dialog, thread_id, '批准')).props('color="cyan" text-color="black"')
        review_dialog.open()

    async def resume_agent(dialog, thread_id, resume_input):
        dialog.close()
        try:
            ui.notify('正在提交反馈，Agent 继续运行...', spinner=True)
            async with httpx.AsyncClient() as client:
                # 依然使用流式，因为可能还有后续步骤或再次进入审核
                async with client.stream('POST', f'{FLASK_API}/api/agent/query', json={
                    'agent_type': 'outline',
                    'thread_id': thread_id,
                    'resume_input': resume_input
                }, timeout=120) as response:
                    async for line in response.aiter_lines():
                        if not line: continue
                        data = json.loads(line)
                        if 'proposal' in data and not data.get('is_approved') and resume_input != '批准':
                            open_review_dialog(thread_id, data)
                            return
                        elif data.get('type') == 'final_state' or '存档' in str(data.get('status_message')):
                             ui.notify('操作成功！', type='positive')
                             ui.navigate.to('/outlines')
                             return
        except Exception as e:
            ui.notify(f'恢复运行失败: {e}', type='negative')

    def open_view_dialog(outline):
        with ui.dialog() as dialog, ui.card().classes('w-[900px] max-h-[80vh] bg-slate-950 border border-slate-800'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label(outline.get('name')).classes('text-xl font-bold text-cyan-400')
                ui.button(icon='close', on_click=dialog.close).props('flat round')
            ui.separator().classes('my-4')
            with ui.scroll_area().classes('w-full h-[500px]'):
                ui.markdown(outline.get('content', '')).classes('text-slate-300')
        dialog.open()

    def open_edit_dialog(outline):
        with ui.dialog() as dialog, ui.card().classes('w-[900px] bg-slate-900 border border-slate-700'):
            ui.label(f"编辑大纲: {outline.get('name')}").classes('text-xl font-bold text-white mb-4')
            name_input = ui.input('名称', value=outline.get('name')).classes('w-full mb-2')
            content_input = ui.textarea('详细内容', value=outline.get('content')).classes('w-full h-80')
            
            with ui.row().classes('w-full justify-end gap-3 mt-4'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('保存修改', on_click=lambda: save_outline(dialog, outline.get('id'), name_input.value, content_input.value)).props('color="positive"')
        dialog.open()

    async def save_outline(dialog, doc_id, name, content):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(f'{FLASK_API}/api/archive/update', json={
                    'id': doc_id,
                    'type': 'outline',
                    'name': name,
                    'content': content
                }, timeout=10)
                if res.status_code == 200:
                    ui.notify('大纲保存成功', type='positive')
                    dialog.close()
                    ui.navigate.to('/outlines') # Refresh
                else:
                    ui.notify(f"保存失败: {res.text}", type='negative')
        except Exception as e:
            ui.notify(f'保存出错: {e}', type='negative')

    def confirm_delete(outline):
        with ui.dialog() as dialog, ui.card().classes('bg-slate-900 border border-red-900'):
            ui.label(f"确认删除大纲 '{outline.get('name')}'？").classes('text-lg font-bold text-red-500')
            ui.label('删除大纲后，相关的章节创作可能失去索引。').classes('text-slate-400 text-sm my-4')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('确定删除', on_click=lambda: do_delete(dialog, outline.get('id'))).props('color="negative"')
        dialog.open()

    async def do_delete(dialog, doc_id):
        try:
            # Reusing the existing deletion logic in lore_db if possible, or direct implement
            # For simplicity, direct delete here
            db_path = get_db_path('outlines_db.json')
            remaining = []
            with open(db_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip(): continue
                    item = json.loads(line)
                    curr_id = item.get('id') or item.get('outline_id')
                    if str(curr_id) != str(doc_id):
                        remaining.append(line)
            with open(db_path, 'w', encoding='utf-8') as f:
                f.writelines(remaining)
            
            ui.notify('大纲已移除', type='warning')
            dialog.close()
            ui.navigate.to('/outlines')
        except Exception as e:
            ui.notify(f'删除失败: {e}', type='negative')
