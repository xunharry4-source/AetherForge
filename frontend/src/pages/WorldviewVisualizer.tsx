import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  ReactFlow, Background, Controls, MiniMap, 
  useNodesState, useEdgesState, Node, Edge, 
  ConnectionLineType, MarkerType 
} from '@xyflow/react';
import { 
  Alert, Box, Text, Paper, Stack, Button, 
  Tree, Group, ActionIcon,
  Tooltip, Loader, Select, TextInput, Table, ScrollArea, Badge
} from '@mantine/core';
import { 
  IconBinaryTree, IconHierarchy, IconRefresh, 
  IconMaximize, IconInfoCircle, IconDatabase, IconSearch
} from '@tabler/icons-react';
import '@xyflow/react/dist/style.css';

// --- Types ---
interface LoreEntry {
  id: string;
  type: string;
  name: string;
  content?: string;
  category?: string;
  path?: string;
  world_id?: string;
  worldview_id?: string;
  outline_id?: string;
  novel_id?: string;
  timestamp?: string;
}

interface TreeNode {
  name: string;
  children: TreeNode[];
  entries: LoreEntry[];
}

interface VisualizerNodeData extends Record<string, unknown> {
  label: string;
  name: string;
  path: string[];
  entries: LoreEntry[];
}

interface World {
  world_id: string;
  name: string;
  summary?: string;
}

// --- Layout Helpers ---
const DEFAULT_VISIBLE_DEPTH = 3;
const FOCUS_RELATION_DEPTH = 3;

const nodeKey = (parts: string[]) => parts.join(' / ') || 'root';

const treeToGraph = (node: TreeNode, x = 0, y = 0, level = 0, parentId?: string, path: string[] = [], maxDepth = DEFAULT_VISIBLE_DEPTH) => {
  const currentPath = [...path, node.name];
  const nodeId = `node:${nodeKey(currentPath)}`;
  const nodes: Node<VisualizerNodeData>[] = [{
    id: nodeId,
    position: { x, y },
    data: { label: `${node.name}${node.entries.length ? ` (${node.entries.length})` : ''}`, name: node.name, path: currentPath, entries: node.entries },
    style: { 
      background: level === 0 ? 'rgba(0, 188, 212, 0.2)' : 'rgba(156, 39, 176, 0.1)',
      color: '#fff',
      border: '1px solid rgba(255,255,255,0.2)',
      borderRadius: '8px',
      padding: '10px',
      fontSize: '12px',
      fontWeight: 600,
      width: 150,
      textAlign: 'center'
    }
  }];
  const edges: Edge[] = [];

  if (parentId) {
    edges.push({
      id: `e-${parentId}-${nodeId}`,
      source: parentId,
      target: nodeId,
      type: ConnectionLineType.SmoothStep,
      animated: true,
      style: { stroke: 'rgba(255,255,255,0.2)' },
      markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(255,255,255,0.2)' }
    });
  }

  if (level >= maxDepth - 1) {
    return { nodes, edges };
  }

  const visibleChildren = node.children.slice(0, 24);
  let currentX = x - ((visibleChildren.length - 1) * 200) / 2;
  visibleChildren.forEach((child) => {
    const { nodes: childNodes, edges: childEdges } = treeToGraph(child, currentX, y + 150, level + 1, nodeId, currentPath, maxDepth);
    nodes.push(...childNodes);
    edges.push(...childEdges);
    currentX += 200;
  });

  return { nodes, edges };
};

const splitPath = (value?: string) =>
  (value || '')
    .split('>')
    .map((part) => part.trim())
    .filter(Boolean);

const buildLimitedTree = (node: TreeNode, maxDepth = DEFAULT_VISIBLE_DEPTH, level = 0): TreeNode => ({
  ...node,
  children: level >= maxDepth - 1 ? [] : node.children.map((child) => buildLimitedTree(child, maxDepth, level + 1)),
});

type DescendantTreeNode = { node: TreeNode; path: string[]; depth: number };

