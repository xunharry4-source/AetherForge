from nicegui import ui, app
import sys
import os

# Ensure the parent directory is in the path so we can import backend logic directly if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.layout import page_layout

@ui.page('/')
def index_page():
    with page_layout():
        ui.label('欢迎使用 PGA 万象星际管理后台').classes('text-2xl font-bold text-slate-200 mt-8')
        ui.label('请从侧边栏选择相应选项来管理实体草案、浏览知识库或配置系统设置。').classes('text-slate-400')
        
        with ui.card().classes('w-full bg-slate-900 border border-slate-700 mt-8 p-6 gap-4'):
            ui.label('混合架构系统状态').classes('text-lg font-bold text-white')
            
            with ui.row().classes('w-full gap-4'):
                # Backend status
                with ui.column().classes('flex-1 bg-black/30 p-4 rounded border border-slate-800'):
                    ui.label('后端引擎 (API)').classes('text-[10px] text-slate-500 font-bold uppercase tracking-wider')
                    backend_label = ui.label('正在连接...').classes('text-emerald-400 font-mono text-sm mt-1')
                    backend_sub = ui.label('FLASK_GATEWAY').classes('text-[8px] text-slate-600 font-mono italic')
                
                # Logic Orch status (Dify/LangGraph)
                with ui.column().classes('flex-1 bg-black/30 p-4 rounded border border-slate-800'):
                    ui.label('逻辑编排 (Dify)').classes('text-[10px] text-slate-500 font-bold uppercase tracking-wider')
                    dify_label = ui.label('检测中...').classes('text-cyan-400 font-mono text-sm mt-1')
                    dify_sub = ui.label('PORT 5001').classes('text-[8px] text-slate-600 font-mono italic')
                
                # Interface status
                with ui.column().classes('flex-1 bg-black/30 p-4 rounded border border-slate-800'):
                    ui.label('用户交互 (SillyTavern)').classes('text-[10px] text-slate-500 font-bold uppercase tracking-wider')
                    st_label = ui.label('待命').classes('text-purple-400 font-mono text-sm mt-1')
                    st_sub = ui.label('PORT 8000').classes('text-[8px] text-slate-600 font-mono italic')

            # Storage and LLM usage summary
            with ui.row().classes('w-full gap-4 mt-2'):
                with ui.row().classes('items-center gap-2 bg-slate-950/50 px-3 py-1 rounded-full border border-slate-800'):
                    ui.icon('database', color='slate-500', size='xs')
                    storage_label = ui.label('存储器: --').classes('text-[10px] text-slate-400 font-mono')
                with ui.row().classes('items-center gap-2 bg-slate-950/50 px-3 py-1 rounded-full border border-slate-800'):
                    ui.icon('token', color='slate-500', size='xs')
                    token_label = ui.label('累计消纳: -- Tokens').classes('text-[10px] text-slate-400 font-mono')

        async def update_health():
            import httpx
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get('http://localhost:5005/api/system/health', timeout=1.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        backend_label.text = f"运行中 ({data.get('status', 'OK')})"
                        
                        # Storage info
                        storage = data.get('storage', {})
                        if storage.get('percent_used') is not None:
                            storage_label.text = f"存储可用: {storage.get('free_gb', 0)}GB ({100-storage.get('percent_used', 0)}% FREE)"
                        
                        # Token info
                        llm = data.get('llm', {})
                        token_label.text = f"总 Token 消耗: {llm.get('total_tokens', 0):,}"
                        
                        # Fake logic for other services based on backend status for now
                        dify_label.text = "LangGraph 活跃" if data.get('status') == 'healthy' else "异常"
                        st_label.text = "已就绪"
                    else:
                        backend_label.text = "服务异常"
            except Exception:
                backend_label.text = "无法连接 API"
                backend_label.classes('text-red-400', remove='text-emerald-400')

        ui.timer(2.0, update_health)

def init_app():
    # Load dynamic pages by importing them
    import ui.pages.entity_drafts
    import ui.pages.lore_db
    import ui.pages.outlines
    import ui.pages.chapters
    import ui.pages.settings

if __name__ in {"__main__", "__mp_main__"}:
    init_app()
    ui.run(port=8090, title='PGA Hybrid Admin', favicon='🌌')
