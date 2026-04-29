from nicegui import ui
import json
import os
import sys
import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common.lore_utils import get_all_templates, upsert_category_template, delete_category_template, add_new_category
from src.common.config_utils import load_config, save_config
from ui.layout import page_layout

FLASK_API = 'http://localhost:5006'


def _load_config():
    """加载模块化 YAML 配置用于展示。"""
    return load_config()


def _save_config(config):
    """保存配置到 config/*.yml。"""
    return save_config(config)


@ui.page('/settings')
def settings_page():
    with page_layout():
        ui.label('设置与模板管理').classes('text-2xl font-bold text-white mb-2')
        ui.label('管理世界观分类模板与系统配置项。').classes('text-slate-400 text-sm mb-6')

        # ========== 第一部分：模板管理 ==========
        with ui.card().classes('w-full bg-slate-900 border border-slate-700 p-6'):
            ui.label('世界观分类模板').classes('text-lg font-bold text-white mb-4')
            ui.label('定义各世界观分类的 JSON 架构（如种族、阵营、地理等）。').classes('text-slate-400 text-xs mb-4')

            state = {'templates': {}, 'selected': None}

            def refresh_templates():
                state['templates'] = get_all_templates()
                state['selected'] = None
                template_list.refresh()
                template_editor.refresh(None)

            # -- 模板列表 + 编辑器 --
            with ui.row().classes('w-full items-start gap-6'):
                # 左侧：模板列表
                with ui.column().classes('w-1/3 gap-2'):
                    @ui.refreshable
                    def template_list():
                        templates = state['templates']
                        if not templates:
                            ui.label('暂无模板数据。').classes('text-slate-500 text-sm italic')
                            return
                        for cat_id, cat_data in templates.items():
                            name_zh = cat_data.get('name_zh', '')
                            is_selected = state['selected'] == cat_id
                            bg = 'bg-indigo-900/40 border-indigo-500' if is_selected else 'bg-black/30 border-slate-700 hover:border-slate-500'
                            with ui.card().classes(f'w-full cursor-pointer {bg} border').on('click', lambda _, c=cat_id: select_template(c)):
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('category', size='1.2rem').classes('text-indigo-400')
                                    with ui.column().classes('gap-0'):
                                        ui.label(cat_id).classes('text-white text-sm font-bold')
                                        if name_zh:
                                            ui.label(name_zh).classes('text-slate-400 text-[10px]')

                    template_list()

                # 右侧：编辑器
                with ui.column().classes('flex-1'):
                    @ui.refreshable
                    def template_editor(cat_id=None):
                        if cat_id is None:
                            with ui.column().classes('w-full items-center justify-center py-12'):
                                ui.icon('touch_app', size='3rem').classes('text-slate-600 mb-2')
                                ui.label('请从左侧选择一个分类以查看或编辑其模板。').classes('text-slate-500 text-sm')
                            return

                        cat_data = state['templates'].get(cat_id, {})
                        name_zh = cat_data.get('name_zh', '')

                        with ui.column().classes('w-full gap-4'):
                            with ui.row().classes('items-center justify-between'):
                                with ui.column().classes('gap-0'):
                                    ui.label(f'{cat_id}').classes('text-xl font-bold text-white')
                                    if name_zh:
                                        ui.label(name_zh).classes('text-indigo-400 text-sm')
                                with ui.row().classes('gap-2'):
                                    ui.button('保存', on_click=lambda: save_template(cat_id, editor.value)).props('color="positive" icon="save"')
                                    ui.button('删除', on_click=lambda: confirm_delete_template(cat_id)).props('color="negative" icon="delete" outline')

                            editor = ui.textarea(
                                '模板 JSON',
                                value=json.dumps(cat_data, ensure_ascii=False, indent=4)
                            ).classes('w-full h-80 font-mono text-xs')

                    template_editor()

            def select_template(cat_id):
                state['selected'] = cat_id
                template_list.refresh()
                template_editor.refresh(cat_id)

            def save_template(cat_id, raw_json):
                try:
                    template_data = json.loads(raw_json)
                    success = upsert_category_template(cat_id, template_data)
                    if success:
                        ui.notify(f'模板 "{cat_id}" 保存成功！', type='positive')
                        refresh_templates()
                    else:
                        ui.notify('保存失败', type='negative')
                except json.JSONDecodeError as e:
                    ui.notify(f'JSON 格式错误：{e}', type='negative')

            def confirm_delete_template(cat_id):
                with ui.dialog() as dialog, ui.card().classes('bg-slate-900 border border-red-800'):
                    ui.label(f'确认删除模板 "{cat_id}"？').classes('text-lg font-bold text-red-400')
                    ui.label('此操作将永久删除该分类及其模板架构，不可撤销。').classes('text-slate-400 text-sm my-4')
                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('取消', on_click=dialog.close).props('flat')
                        ui.button('删除', on_click=lambda: do_delete_template(dialog, cat_id)).props('color="negative"')
                dialog.open()

            def do_delete_template(dialog, cat_id):
                success = delete_category_template(cat_id)
                if success:
                    ui.notify(f'已删除 "{cat_id}"', type='warning')
                    dialog.close()
                    refresh_templates()
                else:
                    ui.notify(f'删除 "{cat_id}" 失败', type='negative')

            # -- 新建分类 --
            ui.separator().classes('my-4')
            with ui.expansion('新建分类模板', icon='add_circle').classes('w-full bg-black/20 border border-slate-800 rounded-lg'):
                with ui.column().classes('gap-4 p-4'):
                    new_cat_id = ui.input('分类标识（如 "factions"）').classes('w-full')
                    new_cat_name = ui.input('中文名称（如 "阵营"）').classes('w-full')
                    new_cat_template = ui.textarea('初始模板 JSON（可选）', value='{}').classes('w-full h-32 font-mono text-xs')

                    def create_category():
                        cat_id = new_cat_id.value.strip()
                        name_zh = new_cat_name.value.strip()
                        if not cat_id or not name_zh:
                            ui.notify('分类标识和中文名称为必填项。', type='warning')
                            return
                        try:
                            tpl = json.loads(new_cat_template.value) if new_cat_template.value.strip() else None
                        except json.JSONDecodeError as e:
                            ui.notify(f'模板 JSON 格式错误：{e}', type='negative')
                            return
                        success, msg = add_new_category(cat_id, name_zh, tpl)
                        if success:
                            ui.notify(msg, type='positive')
                            new_cat_id.value = ''
                            new_cat_name.value = ''
                            new_cat_template.value = '{}'
                            refresh_templates()
                        else:
                            ui.notify(msg, type='negative')

                    ui.button('创建', on_click=create_category).props('color="primary" icon="add"')

            # 初始加载
            refresh_templates()

        # ========== 第二部分：AI 自主化设置 ==========
        with ui.card().classes('w-full bg-slate-900 border border-slate-700 p-6 mt-6'):
            ui.label('AI 自主化引擎控制 (Autonomy)').classes('text-lg font-bold text-white mb-2')
            ui.label('调整 Agent 的决策边界：模式越“激进”，AI 绕过人工确认并自主存库的概率越高。').classes('text-slate-400 text-xs mb-6')

            config = _load_config()
            current_level = config.get("AUTONOMY_LEVEL", "balanced")
            
            with ui.row().classes('w-full items-center gap-8 mb-6'):
                autonomy_radio = ui.radio(
                    {'safe': '安全模式 (Safe)', 'balanced': '均衡模式 (Balanced)', 'aggressive': '激进模式 (Aggressive)'},
                    value=current_level
                ).props('inline color="cyan" dark').classes('text-slate-200')

            def update_autonomy():
                new_level = autonomy_radio.value
                current_config = _load_config()
                current_config["AUTONOMY_LEVEL"] = new_level
                if _save_config(current_config):
                    ui.notify(f'自主化等级已切换至: {new_level.upper()}', type='positive')
                    # 提示手动重启后台或配置热重载
                    ui.notify('配置已持久化，新的 Agent 请求将应用此设置。', type='info')
                else:
                    ui.notify('保存失败，请检查文件权限。', type='negative')

            ui.button('应用并同步设置', on_click=update_autonomy).props('color="cyan" text-color="black" icon="sync"')

        # ========== 第三部分：系统配置（详见） ==========
        with ui.card().classes('w-full bg-slate-900 border border-slate-700 p-6 mt-6'):
            ui.label('系统配置').classes('text-lg font-bold text-white mb-2')
            ui.label('当前模块化 YAML 配置项（只读）。').classes('text-slate-400 text-xs mb-4')

            config = _load_config()
            if config:
                rows = []
                for key, val in config.items():
                    display_val = str(val)
                    if any(s in key.upper() for s in ['KEY', 'SECRET', 'PASSWORD', 'TOKEN']):
                        if isinstance(val, list):
                            display_val = f'[{len(val)} 个密钥，已隐藏]'
                        elif isinstance(val, str) and len(val) > 8:
                            display_val = val[:4] + '****' + val[-4:]
                    elif isinstance(val, (dict, list)):
                        display_val = json.dumps(val, ensure_ascii=False)[:120]
                    rows.append({'key': key, 'value': display_val})

                columns = [
                    {'name': 'key', 'label': '配置项', 'field': 'key', 'align': 'left', 'sortable': True},
                    {'name': 'value', 'label': '值', 'field': 'value', 'align': 'left'},
                ]
                ui.table(columns=columns, rows=rows, row_key='key').classes('w-full').props('flat bordered dense dark')
            else:
                ui.label('未找到配置文件或文件为空。').classes('text-slate-500 italic')