const findTreeNodeByPath = (root: TreeNode | null, pathParts: string[]): TreeNode | null => {
  if (!root) return null;
  const normalizedRoot = root.name.trim();
  const parts = pathParts[0] === normalizedRoot ? pathParts.slice(1) : pathParts;
  let current: TreeNode | null = root;
  for (const part of parts) {
    if (!current) return null;
    const next: TreeNode | undefined = current.children.find((child: TreeNode) => child.name === part);
    if (!next) return null;
    current = next;
  }
  return current;
};

const normalizeTreePath = (root: TreeNode | null, pathParts: string[]) => {
  if (!root) return pathParts.filter(Boolean);
  return pathParts[0] === root.name ? pathParts.slice(1) : pathParts;
};

const collectDescendantNodes = (node: TreeNode | null, maxDepth: number, startPath: string[], depth = 0): DescendantTreeNode[] => {
  if (!node || depth >= maxDepth) return [];
  return node.children.flatMap((child): DescendantTreeNode[] => {
    const path = [...startPath, child.name];
    return [{ node: child, path, depth: depth + 1 }, ...collectDescendantNodes(child, maxDepth, path, depth + 1)];
  });
};

const baseNodeStyle = {
  color: '#fff',
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: '8px',
  padding: '10px',
  fontSize: '12px',
  textAlign: 'center' as const,
};

const buildFocusGraph = (root: TreeNode | null, entry: LoreEntry) => {
  const rawParts = splitPath(entry.path || entry.category);
  const pathParts = rawParts.length > 0 ? rawParts : ['未分类'];
  const ancestorParts = pathParts.slice(Math.max(0, pathParts.length - FOCUS_RELATION_DEPTH));
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  let previousId: string | undefined;

  ancestorParts.forEach((part, index) => {
    const fullPath = pathParts.slice(0, pathParts.length - ancestorParts.length + index + 1);
    const id = `focus:path:${nodeKey(fullPath)}`;
    nodes.push({
      id,
      position: { x: 120 + index * 230, y: 130 },
      data: { label: part },
      style: {
        background: index === ancestorParts.length - 1 ? 'rgba(0, 188, 212, 0.22)' : 'rgba(255,255,255,0.08)',
        color: '#fff',
        border: '1px solid rgba(255,255,255,0.2)',
        borderRadius: '8px',
        padding: '10px',
        fontSize: '12px',
        fontWeight: 700,
        width: 170,
        textAlign: 'center',
      },
    });
    if (previousId) {
      edges.push({
        id: `focus:e:${previousId}-${id}`,
        source: previousId,
        target: id,
        type: ConnectionLineType.SmoothStep,
        markerEnd: { type: MarkerType.ArrowClosed },
      });
    }
    previousId = id;
  });

  const entryId = `focus:entry:${entry.id}`;
  nodes.push({
    id: entryId,
    position: { x: 120 + ancestorParts.length * 230, y: 130 },
    data: { label: `${entry.name || entry.id}\n${entry.type || 'worldview'}` },
    style: {
      background: 'rgba(156, 39, 176, 0.28)',
      color: '#fff',
      border: '1px solid rgba(255,255,255,0.35)',
      borderRadius: '8px',
      padding: '12px',
      fontSize: '12px',
      fontWeight: 800,
      width: 210,
      whiteSpace: 'pre-line',
      textAlign: 'center',
    },
  });
  if (previousId) {
    edges.push({
      id: `focus:e:${previousId}-${entryId}`,
      source: previousId,
      target: entryId,
      type: ConnectionLineType.SmoothStep,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
    });
  }

  const targetNode = findTreeNodeByPath(root, pathParts);
  const descendants = collectDescendantNodes(targetNode, FOCUS_RELATION_DEPTH, pathParts).slice(0, 18);
  descendants.forEach(({ node, path }, index) => {
    const id = `focus:down:${nodeKey(path)}`;
    nodes.push({
      id,
      position: { x: 120 + ancestorParts.length * 230 + 260 + (index % 3) * 220, y: 40 + Math.floor(index / 3) * 110 },
      data: { label: `${node.name}${node.entries.length ? ` (${node.entries.length})` : ''}` },
      style: {
        background: 'rgba(0, 188, 212, 0.12)',
        color: '#fff',
        border: '1px solid rgba(255,255,255,0.18)',
        borderRadius: '8px',
        padding: '10px',
        fontSize: '12px',
        width: 170,
        textAlign: 'center',
      },
    });
    edges.push({
      id: `focus:e:${entryId}-${id}`,
      source: entryId,
      target: id,
      type: ConnectionLineType.SmoothStep,
      markerEnd: { type: MarkerType.ArrowClosed },
    });
  });

  return { nodes, edges };
};

