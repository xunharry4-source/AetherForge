from nicegui import ui

def create_header():
    with ui.header(elevated=True).classes('bg-slate-900 text-white items-center justify-between'):
        with ui.row().classes('items-center gap-4'):
            ui.label('PGA 万象星际管理后台').classes('text-lg font-bold tracking-wider text-cyan-400')
            with ui.row().classes('gap-2'):
                ui.label('系统状态:').classes('text-xs text-slate-400')
                ui.label('混合系统模式').classes('text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30')

def create_sidebar():
    with ui.left_drawer(elevated=True).classes('bg-slate-900 text-slate-300 w-64 border-r border-slate-800'):
        ui.label('导航菜单').classes('text-xs font-bold text-slate-500 mb-4 px-4')
        with ui.column().classes('w-full gap-1'):
            ui.link('实体草案审核', '/drafts').classes('w-full px-4 py-2 hover:bg-slate-800 rounded transition-colors text-slate-300 no-underline text-sm')
            ui.link('万象大脑 (Brain)', '/brain').classes('w-full px-4 py-2 hover:bg-slate-800 rounded transition-colors text-purple-400 no-underline text-sm font-bold border-l-2 border-purple-500 shadow-sm shadow-purple-500/10')
            ui.link('世界观知识库', '/lore').classes('w-full px-4 py-2 hover:bg-slate-800 rounded transition-colors text-slate-300 no-underline text-sm')
            ui.link('小说大纲管理', '/outlines').classes('w-full px-4 py-2 hover:bg-slate-800 rounded transition-colors text-slate-300 no-underline text-sm')
            ui.link('章节创作管理', '/chapters').classes('w-full px-4 py-2 hover:bg-slate-800 rounded transition-colors text-slate-300 no-underline text-sm')
            ui.link('设置与模板管理', '/settings').classes('w-full px-4 py-2 hover:bg-slate-800 rounded transition-colors text-slate-300 no-underline text-sm')
            ui.link('Dify 工作流编排', 'http://localhost:5001').props('target=_blank').classes('w-full px-4 py-2 hover:bg-slate-800 rounded transition-colors text-cyan-400 no-underline text-sm mt-4 border-t border-slate-800 pt-4')
            ui.link('SillyTavern 聊天前端', 'http://localhost:8000').props('target=_blank').classes('w-full px-4 py-2 hover:bg-slate-800 rounded transition-colors text-emerald-400 no-underline text-sm')

def page_layout():
    ui.dark_mode(True)
    create_header()
    create_sidebar()
    return ui.column().classes('w-full max-w-6xl mx-auto p-4 gap-6')
