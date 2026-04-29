import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Alert, Box, Typography, Paper, Grid,
  IconButton, Button, TextField, InputAdornment, Chip,
  List, ListItem, ListItemButton, ListItemText, ListItemIcon,
  Dialog, DialogTitle, DialogContent, DialogActions,
  CircularProgress, Tooltip, Stack, Collapse,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  ToggleButton, ToggleButtonGroup,
  FormControl, InputLabel, MenuItem, Select
} from '@mui/material';
import {
  Search as SearchIcon,
  Add as AddIcon,
  LibraryBooks as LoreIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  Public as WorldviewIcon,
  AutoAwesome as MagicIcon,
  Refresh as RefreshIcon,
  AccountTree as TreeIcon,
  TableRows as TableIcon,
  ExpandMore as ExpandMoreIcon,
  ChevronRight as ChevronRightIcon
} from '@mui/icons-material';

// --- Types ---
interface World {
  world_id: string;
  name: string;
  summary?: string;
}

interface Worldview {
  worldview_id: string;
  world_id?: string;
  name: string;
  summary?: string;
}

interface LoreEntry {
  id: string;
  type: string;
  name: string;
  content: string;
  category: string;
  timestamp?: string;
  outline_id?: string | null;
  worldview_id?: string | null;
  world_id?: string | null;
}

interface LoreTreeNode {
  name: string;
  path: string;
  order: number;
  children: Record<string, LoreTreeNode>;
  entries: LoreEntry[];
}