const buildNextLevelGraph = (root: TreeNode | null, pathParts: string[], queriedEntries: LoreEntry[]) => {
  const cleanPath = pathParts.filter(Boolean);
  const targetNode = findTreeNodeByPath(root, cleanPath);
  const nodeName = cleanPath[cleanPath.length - 1] || '根节点';
  const parentId = `expand:${nodeKey(cleanPath)}`;
  const nodes: Node<VisualizerNodeData>[] = [{
    id: parentId,
    position: { x: 420, y: 40 },
    data: { label: `${nodeName}\n下一级`, name: nodeName, path: cleanPath, entries: targetNode?.entries || [] },
    style: {
      ...baseNodeStyle,
      background: 'rgba(0, 188, 212, 0.24)',
      fontWeight: 800,
      width: 210,
      whiteSpace: 'pre-line',
    },
  }];
  const edges: Edge[] = [];

  const directChildren = (targetNode?.children || []).slice(0, 24);
  directChildren.forEach((child, index) => {
    const childPath = [...cleanPath, child.name];
    const childId = `expand:child:${nodeKey(childPath)}`;
    nodes.push({
      id: childId,
      position: { x: 80 + (index % 4) * 230, y: 190 + Math.floor(index / 4) * 120 },
      data: { label: `${child.name}${child.entries.length ? ` (${child.entries.length})` : ''}`, name: child.name, path: childPath, entries: child.entries },
      style: {
        ...baseNodeStyle,
        background: 'rgba(156, 39, 176, 0.16)',
        fontWeight: 700,
        width: 180,
      },
    });
    edges.push({
      id: `expand:e:${parentId}-${childId}`,
      source: parentId,
      target: childId,
      type: ConnectionLineType.SmoothStep,
      markerEnd: { type: MarkerType.ArrowClosed },
    });
  });

  const directPathText = cleanPath.join(' > ');
  const directEntries = queriedEntries
    .filter((entry) => {
      const entryPath = entry.path || entry.category || '';
      const entryParts = splitPath(entryPath);
      return entryPath === directPathText || entryParts.length === cleanPath.length + 1 && entryParts.slice(0, cleanPath.length).join(' > ') === directPathText;
    })
    .slice(0, 16);

  directEntries.forEach((entry, index) => {
    const entryId = `expand:entry:${entry.id}`;
    nodes.push({
      id: entryId,
      position: { x: 80 + (index % 4) * 230, y: 190 + Math.ceil(directChildren.length / 4) * 120 + Math.floor(index / 4) * 120 },
      data: { label: `${entry.name || entry.id}\n${entry.type}`, name: entry.name || entry.id, path: splitPath(entry.path || entry.category), entries: [entry] },
      style: {
        ...baseNodeStyle,
        background: 'rgba(0, 188, 212, 0.12)',
        width: 180,
        whiteSpace: 'pre-line',
      },
    });
    edges.push({
      id: `expand:e:${parentId}-${entryId}`,
      source: parentId,
      target: entryId,
      type: ConnectionLineType.SmoothStep,
      markerEnd: { type: MarkerType.ArrowClosed },
    });
  });

  return { nodes, edges, childCount: directChildren.length, entryCount: directEntries.length };
};

