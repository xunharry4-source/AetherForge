from nicegui import ui
import json
import os
import sys

# Ensure backend imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common.lore_utils import get_draft_entities, approve_draft_entity, batch_approve_draft_entities, batch_reject_draft_entities, get_db_path
from ui.layout import page_layout

def _reject_draft_entity(name: str):
    """通过 lore_utils 物理拒绝草案 (MongoDB)"""
    try:
        from src.common.lore_utils import batch_reject_draft_entities
        result = batch_reject_draft_entities([name])
        return result['success'] > 0
    except Exception as e:
        print(f"Reject error: {e}")
        return False

@ui.page('/drafts')
def entity_drafts_page():
    with page_layout():
        ui.label('实体草案审核').classes('text-2xl font-bold text-white mb-2')
        ui.label('在 AI 生成的条目进入正式知识库之前，对其进行审核、批准或拒绝。').classes('text-slate-400 text-sm mb-6')
        
        # 状态容器
        state = {'drafts': [], 'selected': []}
        
        def refresh_drafts():
            state['drafts'] = get_draft_entities()
            state['selected'] = []
            render_drafts_container.refresh()
            update_batch_buttons()

        def approve_single(name):
            if approve_draft_entity(name):
                ui.notify(f'已批准 "{name}"', type='positive')
                refresh_drafts()
            else:
                ui.notify(f'批准 "{name}" 失败', type='negative')

        def reject_single(name):
            if _reject_draft_entity(name):
                ui.notify(f'已拒绝 "{name}"', type='warning')
                refresh_drafts()
            else:
                ui.notify(f'拒绝 "{name}" 失败', type='negative')

        def toggle_selection(name):
            if name in state['selected']:
                state['selected'].remove(name)
            else:
                state['selected'].append(name)
            update_batch_buttons()

        def batch_approve():
            if not state['selected']: return
            result = batch_approve_draft_entities(state['selected'])
            ui.notify(f"批量批准完成。成功: {result['success']}, 失败: {result['failed']}", type='positive')
            refresh_drafts()

        def batch_reject():
            if not state['selected']: return
            result = batch_reject_draft_entities(state['selected'])
            ui.notify(f"批量拒绝完成。成功: {result['success']}, 失败: {result['failed']}", type='warning')
            refresh_drafts()

        # 批量操作栏
        with ui.row().classes('w-full items-center justify-between bg-slate-800 p-4 rounded-lg border border-slate-700'):
            ui.label('批量操作:').classes('text-slate-300 font-bold')
            with ui.row().classes('gap-2'):
                btn_approve = ui.button('批准所选', on_click=batch_approve).props('color="positive" icon="check" flat').classes('opacity-50')
                btn_reject = ui.button('拒绝所选', on_click=batch_reject).props('color="negative" icon="delete" flat').classes('opacity-50')

        def update_batch_buttons():
            has_selection = len(state['selected']) > 0
            if has_selection:
                btn_approve.classes(remove='opacity-50')
                btn_reject.classes(remove='opacity-50')
            else:
                btn_approve.classes(add='opacity-50')
                btn_reject.classes(add='opacity-50')

        @ui.refreshable
        def render_drafts_container():
            drafts = state['drafts']
            if not drafts:
                with ui.column().classes('w-full items-center py-12'):
                    ui.icon('inbox', size='4rem').classes('text-slate-600 mb-4')
                    ui.label('暂无待审核的条目草案。').classes('text-slate-400')
                return
            
            with ui.grid(columns=2).classes('w-full gap-4'):
                for draft in drafts:
                    name = draft.get('name', '未命名')
                    draft_type = draft.get('type', 'general').upper()
                    # 翻译类型
                    type_map = {'RACE': '种族', 'FACTION': '势力', 'GEOGRAPHY': '地理', 'MECHANISM': '机制', 'HISTORY': '历史', 'GENERAL': '通用'}
                    display_type = type_map.get(draft_type, draft_type)

                    with ui.card().classes('bg-black/40 border border-slate-700 hover:border-slate-500 w-full'):
                        with ui.row().classes('w-full items-start justify-between mb-2'):
                            with ui.row().classes('items-center gap-2'):
                                ui.checkbox('', on_change=lambda e, n=name: toggle_selection(n)).classes('text-emerald-500')
                                with ui.column().classes('gap-0'):
                                    ui.label(name).classes('text-lg font-bold text-white')
                                    ui.label(display_type).classes('text-[10px] text-orange-400 font-bold tracking-wider bg-orange-500/10 px-2 py-0.5 rounded')
                            ui.label(draft.get('created_at', '')[:10]).classes('text-[10px] text-slate-500 font-mono')
                        
                        ui.label('创作上下文').classes('text-[9px] text-slate-500 uppercase mt-2')
                        ui.label(draft.get('source_context', '')).classes('text-xs text-slate-400 line-clamp-3')
                        
                        with ui.expansion('查看原始 JSON 数据').classes('w-full mt-2 bg-slate-900 border border-slate-800 rounded'):
                            ui.markdown(f"```json\n{json.dumps(draft.get('entity_card', {}), indent=2, ensure_ascii=False)}\n```").classes('text-[10px]')
                        
                        with ui.row().classes('w-full gap-2 mt-4'):
                            ui.button('批准', on_click=lambda _, n=name: approve_single(n)).props('color="positive" outline').classes('flex-1')
                            ui.button('拒绝', on_click=lambda _, n=name: reject_single(n)).props('color="negative" outline').classes('flex-1')

        # Initial Load
        refresh_drafts()
