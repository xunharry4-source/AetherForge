from nicegui import ui
import httpx
import json
import asyncio
from ui.layout import page_layout

@ui.page('/brain')
async def brain_page():
    with page_layout():
        ui.label('🌌 万象大脑 (Cosmos Brain)').classes('text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-cyan-400 mt-4')
        ui.label('项目级认知审计与自主创意扩张引擎。大脑会分析全量背景素材，发现逻辑断层并派发任务。').classes('text-slate-400 text-sm')

        # --- 控制区 ---
        with ui.row().classes('w-full gap-4 items-center bg-slate-900/50 p-4 rounded-xl border border-slate-800'):
            ui.label('大脑状态:').classes('text-xs text-slate-500 uppercase font-bold')
            status_indicator = ui.label('待命 (Standby)').classes('text-emerald-400 font-mono text-sm')
            ui.space()
            
            async def trigger_brain():
                status_indicator.text = "正在唤醒神经网络..."
                status_indicator.classes('text-cyan-400', remove='text-emerald-400')
                ui.notify('万象大脑已开始全局扫描，请稍候...', type='info')
                
                try:
                    async with httpx.AsyncClient() as client:
                        # 暂时使用默认 ID，实际可从 URL 或全局上下文获取
                        resp = await client.post('http://localhost:5005/api/agent/brain', json={
                            "worldview_id": "default_wv",
                            "outline_id": None
                        }, timeout=60.0)
                        
                        if resp.status_code == 200:
                            data = resp.json()
                            status_indicator.text = "思考建议已更新"
                            status_indicator.classes('text-emerald-400', remove='text-cyan-400')
                            ui.notify('大脑深度思辨完成！', type='positive')
                            
                            # 局部刷新显示
                            refresh_brain_results(data)
                        else:
                            ui.notify(f'请求失败: {resp.text}', type='negative')
                except Exception as e:
                    ui.notify(f'大脑连接异常: {e}', type='negative')
                    status_indicator.text = "离线"
                    status_indicator.classes('text-red-400')

            ui.button('启动自主思辨扫描', on_click=trigger_brain).props('color="cyan" icon="psychology" outline').classes('shadow-lg shadow-cyan-500/10')

        # --- 结果展示区 ---
        results_container = ui.column().classes('w-full mt-6 gap-6')
        
        def refresh_brain_results(data):
            results_container.clear()
            
            with results_container:
                # 1. 逻辑审计报告
                with ui.card().classes('w-full bg-slate-900 border border-slate-800 p-6'):
                    with ui.row().classes('items-center gap-2 mb-4'):
                        ui.icon('report_problem', color='amber-400')
                        ui.label('逻辑一致性审计 (Audit Insights)').classes('text-lg font-bold text-white')
                    
                    insights = data.get('insights', [])
                    if not insights:
                        ui.label('未发现明显逻辑冲突。叙事逻辑稳健。').classes('text-slate-500 italic p-4')
                    else:
                        for ins in insights:
                            severity_color = 'red-400' if ins.get('severity') == 'high' else 'amber-400'
                            with ui.column().classes('mb-4 p-4 bg-black/30 rounded border-l-4 border-' + severity_color):
                                ui.label(ins['problem']).classes('text-sm font-bold text-slate-200')
                                ui.label(f"💡 建议: {ins['suggestion']}").classes('text-xs text-slate-400 mt-1')
                
                # 2. 创意扩张种子
                with ui.card().classes('w-full bg-slate-900 border border-slate-800 p-6'):
                    with ui.row().classes('items-center gap-2 mb-4'):
                        ui.icon('auto_awesome', color='cyan-400')
                        ui.label('自主创意扩张种子 (Expansion Seeds)').classes('text-lg font-bold text-white')
                    
                    seeds = data.get('expansion_seeds', [])
                    if not seeds:
                        ui.label('当前无待办创意种子。').classes('text-slate-500 italic p-4')
                    else:
                        with ui.row().classes('w-full gap-4'):
                            for seed in seeds:
                                with ui.card().classes('flex-1 bg-black/40 border border-slate-700 hover:border-cyan-500/50 transition-all'):
                                    ui.label(seed['name']).classes('text-sm font-bold text-cyan-400 uppercase tracking-tighter')
                                    ui.label(seed['category']).classes('text-[8px] bg-cyan-900/30 text-cyan-300 px-1 rounded')
                                    ui.label(seed['description']).classes('text-xs text-slate-400 mt-2 line-clamp-3')
                                    ui.button('采纳此想法', color='cyan-900').props('flat size="sm" icon="add"').classes('mt-2')

                # 3. 大脑派发的跨 Agent 指令
                with ui.card().classes('w-full bg-slate-900 border border-slate-800 p-6'):
                    with ui.row().classes('items-center gap-2 mb-4'):
                        ui.icon('smart_toy', color='purple-400')
                        ui.label('大脑指派任务 (Agent Orchestration)').classes('text-lg font-bold text-white')
                    
                    commands = data.get('pending_commands', [])
                    if not commands:
                        ui.label('目前无协同任务派发。').classes('text-slate-500 italic p-4')
                    else:
                        with ui.column().classes('w-full gap-2'):
                            for cmd in commands:
                                with ui.row().classes('w-full items-center p-3 bg-slate-950 rounded border border-slate-800'):
                                    ui.label(f"TARGET: {cmd['target'].upper()}").classes('text-[10px] font-mono font-bold text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded')
                                    ui.label(cmd['query']).classes('text-xs text-slate-300 flex-grow px-2')
                                    ui.badge(cmd['priority'], color='red' if cmd['priority']=='high' else 'blue')

        # 初始空白提示
        with results_container:
            with ui.column().classes('w-full items-center justify-center py-20 opacity-30'):
                ui.icon('neurology', size='6rem', color='slate-500')
                ui.label('请点击上方按钮唤醒大脑神经网络').classes('text-slate-500 mt-4')
