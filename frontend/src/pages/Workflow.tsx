import React, { useState } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Box, Typography, Paper, Chip, IconButton, Tooltip, Stack } from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import CreateIcon from '@mui/icons-material/Create';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import HowToRegIcon from '@mui/icons-material/HowToReg';
import SaveIcon from '@mui/icons-material/Save';
import TuneIcon from '@mui/icons-material/Tune';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import RefreshIcon from '@mui/icons-material/Refresh';
import AccountTreeIcon from '@mui/icons-material/AccountTree';

// --- Custom Node Styles & Components ---

const BaseNode = ({ icon: Icon, title, status, data, color }: any) => {
  const isActive = status === 'active';
  const isCompleted = status === 'completed';
  const isError = status === 'error';

  return (
    <div
      className={`glass-panel ${isActive ? 'node-active' : ''}`}
      style={{
        padding: '12px',
        borderRadius: '12px',
        minWidth: '180px',
        borderLeft: `4px solid ${color}`,
        position: 'relative',
        transition: 'all 0.3s ease'
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
        <Box sx={{ 
          p: 1, 
          borderRadius: '8px', 
          bgcolor: `${color}22`,
          color: color,
          display: 'flex'
        }}>
          <Icon sx={{ fontSize: 18 }} />
        </Box>
        <Typography variant="body2" sx={{ fontWeight: 600, color: 'white' }}>
          {title}
        </Typography>
      </Box>
      
      <Box sx={{ px: 1 }}>
        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.6)', display: 'block' }}>
          {data.label || '等待中...'}
        </Typography>
        {data.details && (
          <Typography variant="caption" sx={{ color: color, fontSize: '0.65rem', display: 'block', mt: 0.5 }}>
            {data.details}
          </Typography>
        )}
      </Box>

      {isCompleted && (
        <Box sx={{ position: 'absolute', top: -10, right: -10, bgcolor: '#4caf50', borderRadius: '50%', p: 0.5, display: 'flex' }}>
          <VerifiedUserIcon sx={{ fontSize: 12, color: 'white' }} />
        </Box>
      )}

      <Handle type="source" position={Position.Bottom} style={{ background: color }} />
    </div>
  );
};

const nodeTypes = {
  writing_retriever: (props: any) => <BaseNode {...props} icon={SearchIcon} title="RAG 知识锚定" color="#00bcd4" />,
  planner: (props: any) => <BaseNode {...props} icon={TuneIcon} title="场次策划" color="#9c27b0" />,
  write_draft: (props: any) => (
    <Box sx={{ position: 'relative' }}>
      <BaseNode {...props} icon={CreateIcon} title="文学创作" color="#ff9800" />
      {props.data.mode && (
        <Chip 
          label={props.data.mode === 'patch' ? 'PATCH' : 'REWRITE'} 
          size="small" 
          color={props.data.mode === 'patch' ? 'info' : 'warning'}
          icon={props.data.mode === 'patch' ? <AccountTreeIcon sx={{ fontSize: 12 }}/> : <RefreshIcon sx={{ fontSize: 12 }}/>}
          sx={{ position: 'absolute', bottom: -12, left: '50%', transform: 'translateX(-50%)', height: 18, fontSize: '0.6rem', fontWeight: 800 }}
        />
      )}
    </Box>
  ),
  audit_logic: (props: any) => <BaseNode {...props} icon={VerifiedUserIcon} title="逻辑审计" color="#f44336" />,
  human: (props: any) => <BaseNode {...props} icon={HowToRegIcon} title="人工核准" color="#4caf50" />,
  prose_saver: (props: any) => <BaseNode {...props} icon={SaveIcon} title="物理入库" color="#ffeb3b" />,
};

// --- Mock Workflow Logic ---

const initialNodes: Node[] = [
  { id: 'n1', type: 'writing_retriever', position: { x: 250, y: 0 }, data: { label: '等待检索指令...', status: 'idle' } },
  { id: 'n2', type: 'planner', position: { x: 250, y: 120 }, data: { label: '等待策划任务...', status: 'idle' } },
  { id: 'n3', type: 'write_draft', position: { x: 250, y: 240 }, data: { label: '等待创作启动...', status: 'idle' } },
  { id: 'n4', type: 'audit_logic', position: { x: 250, y: 360 }, data: { label: '等待审计逻辑...', status: 'idle' } },
  { id: 'n5', type: 'human', position: { x: 250, y: 480 }, data: { label: '等待人工介入...', status: 'idle' } },
];

const initialEdges: Edge[] = [
  { id: 'e1-2', source: 'n1', target: 'n2', animated: true, style: { stroke: '#00bcd4' } },
  { id: 'e2-3', source: 'n2', target: 'n3', animated: true, style: { stroke: '#9c27b0' } },
  { id: 'e3-4', source: 'n3', target: 'n4', animated: true, style: { stroke: '#ff9800' } },
  { id: 'e4-5', source: 'n4', target: 'n5', animated: true, style: { stroke: '#f44336' } },
];

// --- Main Dashboard ---

// --- Real-time Node Management ---

export const Workflow: React.FC = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [activeMode, setActiveMode] = useState<'patch' | 'rewrite'>('patch');
  const [logs, setLogs] = useState<{id: string, msg: string, type: string}[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);

  const runAgent = async (query: string) => {
    setIsProcessing(true);
    // Reset all nodes to idle
    setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, status: 'idle', label: '等待中...' } })));
    setLogs(prev => [{ id: Date.now().toString(), msg: "物理引擎初始化中...", type: 'system' }, ...prev]);
    
    try {
      const response = await fetch('/api/agent/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query,
          agent_type: 'writing',
          outline_id: 'pga_test_project',
          worldview_id: 'default_wv'
        })
      });

      if (!response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            
            if (data.type === 'node_update') {
              setNodes((nds) => {
                // Find current node index
                const currentIndex = nds.findIndex(n => n.type === data.node || (n.id === 'n3' && data.node === 'write_draft'));
                
                return nds.map((node, idx) => {
                  // This is the active node
                  if (node.type === data.node || (node.id === 'n3' && data.node === 'write_draft')) {
                    return { 
                      ...node, 
                      data: { 
                        ...node.data, 
                        label: data.status_message,
                        status: 'active',
                        mode: data.node === 'write_draft' ? activeMode : node.data.mode
                      } 
                    };
                  }
                  // Mark previous nodes as completed
                  if (currentIndex !== -1 && idx < currentIndex) {
                    return { ...node, data: { ...node.data, status: 'completed' } };
                  }
                  return node;
                });
              });

              if (data.node === 'atomic' || data.node === 'system') {
                setLogs(prev => [{
                  id: Math.random().toString(36).substr(2, 9),
                  msg: data.status_message,
                  type: data.node
                }, ...prev].slice(0, 50));
              }
            } else if (data.type === 'final_state') {
              setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, status: 'completed' } })));
              setLogs(prev => [{ id: 'final', msg: "全链路执行完毕，物理闭环已达成。", type: 'success' }, ...prev]);
              setIsProcessing(false);
            }
          } catch (e) {
            console.warn("JSON Parse error in stream:", e);
          }
        }
      }
    } catch (error) {
      setLogs(prev => [{ id: 'err', msg: `连接中断: ${error}`, type: 'error' }, ...prev]);
      setIsProcessing(false);
    }
  };

  return (
    <Box sx={{ 
      display: 'flex', 
      height: '100vh', 
      bgcolor: '#05050a',
      color: 'white',
      p: 3,
      gap: 3
    }}>
      {/* Sidebar Controls */}
      <Paper className="glass-panel" sx={{ width: 340, p: 3, borderRadius: '24px', display: 'flex', flexDirection: 'column', gap: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <AutoAwesomeIcon sx={{ color: '#00bcd4' }} />
          <Typography variant="h6" sx={{ fontWeight: 800, letterSpacing: -0.5 }}>万象星际 COMMAND</Typography>
        </Box>
        
        <Box>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.4)', mb: 1, display: 'block' }}>迭代策略控制</Typography>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
            <Tooltip title="增量修订 (保护模式)">
              <IconButton 
                onClick={() => setActiveMode('patch')}
                sx={{ 
                  bgcolor: activeMode === 'patch' ? 'rgba(0, 188, 212, 0.2)' : 'transparent',
                  border: `1px solid ${activeMode === 'patch' ? '#00bcd4' : 'rgba(255,255,255,0.1)'}`,
                  color: activeMode === 'patch' ? '#00bcd4' : 'white'
                }}
              >
                <AccountTreeIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="全量重写 (重塑模式)">
              <IconButton 
                onClick={() => setActiveMode('rewrite')}
                sx={{ 
                  bgcolor: activeMode === 'rewrite' ? 'rgba(255, 152, 0, 0.2)' : 'transparent',
                  border: `1px solid ${activeMode === 'rewrite' ? '#ff9800' : 'rgba(255,255,255,0.1)'}`,
                  color: activeMode === 'rewrite' ? '#ff9800' : 'white'
                }}
              >
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
          <button
            onClick={() => runAgent("开始创作")}
            disabled={isProcessing}
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '12px',
              border: 'none',
              background: 'linear-gradient(90deg, #00bcd4, #9c27b0)',
              color: 'white',
              fontWeight: 700,
              cursor: isProcessing ? 'not-allowed' : 'pointer',
              opacity: isProcessing ? 0.6 : 1
            }}
          >
            {isProcessing ? '正在执行物理逻辑...' : '启动创作引擎'}
          </button>
        </Box>

        <Box sx={{ flexGrow: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.4)', mb: 2, display: 'block' }}>实时原子日志 (Atomic Logs)</Typography>
          <Box sx={{ flexGrow: 1, overflowY: 'auto', pr: 1, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            <>
              {logs.map((log) => (
                <div
                  key={log.id}
                >
                  <Paper sx={{ 
                    p: 1.5, 
                    bgcolor: log.type === 'error' ? 'rgba(244, 67, 54, 0.1)' : 'rgba(255, 255, 255, 0.03)',
                    border: `1px solid ${log.type === 'error' ? 'rgba(244, 67, 54, 0.3)' : 'rgba(255, 255, 255, 0.08)'}`,
                    borderRadius: '10px' 
                  }}>
                    <Typography variant="caption" sx={{ 
                      color: log.type === 'error' ? '#f44336' : (log.type === 'system' ? '#00bcd4' : 'rgba(255,255,255,0.4)'), 
                      fontWeight: 700,
                      fontSize: '0.6rem',
                      textTransform: 'uppercase'
                    }}>
                      [{log.type}]
                    </Typography>
                    <Typography variant="body2" sx={{ fontSize: '0.75rem', mt: 0.2, color: 'rgba(255,255,255,0.9)' }}>
                      {log.msg}
                    </Typography>
                  </Paper>
                </div>
              ))}
            </>
          </Box>
        </Box>
      </Paper>

      {/* Main Flow Canvas */}
      <Box sx={{ flexGrow: 1, position: 'relative' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          style={{ background: 'transparent' }}
        >
          <Controls showInteractive={false} style={{ display: 'flex', flexDirection: 'row', bottom: 20, left: 20, background: 'rgba(255,255,255,0.05)', border: 'none', boxShadow: 'none' }} />
          <Background color="rgba(255,255,255,0.03)" gap={24} size={1} />
        </ReactFlow>

        {/* Global Progress Overlay */}
        <Box sx={{ position: 'absolute', top: 20, right: 20, textAlign: 'right' }}>
          <Typography variant="h4" sx={{ fontWeight: 900, mb: -0.5 }}>{isProcessing ? 'EXECUTING' : 'READY'}</Typography>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.4)' }}>系统实时运行状态</Typography>
        </Box>
      </Box>
    </Box>
  );
};