export const LoreDB: React.FC = () => {
  const [worlds, setWorlds] = useState<World[]>([]);
  const [selectedWorldId, setSelectedWorldId] = useState<string>('');
  const [worldviews, setWorldviews] = useState<Worldview[]>([]);
  const [selectedWV, setSelectedWV] = useState<string | null>(null);
  const [entries, setEntries] = useState<LoreEntry[]>([]);
  const [viewMode, setViewMode] = useState<'tree' | 'table'>('tree');
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isWVModalOpen, setIsWVModalOpen] = useState(false);
  const [isEntryModalOpen, setIsEntryModalOpen] = useState(false);
  const [newWV, setNewWV] = useState({ name: '', summary: '' });
  const [editingEntry, setEditingEntry] = useState<Partial<LoreEntry> | null>(null);
  const [error, setError] = useState<string | null>(null);

  // --- API Calls ---

  const fetchWorlds = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/worlds/list');
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      const data = await res.json();
      setWorlds(data);
      if (data.length > 0) {
        setSelectedWorldId((current) => current || data[0].world_id);
      } else {
        setSelectedWorldId('');
        setWorldviews([]);
        setSelectedWV(null);
        setEntries([]);
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
      setWorlds([]);
      setSelectedWorldId('');
      setWorldviews([]);
      setSelectedWV(null);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchWorldviews = useCallback(async (currentWorldId: string) => {
    if (!currentWorldId) {
      setWorldviews([]);
      setSelectedWV(null);
      setEntries([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/worldviews/list?world_id=${encodeURIComponent(currentWorldId)}&page=1&page_size=50`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      const data = await res.json();
      const mismatched = data.filter((worldview: Worldview) => worldview.world_id !== currentWorldId);
      if (mismatched.length > 0) {
        throw new Error(`接口返回了非当前世界的世界观: ${mismatched.map((item: Worldview) => item.worldview_id).join(', ')}`);
      }
      setWorldviews(data);
      setSelectedWV((current) => {
        if (data.some((worldview: Worldview) => worldview.worldview_id === current)) return current;
        return data[0]?.worldview_id || null;
      });
      if (data.length === 0) setEntries([]);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
      setWorldviews([]);
      setSelectedWV(null);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchEntries = useCallback(async (currentWorldId: string, wvId: string, query: string = '') => {
    if (!currentWorldId || !wvId) {
      setEntries([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const url = `/api/lore/list?world_id=${encodeURIComponent(currentWorldId)}&worldview_id=${encodeURIComponent(wvId)}${query ? `&query=${encodeURIComponent(query)}` : ''}&page=1&page_size=50`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      const data = await res.json();
      const mismatched = data.filter((entry: LoreEntry) => entry.world_id !== currentWorldId);
      if (mismatched.length > 0) {
        throw new Error(`接口返回了非当前世界的设定条目: ${mismatched.map((entry: LoreEntry) => entry.id).join(', ')}`);
      }
      setEntries(data);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWorlds();
  }, [fetchWorlds]);

  useEffect(() => {
    fetchWorldviews(selectedWorldId);
  }, [selectedWorldId, fetchWorldviews]);

  useEffect(() => {
    if (selectedWorldId && selectedWV) {
      fetchEntries(selectedWorldId, selectedWV, searchQuery);
    } else {
      setEntries([]);
    }
  }, [selectedWorldId, selectedWV, searchQuery, fetchEntries]);

  const handleCreateWorldview = async () => {
    if (!newWV.name || !selectedWorldId) return;
    setError(null);
    try {
      const res = await fetch('/api/worldviews/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...newWV, world_id: selectedWorldId })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      const data = await res.json();
      await fetchWorldviews(selectedWorldId);
      setSelectedWV(data.worldview_id);
      setIsWVModalOpen(false);
      setNewWV({ name: '', summary: '' });
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  };

  const handleSaveEntry = async () => {
    if (!editingEntry?.name || !selectedWV || !selectedWorldId) return;
    setError(null);
    try {
      const res = await fetch('/api/archive/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...editingEntry,
          type: 'worldview',
          world_id: selectedWorldId,
          worldview_id: selectedWV
        })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      fetchEntries(selectedWorldId, selectedWV, searchQuery);
      setIsEntryModalOpen(false);
      setEditingEntry(null);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  };

  const handleDeleteEntry = async (id: string) => {
    if (!selectedWorldId || !selectedWV) return;
    if (!window.confirm('确定要物理清理该设定条目吗？不可恢复。')) return;
    setError(null);
    try {
      const res = await fetch('/api/archive/delete', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, type: 'worldview', world_id: selectedWorldId, worldview_id: selectedWV })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      fetchEntries(selectedWorldId, selectedWV, searchQuery);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  };

  // --- UI Renderers ---
  const loreTree = useMemo(() => {
    const root: LoreTreeNode = { name: '全部设定', path: 'root', order: 0, children: {}, entries: [] };
    const selectedWorld = worlds.find((world) => world.world_id === selectedWorldId);
    const worldName = selectedWorld?.name || selectedWorldId || '未选择世界';
    const selectedWorldview = worldviews.find((worldview) => worldview.worldview_id === selectedWV);
    const worldviewName = selectedWorldview?.name || selectedWV || '未选择世界观';
    const outlineNameById = new Map<string, string>();

    entries.forEach((entry) => {
      if (entry.type === 'outline') {
        const outlineId = entry.outline_id || entry.id;
        outlineNameById.set(outlineId, entry.name || outlineId);
      }
    });

    const getChild = (parent: LoreTreeNode, key: string, name: string, order: number) => {
      if (!parent.children[key]) {
        parent.children[key] = {
          name,
          path: `${parent.path}/${key}`,
          order,
          children: {},
          entries: [],
        };
      } else {
        parent.children[key].name = name;
      }
      return parent.children[key];
    };

    const worldNode = getChild(root, `world:${selectedWorldId || 'unknown'}`, `世界：${worldName}`, 0);
    const worldviewNode = getChild(
      worldNode,
      `worldview:${selectedWV || 'unknown'}`,
      `世界观：${worldviewName}`,
      0
    );
    const worldviewEntriesNode = getChild(worldviewNode, 'worldview-entries', '世界观设定', 0);
    const uncategorizedNovelNode = getChild(worldviewNode, 'novel:unassigned', '小说：未归属小说', 99);
    const uncategorizedOutlineNode = getChild(uncategorizedNovelNode, 'outline:unassigned', '大纲：未归属大纲', 0);

    const getNovelOutlineNode = (entry: LoreEntry) => {
      const outlineId = entry.outline_id || (entry.type === 'outline' ? entry.id : null);
      if (!outlineId) return uncategorizedOutlineNode;

      const novelName = outlineNameById.get(outlineId) || outlineId;
      const novelNode = getChild(worldviewNode, `novel:${outlineId}`, `小说：${novelName}`, 10);
      return getChild(novelNode, `outline:${outlineId}`, `大纲：${novelName}`, 0);
    };

    entries.forEach((entry) => {
      if (entry.type === 'worldview') {
        worldviewEntriesNode.entries.push(entry);
        return;
      }

      if (entry.type === 'outline') {
        getNovelOutlineNode(entry).entries.push(entry);
        return;
      }

      if (entry.type === 'prose') {
        const outlineNode = getNovelOutlineNode(entry);
        const chapterNode = getChild(outlineNode, 'chapters', '章节', 0);
        chapterNode.entries.push(entry);
        return;
      }

      const fallbackNode = entry.outline_id
        ? getChild(getNovelOutlineNode(entry), 'related-materials', '关联资料', 1)
        : worldviewEntriesNode;
      fallbackNode.entries.push(entry);
    });

    const pruneEmptyNodes = (node: LoreTreeNode): boolean => {
      Object.entries(node.children).forEach(([key, child]) => {
        if (!pruneEmptyNodes(child)) {
          delete node.children[key];
        }
      });
      return node.path === 'root' || node.entries.length > 0 || Object.keys(node.children).length > 0;
    };

    pruneEmptyNodes(root);

    return root;
  }, [entries, selectedWV, selectedWorldId, worldviews, worlds]);

  const openEntryEditor = (entry: LoreEntry) => {
    setEditingEntry(entry);
    setIsEntryModalOpen(true);
  };

  const toggleTreeNode = (path: string) => {
    setExpandedNodes((current) => ({ ...current, [path]: current[path] === false ? true : false }));
  };

  const isNodeExpanded = (path: string) => expandedNodes[path] !== false;

  const renderTreeNode = (node: LoreTreeNode, depth = 0): React.ReactNode => {
    const children = Object.values(node.children).sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
    const hasContent = children.length > 0 || node.entries.length > 0;
    const expanded = isNodeExpanded(node.path);

    if (!hasContent) return null;

    return (
      <Box key={node.path}>
        {node.path !== 'root' && (
          <ListItem disablePadding sx={{ pl: depth * 2 }}>
            <ListItemButton onClick={() => toggleTreeNode(node.path)} sx={{ borderRadius: '10px' }}>
              <ListItemIcon sx={{ minWidth: 32, color: 'primary.main' }}>
                {expanded ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
              </ListItemIcon>
              <ListItemText
                primary={node.name}
                secondary={`${node.entries.length} 条直接设定 / ${children.length} 个子类`}
                primaryTypographyProps={{ variant: 'body2', fontWeight: 800 }}
                secondaryTypographyProps={{ variant: 'caption', sx: { opacity: 0.55 } }}
              />
            </ListItemButton>
          </ListItem>
        )}

        <Collapse in={node.path === 'root' || expanded} timeout="auto" unmountOnExit>
          {children.map((child) => renderTreeNode(child, node.path === 'root' ? 0 : depth + 1))}
          {node.entries
            .slice()
            .sort((a, b) => a.name.localeCompare(b.name))
            .map((entry) => (
              <ListItem key={entry.id} disablePadding sx={{ pl: (node.path === 'root' ? 0 : depth + 1) * 2 }}>
                <ListItemButton onClick={() => openEntryEditor(entry)} sx={{ borderRadius: '10px', alignItems: 'flex-start' }}>
                  <ListItemIcon sx={{ minWidth: 36, pt: 0.5 }}>
                    <LoreIcon sx={{ fontSize: 18, color: 'rgba(255,255,255,0.55)' }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
                        <Typography variant="body2" sx={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {entry.name}
                        </Typography>
                        <Chip label={entry.type} size="small" sx={{ height: 18, fontSize: '0.62rem' }} />
                      </Box>
                    }
                    secondary={entry.content || '无内容'}
                    secondaryTypographyProps={{
                      variant: 'caption',
                      sx: {
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                        opacity: 0.65,
                      },
                    }}
                  />
                  <IconButton
                    size="small"
                    onClick={(event) => {
                      event.stopPropagation();
                      handleDeleteEntry(entry.id);
                    }}
                    sx={{ color: 'rgba(255,255,255,0.25)', '&:hover': { color: 'error.main' } }}
                  >
                    <DeleteIcon sx={{ fontSize: 16 }} />
                  </IconButton>
                </ListItemButton>
              </ListItem>
            ))}
        </Collapse>
      </Box>
    );
  };

  return (
    <Box sx={{ display: 'flex', height: 'calc(100vh - 120px)', gap: 3 }}>
      
      {/* Sidebar: Worldview List */}
      <Paper className="glass-panel" sx={{ width: 280, p: 2, borderRadius: '20px', display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, px: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 800, color: 'primary.main' }}>世界观架构</Typography>
          <Tooltip title="新建世界观">
            <span>
            <IconButton size="small" disabled={!selectedWorldId} onClick={() => setIsWVModalOpen(true)} sx={{ color: 'primary.main' }}>
              <AddIcon fontSize="small" />
            </IconButton>
            </span>
          </Tooltip>
        </Box>
        
        <List sx={{ flexGrow: 1, overflowY: 'auto', px: 0 }}>
          {!selectedWorldId ? (
            <Alert severity="warning" sx={{ borderRadius: '12px' }}>必须选择世界</Alert>
          ) : worldviews.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 6, opacity: 0.45 }}>
              <WorldviewIcon sx={{ fontSize: 44, mb: 1 }} />
              <Typography variant="body2">当前世界暂无世界观</Typography>
            </Box>
          ) : worldviews.map((wv) => (
            <ListItem key={wv.worldview_id} disablePadding sx={{ mb: 1 }}>
              <ListItemButton
                selected={selectedWV === wv.worldview_id}
                onClick={() => setSelectedWV(wv.worldview_id)}
                sx={{
                  borderRadius: '12px',
                  '&.Mui-selected': {
                    bgcolor: 'rgba(0, 188, 212, 0.15)',
                    '&:hover': { bgcolor: 'rgba(0, 188, 212, 0.2)' }
                  }
                }}
              >
                <ListItemIcon sx={{ minWidth: 40 }}>
                  <WorldviewIcon sx={{ fontSize: 20, color: selectedWV === wv.worldview_id ? 'primary.main' : 'rgba(255,255,255,0.4)' }} />
                </ListItemIcon>
                <ListItemText 
                  primary={wv.name} 
                  primaryTypographyProps={{ variant: 'body2', fontWeight: selectedWV === wv.worldview_id ? 700 : 500 }}
                  secondary={wv.summary}
                  secondaryTypographyProps={{ variant: 'caption', noWrap: true, sx: { opacity: 0.5 } }}
                />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </Paper>

      {/* Main Area: Lore Grid */}
      <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {error && <Alert severity="error">{error}</Alert>}
        
        {/* Header Controls */}
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <FormControl size="small" required sx={{ minWidth: 280 }}>
            <InputLabel id="lore-world-select-label">世界</InputLabel>
            <Select
              labelId="lore-world-select-label"
              label="世界"
              value={selectedWorldId}
              onChange={(event) => {
                setSelectedWorldId(event.target.value);
                setSelectedWV(null);
                setEntries([]);
                setExpandedNodes({});
              }}
            >
              {worlds.map((world) => (
                <MenuItem key={world.world_id} value={world.world_id}>
                  {world.name} ({world.world_id})
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            fullWidth
            placeholder="搜索设定实体 (支持语义与关键字)..."
            variant="outlined"
            size="small"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: 'rgba(255,255,255,0.3)' }} />
                </InputAdornment>
              ),
              sx: { 
                borderRadius: '12px', 
                bgcolor: 'rgba(255,255,255,0.03)',
                '& fieldset': { borderColor: 'rgba(255,255,255,0.1)' }
              }
            }}
          />
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            disabled={!selectedWorldId || !selectedWV}
            onClick={() => {
              setEditingEntry({ id: '', name: '', content: '', category: 'General' });
              setIsEntryModalOpen(true);
            }}
            sx={{ 
              borderRadius: '12px', 
              whiteSpace: 'nowrap',
              background: 'linear-gradient(90deg, #00bcd4, #9c27b0)',
              px: 3
            }}
          >
            新增设定
          </Button>
          <IconButton
            disabled={!selectedWorldId || !selectedWV}
            onClick={() => selectedWorldId && selectedWV && fetchEntries(selectedWorldId, selectedWV, searchQuery)}
            sx={{ color: 'rgba(255,255,255,0.5)' }}
          >
            <RefreshIcon />
          </IconButton>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={viewMode}
            onChange={(_, value) => {
              if (value === 'tree' || value === 'table') setViewMode(value);
            }}
            sx={{
              bgcolor: 'rgba(255,255,255,0.03)',
              borderRadius: '12px',
              '& .MuiToggleButton-root': {
                color: 'rgba(255,255,255,0.6)',
                borderColor: 'rgba(255,255,255,0.12)',
                px: 1.5,
              },
              '& .Mui-selected': {
                color: 'primary.main',
                bgcolor: 'rgba(0, 188, 212, 0.12) !important',
              }
            }}
          >
            <ToggleButton value="tree" aria-label="树视图">
              <TreeIcon fontSize="small" />
            </ToggleButton>
            <ToggleButton value="table" aria-label="表格视图">
              <TableIcon fontSize="small" />
            </ToggleButton>
          </ToggleButtonGroup>
        </Box>

        {/* Entries: Tree/Table */}
        <Box sx={{ flexGrow: 1, overflowY: 'auto', pr: 1 }}>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
              <CircularProgress color="primary" />
            </Box>
          ) : !selectedWorldId ? (
            <Alert severity="warning">必须选择世界后才能查看世界观内容。</Alert>
          ) : viewMode === 'tree' ? (
            <Paper className="glass-panel" sx={{ borderRadius: '18px', overflow: 'hidden' }}>
              <Box sx={{ px: 2, py: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <TreeIcon sx={{ color: 'primary.main' }} />
                  <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>层级树视图</Typography>
                </Box>
                <Chip label={`${entries.length} 条`} size="small" />
              </Box>
              <List dense sx={{ p: 1.5 }}>
                {entries.length > 0 ? renderTreeNode(loreTree) : (
                  <Box sx={{ textAlign: 'center', py: 10, opacity: 0.35 }}>
                    <LoreIcon sx={{ fontSize: 60, mb: 2 }} />
                    <Typography>该世界观下暂无设定条目</Typography>
                  </Box>
                )}
              </List>
            </Paper>
          ) : (
            <TableContainer component={Paper} className="glass-panel" sx={{ borderRadius: '18px' }}>
              <Table stickyHeader size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 800, bgcolor: 'rgba(22,22,37,0.95)' }}>名称</TableCell>
                    <TableCell sx={{ fontWeight: 800, bgcolor: 'rgba(22,22,37,0.95)' }}>类型</TableCell>
                    <TableCell sx={{ fontWeight: 800, bgcolor: 'rgba(22,22,37,0.95)' }}>分类</TableCell>
                    <TableCell sx={{ fontWeight: 800, bgcolor: 'rgba(22,22,37,0.95)', minWidth: 360 }}>内容</TableCell>
                    <TableCell sx={{ fontWeight: 800, bgcolor: 'rgba(22,22,37,0.95)' }}>时间</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 800, bgcolor: 'rgba(22,22,37,0.95)' }}>操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {entries.map((entry) => (
                    <TableRow key={entry.id} hover sx={{ cursor: 'pointer' }} onClick={() => openEntryEditor(entry)}>
                      <TableCell sx={{ fontWeight: 700, maxWidth: 220 }}>
                        <Typography variant="body2" noWrap>{entry.name}</Typography>
                        <Typography variant="caption" sx={{ opacity: 0.45 }} noWrap>{entry.id}</Typography>
                      </TableCell>
                      <TableCell>
                        <Chip label={entry.type} size="small" sx={{ fontSize: '0.68rem' }} />
                      </TableCell>
                      <TableCell sx={{ maxWidth: 240 }}>
                        <Typography variant="body2" noWrap>{entry.category}</Typography>
                      </TableCell>
                      <TableCell>
                        <Typography
                          variant="body2"
                          sx={{
                            color: 'text.secondary',
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                            lineHeight: 1.45,
                          }}
                        >
                          {entry.content || '无内容'}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ opacity: 0.65, whiteSpace: 'nowrap' }}>
                        {entry.timestamp?.split('T')[0] || 'Unknown'}
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title="编辑">
                          <IconButton
                            size="small"
                            onClick={(event) => {
                              event.stopPropagation();
                              openEntryEditor(entry);
                            }}
                          >
                            <EditIcon sx={{ fontSize: 17 }} />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="删除">
                          <IconButton
                            size="small"
                            onClick={(event) => {
                              event.stopPropagation();
                              handleDeleteEntry(entry.id);
                            }}
                            sx={{ color: 'rgba(255,255,255,0.35)', '&:hover': { color: 'error.main' } }}
                          >
                            <DeleteIcon sx={{ fontSize: 17 }} />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                  {entries.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} align="center" sx={{ py: 10, opacity: 0.45 }}>
                        该世界观下暂无设定条目
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      </Box>

      {/* --- Modals --- */}

      {/* New Worldview Modal */}
      <Dialog 
        open={isWVModalOpen} 
        onClose={() => setIsWVModalOpen(false)}
        PaperProps={{ className: 'glass-panel', sx: { borderRadius: '20px', minWidth: 400 } }}
      >
        <DialogTitle sx={{ fontWeight: 800 }}>新建星际世界观</DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <TextField
              label="所属世界"
              fullWidth
              value={worlds.find((world) => world.world_id === selectedWorldId)?.name || selectedWorldId}
              InputProps={{ readOnly: true }}
              required
            />
            <TextField
              label="世界观名称"
              fullWidth
              value={newWV.name}
              onChange={(e) => setNewWV({ ...newWV, name: e.target.value })}
            />
            <TextField
              label="核心简述"
              fullWidth
              multiline
              rows={3}
              value={newWV.summary}
              onChange={(e) => setNewWV({ ...newWV, summary: e.target.value })}
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ p: 3 }}>
          <Button onClick={() => setIsWVModalOpen(false)} sx={{ color: 'text.secondary' }}>取消</Button>
          <Button onClick={handleCreateWorldview} variant="contained" sx={{ borderRadius: '10px' }}>确认部署</Button>
        </DialogActions>
      </Dialog>

      {/* Edit Entry Modal */}
      <Dialog 
        open={isEntryModalOpen} 
        onClose={() => setIsEntryModalOpen(false)}
        maxWidth="md"
        fullWidth
        PaperProps={{ className: 'glass-panel', sx: { borderRadius: '24px' } }}
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1.5, fontWeight: 800 }}>
          <MagicIcon sx={{ color: 'primary.main' }} />
          {editingEntry?.id ? '编辑设定条目' : '新增设定条目'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <Grid container spacing={2}>
              <Grid item xs={8}>
                <TextField
                  label="条目名称 / 实体名"
                  fullWidth
                  value={editingEntry?.name || ''}
                  onChange={(e) => setEditingEntry({ ...editingEntry, name: e.target.value })}
                />
              </Grid>
              <Grid item xs={4}>
                <TextField
                  label="分类"
                  fullWidth
                  value={editingEntry?.category || ''}
                  onChange={(e) => setEditingEntry({ ...editingEntry, category: e.target.value })}
                />
              </Grid>
            </Grid>
            <TextField
              label="设定详细内容"
              fullWidth
              multiline
              rows={12}
              value={editingEntry?.content || ''}
              onChange={(e) => setEditingEntry({ ...editingEntry, content: e.target.value })}
              sx={{ 
                '& .MuiInputBase-root': { fontFamily: 'monospace', fontSize: '0.9rem' }
              }}
            />
            <Typography variant="caption" sx={{ opacity: 0.5 }}>
              * 物理引擎会自动执行向量化索引，同步至 ChromaDB 以供 Agent 检索。
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ p: 3 }}>
          <Button onClick={() => setIsEntryModalOpen(false)} sx={{ color: 'text.secondary' }}>舍弃修改</Button>
          <Button onClick={handleSaveEntry} variant="contained" sx={{ 
            borderRadius: '12px', 
            background: 'linear-gradient(90deg, #00bcd4, #9c27b0)',
            px: 4
          }}>
            同步物理库
          </Button>
        </DialogActions>
      </Dialog>

    </Box>
  );
};