// --- Main Component ---
export const WorldviewVisualizer: React.FC = () => {
  const [viewMode, setViewMode] = useState<string>('graph');
  const [worlds, setWorlds] = useState<World[]>([]);
  const [selectedWorldId, setSelectedWorldId] = useState<string>('');
  const [treeData, setTreeData] = useState<TreeNode | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<LoreEntry[]>([]);
  const [selectedEntry, setSelectedEntry] = useState<LoreEntry | null>(null);
  const [expandedNodeLabel, setExpandedNodeLabel] = useState('');
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const fetchWorlds = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/worlds/list');
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      setWorlds(data);
      if (data.length > 0) {
        setSelectedWorldId((current) => current || data[0].world_id);
      } else {
        setTreeData(null);
        setSearchResults([]);
        setSelectedEntry(null);
        setNodes([]);
        setEdges([]);
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
      setWorlds([]);
      setTreeData(null);
      setSearchResults([]);
      setSelectedEntry(null);
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  }, [setEdges, setNodes]);

  const fetchData = useCallback(async () => {
    if (!selectedWorldId) {
      setTreeData(null);
      setSearchResults([]);
      setSelectedEntry(null);
      setNodes([]);
      setEdges([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/lore/tree?world_id=${encodeURIComponent(selectedWorldId)}&page=1&page_size=50`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      setTreeData(data);
      setSelectedEntry(null);
      
      const { nodes: graphNodes, edges: graphEdges } = treeToGraph(data, 400, 50, 0, undefined, [], DEFAULT_VISIBLE_DEPTH);
      setNodes(graphNodes);
      setEdges(graphEdges);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
      setTreeData(null);
      setSelectedEntry(null);
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  }, [selectedWorldId, setEdges, setNodes]);

  const searchLore = useCallback(async () => {
    if (!selectedWorldId) {
      setSearchResults([]);
      return;
    }
    if (!searchQuery.trim()) {
      setSearchResults([]);
      setSelectedEntry(null);
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const res = await fetch(`/api/lore/list?world_id=${encodeURIComponent(selectedWorldId)}&query=${encodeURIComponent(searchQuery.trim())}&page=1&page_size=50`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      const mismatched = data.filter((entry: LoreEntry) => entry.world_id !== selectedWorldId);
      if (mismatched.length > 0) {
        throw new Error(`接口返回了非当前世界的内容: ${mismatched.map((entry: LoreEntry) => entry.id).join(', ')}`);
      }
      setSearchResults(data);
      setSelectedEntry(null);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
      setSearchResults([]);
      setSelectedEntry(null);
    } finally {
      setSearching(false);
    }
  }, [searchQuery, selectedWorldId]);

  const focusEntry = useCallback((entry: LoreEntry) => {
    setSelectedEntry(entry);
    setExpandedNodeLabel('');
    const { nodes: focusNodes, edges: focusEdges } = buildFocusGraph(treeData, entry);
    setNodes(focusNodes);
    setEdges(focusEdges);
    setViewMode('graph');
  }, [setEdges, setNodes, treeData]);

  const expandNode = useCallback(async (pathParts: string[]) => {
    if (!selectedWorldId || pathParts.length === 0) return;
    const cleanPathParts = normalizeTreePath(treeData, pathParts);
    const displayPath = cleanPathParts.length > 0 ? cleanPathParts : [treeData?.name || pathParts[pathParts.length - 1]];
    const query = cleanPathParts.length > 0 ? cleanPathParts.join(' > ') : pathParts[pathParts.length - 1];
    setSearching(true);
    setError(null);
    try {
      const res = await fetch(`/api/lore/list?world_id=${encodeURIComponent(selectedWorldId)}&query=${encodeURIComponent(query)}&page=1&page_size=50`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      const mismatched = data.filter((entry: LoreEntry) => entry.world_id !== selectedWorldId);
      if (mismatched.length > 0) {
        throw new Error(`接口返回了非当前世界的内容: ${mismatched.map((entry: LoreEntry) => entry.id).join(', ')}`);
      }
      const { nodes: expandedNodes, edges: expandedEdges, childCount, entryCount } = buildNextLevelGraph(treeData, cleanPathParts, data);
      setNodes(expandedNodes);
      setEdges(expandedEdges);
      setSelectedEntry(null);
      setExpandedNodeLabel(`${displayPath[displayPath.length - 1]}：${childCount} 个下级 / ${entryCount} 条内容`);
      setSearchResults(data);
      setViewMode('graph');
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setSearching(false);
    }
  }, [selectedWorldId, setEdges, setNodes, treeData]);

  const showDefaultGraph = useCallback(() => {
    if (!treeData) return;
    setSelectedEntry(null);
    setExpandedNodeLabel('');
    const { nodes: graphNodes, edges: graphEdges } = treeToGraph(treeData, 400, 50, 0, undefined, [], DEFAULT_VISIBLE_DEPTH);
    setNodes(graphNodes);
    setEdges(graphEdges);
    setViewMode('graph');
  }, [setEdges, setNodes, treeData]);

  useEffect(() => {
    fetchWorlds();
  }, [fetchWorlds]);

  useEffect(() => {
    if (selectedWorldId) {
      fetchData();
    }
  }, [fetchData, selectedWorldId]);

  // Mantine Tree format conversion
  const mantineTreeData = useMemo(() => {
    if (!treeData) return [];
    const limitedTree = buildLimitedTree(treeData, DEFAULT_VISIBLE_DEPTH);
    
    const transform = (node: TreeNode, path: string[] = []): any => ({
      label: node.name,
      value: nodeKey([...path, node.name]),
      children: node.children.map((child) => transform(child, [...path, node.name]))
    });
    
    return [transform(limitedTree)];
  }, [treeData]);

  return (
    <Box p="md" style={{ height: 'calc(100vh - 100px)', display: 'flex', flexDirection: 'column' }}>
      
      {/* Header Controls */}
      <Paper p="sm" mb="md" className="glass-panel" style={{ borderRadius: '16px' }}>
        <Group justify="space-between">
          <Group>
            <IconHierarchy color="#00bcd4" size={24} />
            <Text fw={800} size="lg">星际图谱视觉转换</Text>
            <Badge color="cyan" variant="light">默认显示 3 级</Badge>
            {selectedEntry && <Badge color="grape" variant="light">聚焦：{selectedEntry.name}</Badge>}
            {expandedNodeLabel && <Badge color="teal" variant="light">展开：{expandedNodeLabel}</Badge>}
          </Group>
          
          <Group>
            <Select
              required
              label="世界"
              placeholder="必须选择世界"
              data={worlds.map((world) => ({ value: world.world_id, label: `${world.name} (${world.world_id})` }))}
              value={selectedWorldId || null}
              onChange={(value) => setSelectedWorldId(value || '')}
              allowDeselect={false}
              w={300}
            />
            <Button variant={viewMode === 'graph' ? 'filled' : 'light'} color="cyan" onClick={showDefaultGraph}>关系图谱</Button>
            <Button variant={viewMode === 'tree' ? 'filled' : 'light'} color="cyan" onClick={() => setViewMode('tree')}>逻辑树</Button>
            <Tooltip label="刷新数据">
              <ActionIcon variant="light" color="cyan" size="lg" onClick={fetchData}>
                <IconRefresh size={20} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </Paper>

      <Paper p="sm" mb="md" className="glass-panel" style={{ borderRadius: '16px' }}>
        <Stack gap="sm">
          <Group align="end">
            <TextInput
              label="查询内容"
              placeholder="输入名称、内容或路径关键词"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.currentTarget.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') searchLore();
              }}
              style={{ flex: 1 }}
            />
            <Button leftSection={<IconSearch size={16} />} loading={searching} disabled={!selectedWorldId || !searchQuery.trim()} onClick={searchLore}>
              查询
            </Button>
          </Group>
          {searchResults.length > 0 && (
            <ScrollArea h={220}>
              <Table striped highlightOnHover withTableBorder withColumnBorders stickyHeader>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>名称</Table.Th>
                    <Table.Th>类型</Table.Th>
                    <Table.Th>层级路径</Table.Th>
                    <Table.Th>内容摘要</Table.Th>
                    <Table.Th>时间</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {searchResults.map((entry) => (
                    <Table.Tr
                      key={entry.id}
                      onClick={() => focusEntry(entry)}
                      style={{ cursor: 'pointer', background: selectedEntry?.id === entry.id ? 'rgba(156, 39, 176, 0.18)' : undefined }}
                    >
                      <Table.Td><Text size="sm" fw={700}>{entry.name || entry.id}</Text></Table.Td>
                      <Table.Td><Badge size="sm">{entry.type}</Badge></Table.Td>
                      <Table.Td><Text size="xs" c="dimmed">{entry.path || entry.category || '未分类'}</Text></Table.Td>
                      <Table.Td><Text size="xs" lineClamp={2}>{entry.content || '无内容'}</Text></Table.Td>
                      <Table.Td><Text size="xs" c="dimmed">{entry.timestamp?.split('T')[0] || 'Unknown'}</Text></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          )}
          {searchQuery.trim() && !searching && searchResults.length === 0 && (
            <Text size="xs" c="dimmed">当前查询暂无结果。</Text>
          )}
        </Stack>
      </Paper>

      {/* Main Content Area */}
      <Box style={{ flexGrow: 1, position: 'relative', overflow: 'hidden' }}>
        {error ? (
          <Alert color="red" title="真实接口请求失败">
            {error}
          </Alert>
        ) : !selectedWorldId ? (
          <Alert color="yellow" title="必须选择世界">
            当前没有可用世界，或世界列表尚未加载完成。
          </Alert>
        ) : loading ? (
          <Box style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <Loader color="cyan" size="xl" type="bars" />
          </Box>
        ) : viewMode === 'graph' ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={(_, node) => expandNode((node.data as VisualizerNodeData).path || [])}
            fitView
            style={{ background: 'transparent' }}
          >
            <Background color="rgba(255,255,255,0.05)" gap={20} />
            <Controls />
            <MiniMap 
              nodeColor={(n) => n.style?.background as string} 
              maskColor="rgba(0,0,0,0.5)"
              style={{ background: 'rgba(255,255,255,0.05)' }}
            />
          </ReactFlow>
        ) : (
          <Paper p="xl" className="glass-panel" style={{ height: '100%', overflowY: 'auto', borderRadius: '16px' }}>
            <Stack gap="xl">
              <Group>
                <IconBinaryTree size={28} color="#9c27b0" />
                <Text fw={700} size="lg">架构层级树（默认 3 级）</Text>
              </Group>
              
              <Tree
                data={mantineTreeData}
                levelOffset="xl"
                renderNode={({ node, expanded, hasChildren, elementProps }) => (
                  <Group
                    gap={5}
                    {...elementProps}
                    onClick={(event) => {
                      elementProps.onClick?.(event);
                      expandNode(String(node.value).split(' / '));
                    }}
                    style={{ padding: '8px 12px', borderRadius: '8px', cursor: 'pointer' }}
                  >
                    {hasChildren && (
                      <ActionIcon size="xs" variant="transparent" style={{ transition: 'transform 0.2s', transform: expanded ? 'rotate(90deg)' : 'none' }}>
                        <IconMaximize size={12} />
                      </ActionIcon>
                    )}
                    <IconDatabase size={16} color={hasChildren ? '#00bcd4' : '#9c27b0'} />
                    <Text size="sm" fw={hasChildren ? 700 : 400}>{node.label}</Text>
                  </Group>
                )}
              />
            </Stack>
          </Paper>
        )}
      </Box>
    </Box>
  );
};
