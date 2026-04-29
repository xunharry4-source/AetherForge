from fastapi import Request
from nicegui import ui
import os
import json
import httpx
import sys

# Ensure backend imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_api import get_all_lore_items
from src.common.lore_utils import get_db_path
from ui.layout import page_layout

FLASK_API = 'http://127.0.0.1:5006'

async def get_worlds():
    async with httpx.AsyncClient() as client:
        res = await client.get(f'{FLASK_API}/api/worlds/list', timeout=10)
        return res.json() if res.status_code == 200 else []

async def get_outlines(world_id):
    if not world_id:
        return []
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f'{FLASK_API}/api/outlines/list',
            params={'world_id': world_id, 'page': 1, 'page_size': 50},
            timeout=10,
        )
        return res.json() if res.status_code == 200 else []

async def get_worldviews(world_id):
    if not world_id:
        return []
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f'{FLASK_API}/api/worldviews/list',
            params={'world_id': world_id, 'page': 1, 'page_size': 50},
            timeout=10,
        )
        return res.json() if res.status_code == 200 else []

@ui.page('/outlines')
async def outlines_page(request: Request):
    worlds = await get_worlds()
    requested_world = request.query_params.get('world_id')
    world_options = {world['world_id']: f"{world.get('name', world['world_id'])} ({world['world_id']})" for world in worlds}
    current_world = requested_world if requested_world in world_options else next(iter(world_options), None)
    outlines = await get_outlines(current_world)
    worldviews = await get_worldviews(current_world)
    
    with page_layout():
        # --- Worldview Management Section ---
        with ui.row().classes('w-full items-center justify-between mb-4 mt-2'):
            with ui.column():
                ui.label('世界观管理').classes('text-2xl font-bold text-white')
                ui.label('管理独立的世界观容器，每个容器拥有独立的设定库。').classes('text-slate-400 text-sm')
            with ui.row().classes('items-center gap-3'):
                ui.select(
                    world_options,
                    value=current_world,
                    label='当前世界',
                    on_change=lambda e: ui.navigate.to(f'/outlines?world_id={e.value}'),
                ).props('dark dense outlined').classes('min-w-[260px] text-cyan-300')
                ui.button('创建世界观', icon='public', on_click=lambda: open_create_wv_dialog(current_world)).props('outline color="cyan"')

        if not current_world:
            with ui.card().classes('w-full p-8 bg-yellow-950/30 border border-yellow-700'):
                ui.label('必须选择世界后才能查看大纲。').classes('text-yellow-300 font-bold')
            return

        with ui.row().classes('w-full gap-4 mb-8 overflow-x-auto pb-2'):
            for wv in worldviews:
                with ui.card().classes('bg-slate-800/40 border border-slate-700 min-w-[250px] p-4'):
                    ui.label(wv.get('name')).classes('text-lg font-bold text-cyan-300')
                    ui.label(wv.get('summary', '无简介')[:50] + '...').classes('text-slate-400 text-xs mb-2 h-8 overflow-hidden')
                    with ui.row().classes('w-full justify-between items-center'):
                        ui.label(f"ID: {wv.get('worldview_id')}").classes('text-[10px] text-slate-500')
                        ui.badge('ACTIVE', color='green-9').classes('text-[8px]')

        ui.separator().classes('my-6 border-slate-700')

        # --- Novel Outlines Section ---
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column():
                ui.label('小说大纲 / 项目').classes('text-2xl font-bold text-white')
                ui.label('在选定的世界观下创作具体的小说项目。').classes('text-slate-400 text-sm')
            ui.button('新建小说项目', icon='add', on_click=lambda: open_create_dialog(current_world, worldviews)).props('color="cyan" text-color="black"')

        if not outlines:
            with ui.card().classes('w-full p-12 items-center justify-center bg-slate-800/20 border-dashed border-2 border-slate-700'):
                ui.icon('assignment_late', size='4rem').classes('text-slate-600 mb-4')
                ui.label('尚未创建任何小说项目').classes('text-slate-400 italic')
                ui.button('立即开始创作', on_click=lambda: open_create_dialog(current_world, worldviews)).props('flat color="cyan"')
        else:
            with ui.grid(columns=3).classes('w-full gap-4'):
                for outline in outlines:
                    with ui.card().classes('bg-slate-800 border border-slate-700 hover:border-cyan-500/50 transition-all cursor-pointer p-0 overflow-hidden') as card:
                        with ui.column().classes('p-4 w-full'):
                            with ui.row().classes('w-full items-start justify-between'):
                                ui.label(outline.get('title') or outline.get('name', '未命名')).classes('text-lg font-bold text-cyan-100 line-clamp-1')
                                ui.badge(outline.get('worldview_id', 'default_wv'), color='indigo-9').classes('text-[10px]')
                            
                            ui.label(outline.get('timestamp', 'N/A')).classes('text-[10px] text-slate-500 mb-2')
                            
                            content_preview = (outline.get('summary') or outline.get('content', ''))[:100] + '...'
                            ui.label(content_preview).classes('text-slate-400 text-sm line-clamp-3 mb-4 h-15')
                            
                            with ui.row().classes('w-full justify-end gap-2 pt-2 border-t border-slate-700'):
                                ui.button(icon='visibility', on_click=lambda o=outline: open_view_dialog(o)).props('flat round size="sm"').tooltip('查看')
                                ui.button(icon='edit', on_click=lambda o=outline: open_edit_dialog(o)).props('flat round size="sm"').tooltip('编辑')
                                ui.button(icon='delete', on_click=lambda o=outline: confirm_delete(o)).props('flat round color="negative" size="sm"').tooltip('删除')

    # --- Dialogs ---
    def open_create_dialog(world_id, worldviews):
        with ui.dialog() as dialog, ui.card().classes('w-[800px] bg-slate-900 border border-slate-700'):
            ui.label('创作新小说项目').classes('text-xl font-bold text-white mb-4')
            ui.input('所属世界', value=world_options.get(world_id, world_id or '')).props('readonly').classes('w-full mb-4')
            
            wv_options = {wv['worldview_id']: wv['name'] for wv in worldviews}
            wv_select = ui.select(wv_options, value=next(iter(wv_options)) if wv_options else None, label='所属世界观').classes('w-full mb-4')
            
            name_input = ui.input('小说名称', placeholder='输入小说名称...').classes('w-full mb-4')
            query_input = ui.input('核心创作灵感', placeholder='例如：写一个关于星际赏金猎人发现古文明遗迹的故事...').classes('w-full mb-4')
            
            ui.label('大纲 Agent 将根据此灵感及选定的世界观设定生成结构化大纲。').classes('text-slate-500 text-xs mb-6')
            
            with ui.row().classes('w-full justify-end gap-3'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('启动 Agent 生成', on_click=lambda: start_generation(dialog, world_id, query_input.value, name_input.value, wv_select.value)).props('color="cyan" text-color="black"')

    def open_create_wv_dialog(world_id):
        with ui.dialog() as dialog, ui.card().classes('w-[600px] bg-slate-900 border border-slate-700'):
            ui.label('创建新世界观').classes('text-xl font-bold text-white mb-4')
            ui.input('所属世界', value=world_options.get(world_id, world_id or '')).props('readonly').classes('w-full mb-4')
            name_input = ui.input('世界观名称', placeholder='例如：万象星际、赛博长城...').classes('w-full mb-4')
            summary_input = ui.textarea('背景简介', placeholder='简要描述该世界观的核心逻辑与背景...').classes('w-full mb-4')
            
            with ui.row().classes('w-full justify-end gap-3'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('创建', on_click=lambda: save_worldview(dialog, world_id, name_input.value, summary_input.value)).props('color="cyan" text-color="black"')
        dialog.open()

    async def save_worldview(dialog, world_id, name, summary):
        if not world_id or not name:
            ui.notify('请选择世界并输入世界观名称', type='warning')
            return
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(f'{FLASK_API}/api/worldviews/create', json={'world_id': world_id, 'name': name, 'summary': summary})
                if res.status_code == 200:
                    ui.notify('世界观创建成功', type='positive')
                    dialog.close()
                    ui.navigate.to(f'/outlines?world_id={world_id}')
                else:
                    ui.notify(f'创建失败: {res.text}', type='negative')
        except Exception as e:
            ui.notify(f'创建异常: {e}', type='negative')

    async def start_generation(dialog, world_id, query, name, worldview_id):
        if not world_id or not query or not name:
            ui.notify('请选择世界，并输入小说名称与创作灵感', type='warning')
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
                    'name': name,
                    'world_id': world_id,
                    'worldview_id': worldview_id,
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
                             ui.navigate.to(f'/outlines?world_id={world_id}')
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
                             ui.navigate.to(f'/outlines?world_id={current_world}')
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
                ui.button('保存修改', on_click=lambda: save_outline(dialog, outline.get('id'), outline.get('world_id'), outline.get('worldview_id'), name_input.value, content_input.value)).props('color="positive"')
        dialog.open()

    async def save_outline(dialog, doc_id, world_id, worldview_id, name, content):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(f'{FLASK_API}/api/archive/update', json={
                    'id': doc_id,
                    'type': 'outline',
                    'name': name,
                    'content': content,
                    'world_id': world_id,
                    'worldview_id': worldview_id,
                }, timeout=10)
                if res.status_code == 200:
                    ui.notify('大纲保存成功', type='positive')
                    dialog.close()
                    ui.navigate.to(f'/outlines?world_id={world_id}')
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
                ui.button('确定删除', on_click=lambda: do_delete(dialog, outline.get('id'), outline.get('world_id'), outline.get('worldview_id'))).props('color="negative"')
        dialog.open()

    async def do_delete(dialog, doc_id, world_id, worldview_id):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.request('DELETE', f'{FLASK_API}/api/archive/delete', json={
                    'id': doc_id, 
                    'type': 'outline',
                    'world_id': world_id,
                    'worldview_id': worldview_id,
                }, timeout=10)
                
                if res.status_code == 200:
                    ui.notify('大纲及相关索引已物理移除', type='warning')
                    dialog.close()
                    ui.navigate.to(f'/outlines?world_id={world_id}')
                else:
                    ui.notify(f'删除失败: {res.text}', type='negative')
        except Exception as e:
            ui.notify(f'删除异常: {e}', type='negative')
