from nicegui import ui, app
import json
import os
import sys
import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.layout import page_layout

FLASK_API = 'http://127.0.0.1:5006'


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


async def _fetch_lore(world_id, worldview_id=None, page=1, page_size=50):
    if not world_id:
        return []
    async with httpx.AsyncClient() as client:
        params = {'world_id': world_id, 'page': page, 'page_size': page_size}
        if worldview_id:
            params['worldview_id'] = worldview_id
        res = await client.get(f'{FLASK_API}/api/lore/list', params=params, timeout=10)
        return res.json() if res.status_code == 200 else []

async def _get_worlds():
    async with httpx.AsyncClient() as client:
        res = await client.get(f'{FLASK_API}/api/worlds/list', timeout=10)
        return res.json() if res.status_code == 200 else []

async def _get_worldviews(world_id):
    if not world_id:
        return []
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f'{FLASK_API}/api/worldviews/list',
            params={'world_id': world_id, 'page': 1, 'page_size': 50},
            timeout=10,
        )
        return res.json() if res.status_code == 200 else []

def _find_doc_by_id(docs, doc_id):
    for d in docs:
        if str(d.get('id')) == str(doc_id):
            return d
    return None


@ui.page('/lore')
async def lore_db_page():
    # Add D3.js to the head for this page
    ui.add_head_html('<script src="https://d3js.org/d3.v7.min.js"></script>')

    # 状态
    worlds = await _get_worlds()
    world_options = {world['world_id']: f"{world.get('name', world['world_id'])} ({world['world_id']})" for world in worlds}
    current_world = next(iter(world_options), None)
    worldviews = await _get_worldviews(current_world)
    wv_options = {wv['worldview_id']: wv['name'] for wv in worldviews}
    default_wv = next(iter(wv_options), None)
    
    current_wv = default_wv
    all_docs = await _fetch_lore(current_world, current_wv) if current_world and current_wv else []
    tree_format = build_tree_data(all_docs)
    state = {'selected_doc': None, 'all_docs': all_docs, 'current_world': current_world, 'current_wv': current_wv}

    async def update_world(new_world):
        state['current_world'] = new_world
        next_worldviews = await _get_worldviews(new_world)
        next_options = {wv['worldview_id']: wv['name'] for wv in next_worldviews}
        state['current_wv'] = next(iter(next_options), None)
        wv_select.options = next_options
        wv_select.value = state['current_wv']
        wv_select.update()
        state['all_docs'] = await _fetch_lore(state['current_world'], state['current_wv']) if state['current_wv'] else []
        tree.nodes = build_tree_data(state['all_docs'])
        detail_container.refresh(None)

    async def update_wv(new_wv):
        state['current_wv'] = new_wv
        state['all_docs'] = await _fetch_lore(state['current_world'], new_wv)
        tree.nodes = build_tree_data(state['all_docs'])
        detail_container.refresh(None)

    with page_layout():
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column():
                ui.label('世界观知识库浏览器').classes('text-2xl font-bold text-white')
                ui.label('浏览、编辑或删除设定库中的条目。').classes('text-slate-400 text-sm')
            
            with ui.row().classes('items-center gap-4 bg-slate-800/60 p-2 rounded-lg border border-slate-700'):
                ui.label('当前世界:').classes('text-slate-400 text-xs font-bold')
                world_select = ui.select(world_options, value=current_world, on_change=lambda e: update_world(e.value)).props('dark dense borderless').classes('min-w-[220px] text-cyan-400')
                ui.label('当前世界观:').classes('text-slate-400 text-xs font-bold')
                wv_select = ui.select(wv_options, value=current_wv, on_change=lambda e: update_wv(e.value)).props('dark dense borderless').classes('min-w-[150px] text-cyan-400')
                ui.button(icon='download', on_click=lambda: ui.download(f'{FLASK_API}/api/lore/export/opml?world_id={state["current_world"]}&worldview_id={state["current_wv"]}&page=1&page_size=50')).props('flat color="slate-400" size="sm"').tooltip('导出备份 (OPML)')

        with ui.tabs().classes('w-full') as tabs:
            tab_tree = ui.tab('分类浏览', icon='account_tree')
            tab_graph = ui.tab('实体关系图', icon='hub')
            tab_mindmap = ui.tab('知识思维导图', icon='psychology')

        with ui.tab_panels(tabs, value=tab_tree).classes('w-full bg-transparent'):
            # --- Tab 1: Tree View with Search ---
            with ui.tab_panel(tab_tree).classes('p-0'):
                with ui.row().classes('w-full items-center gap-4 mb-4 bg-slate-800/40 p-3 rounded-lg border border-slate-700'):
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
                                doc = _find_doc_by_id(state['all_docs'], real_id)
                                state['selected_doc'] = doc
                                detail_container.refresh(doc)

                            tree = ui.tree(
                                tree_format,
                                label_key='label',
                                on_select=on_select
                            ).classes('w-full text-white')

                            async def filter_tree(query):
                                if not query:
                                    tree.nodes = build_tree_data(state['all_docs'])
                                    return
                                query = query.lower()
                                
                                if semantic_toggle.value:
                                    try:
                                        async with httpx.AsyncClient() as client:
                                            res = await client.post(f'{FLASK_API}/api/search', json={'query': query, 'world_id': state['current_world'], 'worldview_id': state['current_wv']}, timeout=10)
                                            if res.status_code == 200:
                                                filtered = res.json()
                                            else:
                                                ui.notify(f"语义搜索失败: {res.status_code}", type='negative')
                                                return
                                    except Exception as ex:
                                        ui.notify(f"搜索请求出错: {ex}", type='negative')
                                        return
                                else:
                                    filtered = [d for d in state['all_docs'] if 
                                                query in (d.get('name') or '').lower() or 
                                                query in (d.get('content') or '').lower() or
                                                query in (d.get('category') or '').lower()]
                                                
                                tree.nodes = build_tree_data(filtered)
                                detail_container.refresh(None)

                    with splitter.after:
                        @ui.refreshable
                        def detail_container(doc=None):
                            if doc is None:
                                with ui.column().classes('w-full h-[600px] items-center justify-center'):
                                    ui.icon('arrow_back', size='3rem').classes('text-slate-600 mb-2')
                                    ui.label('从树中选择一个条目以查看详细信息。').classes('text-slate-500 text-sm')
                                return

                            name = doc.get('name') or doc.get('query') or '未命名'
                            content = doc.get('content') or '(无内容)'
                            doc_type = doc.get('type', 'unknown').upper()
                            
                            type_map_zh = {'WORLDVIEW': '世界观', 'OUTLINE': '大纲', 'PROSE': '正文', 'DRAFT': '草案'}
                            display_type = type_map_zh.get(doc_type, doc_type)
                            
                            doc_id = doc.get('id', '')
                            timestamp = doc.get('timestamp', '无')

                            with ui.column().classes('w-full gap-4 p-2'):
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
                                ui.label('详细内容').classes('text-xs font-bold text-slate-400 uppercase')
                                with ui.scroll_area().classes('w-full h-[400px] bg-black/30 rounded-lg border border-slate-800 p-4'):
                                    ui.markdown(content).classes('text-slate-300 text-sm')

                        detail_container()

            # --- Tab 2: Entity Graph ---
            with ui.tab_panel(tab_graph).classes('p-0'):
                with ui.column().classes('w-full h-[650px] bg-black/40 rounded-lg border border-slate-800 relative'):
                    graph_id = 'd3-graph-container'
                    graph_html = ui.html(f'<div id="{graph_id}" style="width:100%; height:100%;"></div>', sanitize=False).classes('w-full h-full')
                    
                    async def refresh_graph():
                        wv_id = state['current_wv']
                        graph_html.content = f'<div id="{graph_id}" style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; color:#64748b;"><p>图谱加载中...</p></div>'
                        
                        try:
                            async with httpx.AsyncClient() as client:
                                res = await client.get(
                                    f'{FLASK_API}/api/lore/entity-graph/all',
                                    params={'world_id': state['current_world'], 'worldview_id': wv_id, 'page': 1, 'page_size': 50},
                                    timeout=10,
                                )
                                if res.status_code == 200:
                                    data = res.json()
                                    if not data['nodes']:
                                        graph_html.content = '<div class="flex items-center justify-center h-full text-slate-500">暂无关联数据</div>'
                                        return
                                    
                                    # Inject D3 rendering script
                                    js_code = f"""
                                    (function() {{
                                        const container = document.getElementById('{graph_id}');
                                        container.innerHTML = '';
                                        const width = container.clientWidth;
                                        const height = container.clientHeight;
                                        const data = {json.dumps(data)};

                                        const svg = d3.select(container).append('svg')
                                            .attr('width', width)
                                            .attr('height', height)
                                            .call(d3.zoom().on('zoom', (event) => g.attr('transform', event.transform)))
                                            .append('g');
                                        
                                        const g = svg.append('g');

                                        const simulation = d3.forceSimulation(data.nodes)
                                            .force('link', d3.forceLink(data.links).id(d => d.id).distance(100))
                                            .force('charge', d3.forceManyBody().strength(-200))
                                            .force('center', d3.forceCenter(width / 2, height / 2));

                                        const link = g.append('g')
                                            .attr('stroke', '#475569')
                                            .attr('stroke-opacity', 0.6)
                                            .selectAll('line')
                                            .data(data.links)
                                            .join('line')
                                            .attr('stroke-width', d => Math.sqrt(d.value || 1));

                                        const node = g.append('g')
                                            .selectAll('circle')
                                            .data(data.nodes)
                                            .join('circle')
                                            .attr('r', d => d.val || 10)
                                            .attr('fill', d => d.type === 'entity' ? '#6366f1' : '#14b8a6')
                                            .call(d3.drag()
                                                .on('start', dragstarted)
                                                .on('drag', dragged)
                                                .on('end', dragended));

                                        node.append('title').text(d => d.name);

                                        const label = g.append('g')
                                            .selectAll('text')
                                            .data(data.nodes)
                                            .join('text')
                                            .text(d => d.name)
                                            .attr('font-size', '10px')
                                            .attr('fill', '#cbd5e1')
                                            .attr('dx', 12)
                                            .attr('dy', 4);

                                        simulation.on('tick', () => {{
                                            link.attr('x1', d => d.source.x)
                                                .attr('y1', d => d.source.y)
                                                .attr('x2', d => d.target.x)
                                                .attr('y2', d => d.target.y);

                                            node.attr('cx', d => d.x)
                                                .attr('cy', d => d.y);
                                            
                                            label.attr('x', d => d.x)
                                                 .attr('y', d => d.y);
                                        }});

                                        function dragstarted(event) {{
                                            if (!event.active) simulation.alphaTarget(0.3).restart();
                                            event.subject.fx = event.subject.x;
                                            event.subject.fys = event.subject.y;
                                        }}
                                        function dragged(event) {{
                                            event.subject.fx = event.x;
                                            event.subject.fy = event.y;
                                        }}
                                        function dragended(event) {{
                                            if (!event.active) simulation.alphaTarget(0);
                                            event.subject.fx = null;
                                            event.subject.fy = null;
                                        }}
                                    }})();
                                    """
                                    ui.run_javascript(js_code)
                                else:
                                    graph_html.content = '<div class="flex items-center justify-center h-full text-red-400">API 错误</div>'
                        except Exception as e:
                            graph_html.content = f'<div class="flex items-center justify-center h-full text-red-500">加载失败: {str(e)}</div>'

                    wv_select.on_value_change(refresh_graph)
                    ui.timer(0.5, refresh_graph, once=True)

            # --- Tab 3: Mindmap ---
            with ui.tab_panel(tab_mindmap).classes('p-0'):
                with ui.column().classes('w-full h-[650px] bg-black/40 rounded-lg border border-slate-800'):
                    mm_html = ui.html('', sanitize=False).classes('w-full h-full overflow-auto')
                    
                    async def refresh_mindmap():
                        wv_id = state['current_wv']
                        try:
                            async with httpx.AsyncClient() as client:
                                res = await client.get(
                                    f'{FLASK_API}/api/lore/mindmap',
                                    params={'world_id': state['current_world'], 'worldview_id': wv_id, 'page': 1, 'page_size': 50},
                                    timeout=10,
                                )
                                if res.status_code == 200:
                                    safe_md = res.text.replace('`', '\\`').replace('$', '\\$')
                                    mm_html.content = f"""
                                    <div id="mindmap-container" style="width:100%; height:100%; background:#09090b;">
                                        <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
                                        <script src="https://cdn.jsdelivr.net/npm/markmap-view"></script>
                                        <script src="https://cdn.jsdelivr.net/npm/markmap-lib"></script>
                                        <svg id="markmap-svg" style="width:100%; height:100%;"></svg>
                                        <script>
                                            try {{
                                                const {{ Markmap, loadCSS, loadJS }} = window.markmap;
                                                const transformer = new markmap.Transformer();
                                                const {{ root, features }} = transformer.transform(`{safe_md}`);
                                                Markmap.create('#markmap-svg', null, root);
                                            }} catch (e) {{
                                                document.getElementById('mindmap-container').innerHTML = '<div style="color:red; p:20px;">Render Error: ' + e.message + '</div>';
                                            }}
                                        </script>
                                    </div>
                                    """
                                else:
                                    mm_html.content = "<div class='p-4 text-slate-500'>该世界观暂无知识条目。</div>"
                        except Exception as ex:
                            mm_html.content = f"<div class='p-4 text-red-500'>加载失败: {ex}</div>"
                    
                    wv_select.on_value_change(refresh_mindmap)
                    ui.timer(0.1, refresh_mindmap, once=True)

    # ---- 辅助函数 ----
    def open_edit_dialog(doc):
        name = doc.get('name') or doc.get('query') or '未命名'
        content = doc.get('content') or ''
        doc_id = doc.get('id', '')
        doc_type = doc.get('type', '').lower()
        if doc_type == 'draft': doc_type = 'entity-draft'

        with ui.dialog() as dialog, ui.card().classes('w-[700px] bg-slate-900 border border-slate-700'):
            ui.label(f'编辑: {name}').classes('text-lg font-bold text-white mb-2')
            name_input = ui.input('条目名称', value=name).classes('w-full')
            content_input = ui.textarea('条目内容', value=content).classes('w-full h-64')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('保存', on_click=lambda: save_edit(dialog, doc_id, doc_type, name_input.value, content_input.value, doc.get('outline_id'))).props('color="positive"')
        dialog.open()

    async def save_edit(dialog, doc_id, doc_type, new_name, new_content, outline_id):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(f'{FLASK_API}/api/archive/update', json={
                    'id': doc_id, 'type': doc_type, 'content': new_content, 'name': new_name,
                    'world_id': state['current_world'], 'worldview_id': state['current_wv'], 'outline_id': outline_id
                }, timeout=10)
                if res.status_code == 200:
                    ui.notify(f'"{new_name}" 保存成功！', type='positive')
                    dialog.close()
                    state['all_docs'] = await _fetch_lore(state['current_world'], state['current_wv'])
                    doc = _find_doc_by_id(state['all_docs'], doc_id)
                    if doc: detail_container.refresh(doc)
                    tree.nodes = build_tree_data(state['all_docs'])
                else:
                    ui.notify(f"保存失败: {res.json().get('error', '未知错误')}", type='negative')
        except Exception as ex:
            ui.notify(f'保存出错: {ex}', type='negative')

    def confirm_delete(doc):
        name = doc.get('name') or '未命名'
        doc_id = doc.get('id', '')
        doc_type = doc.get('type', '').lower()
        if doc_type == 'draft': doc_type = 'entity-draft'

        with ui.dialog() as dialog, ui.card().classes('bg-slate-900 border border-red-800'):
            ui.label(f'确认删除 "{name}"？').classes('text-lg font-bold text-red-400')
            ui.label('此操作不可撤销。').classes('text-slate-400 text-sm my-2')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('删除', on_click=lambda: do_delete(dialog, doc_id, doc_type, name, doc.get('outline_id'))).props('color="negative"')
        dialog.open()

    async def do_delete(dialog, doc_id, doc_type, name, outline_id):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.request('DELETE', f'{FLASK_API}/api/archive/delete', json={
                    'id': doc_id, 'type': doc_type,
                    'world_id': state['current_world'], 'worldview_id': state['current_wv'], 'outline_id': outline_id
                }, timeout=10)
                if res.status_code == 200:
                    ui.notify(f'已删除 "{name}"', type='warning')
                    dialog.close()
                    state['all_docs'] = await _fetch_lore(state['current_world'], state['current_wv'])
                    detail_container.refresh(None)
                    tree.nodes = build_tree_data(state['all_docs'])
                else:
                    ui.notify(f"删除失败: {res.json().get('error', '未知错误')}", type='negative')
        except Exception as ex:
            ui.notify(f'删除错误: {ex}', type='negative')
