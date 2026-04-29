import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  // System
  getHealth: () => apiClient.get('/api/system/health'),
  
  // Lore
  getLore: (params?: { worldview_id?: string; outline_id?: string }) => 
    apiClient.get('/api/lore/all', { params }),

  listLore: (params: { worldview_id?: string; outline_id?: string; novel_id?: string; world_id?: string; query?: string; page: number; page_size: number }) =>
    apiClient.get('/api/lore/list', { params }),

  listWorldviews: (params: { world_id?: string; worldview_id?: string; query?: string; page: number; page_size: number }) =>
    apiClient.get('/api/worldviews/list', { params }),

  listWorlds: () => apiClient.get('/api/worlds/list'),

  createWorld: (data: { name: string; summary?: string }) =>
    apiClient.post('/api/worlds/create', data),

  updateWorld: (data: { world_id: string; name?: string; summary?: string }) =>
    apiClient.post('/api/worlds/update', data),

  deleteWorld: (data: { world_id: string; cascade?: boolean }) =>
    apiClient.delete('/api/worlds/delete', { data }),

  createWorldview: (data: { name: string; summary?: string; world_id: string }) =>
    apiClient.post('/api/worldviews/create', data),

  updateWorldview: (data: { worldview_id: string; name?: string; summary?: string; world_id?: string }) =>
    apiClient.post('/api/worldviews/update', data),

  deleteWorldview: (data: { worldview_id: string; cascade?: boolean }) =>
    apiClient.delete('/api/worldviews/delete', { data }),

  listNovels: (params: { world_id?: string; novel_id?: string; query?: string; page: number; page_size: number }) =>
    apiClient.get('/api/novels/list', { params }),

  createNovel: (data: { name: string; summary?: string; world_id: string }) =>
    apiClient.post('/api/novels/create', data),

  updateNovel: (data: { novel_id: string; name?: string; summary?: string; world_id?: string }) =>
    apiClient.post('/api/novels/update', data),

  deleteNovel: (data: { novel_id: string; cascade?: boolean }) =>
    apiClient.delete('/api/novels/delete', { data }),

  getWorldHierarchyTree: (params: { world_id: string; worldview_id?: string; novel_id?: string; outline_id?: string; page: number; page_size: number }) =>
    apiClient.get('/api/world-hierarchy/tree', { params }),

  startHierarchyAgent: (data: {
    agent_type: 'world' | 'worldview' | 'novel' | 'outline' | 'chapter';
    action: 'create' | 'update' | 'delete';
    message?: string;
    payload: Record<string, unknown>;
  }) => apiClient.post('/api/hierarchy-agent/start', data),

  respondHierarchyAgent: (data: {
    run_id: string;
    decision: 'approve' | 'request_changes' | 'reject';
    message?: string;
    revision_mode?: 'partial_rewrite' | 'full_rewrite' | 'content_rewrite';
    manual_edit?: boolean;
    payload?: Record<string, unknown>;
  }) => apiClient.post('/api/hierarchy-agent/respond', data),

  getHierarchyAgent: (params: { run_id: string }) =>
    apiClient.get('/api/hierarchy-agent/get', { params }),

  listHierarchyAgents: (params: { agent_type?: string; status?: string; run_id?: string; page: number; page_size: number }) =>
    apiClient.get('/api/hierarchy-agent/list', { params }),

  listOutlines: (params: { world_id?: string; worldview_id?: string; novel_id?: string; outline_id?: string; query?: string; page: number; page_size: number }) =>
    apiClient.get('/api/outlines/list', { params }),

  createOutline: (data: { name: string; summary?: string; worldview_id?: string; novel_id?: string; world_id?: string }) =>
    apiClient.post('/api/outlines/create', data),

  updateArchiveItem: (data: {
    id: string;
    type: 'worldview' | 'outline' | 'prose' | 'novel' | 'entity-draft';
    name?: string;
    content?: string;
    category?: string;
    world_id?: string;
    worldview_id?: string;
    novel_id?: string;
    outline_id?: string;
  }) => apiClient.post('/api/archive/update', data),

  deleteArchiveItem: (data: {
    id: string;
    type: 'worldview' | 'outline' | 'prose' | 'novel' | 'entity-draft';
    world_id?: string;
    worldview_id?: string;
    novel_id?: string;
    outline_id?: string;
    cascade?: boolean;
  }) => apiClient.delete('/api/archive/delete', { data }),

  searchArchive: (data: { query: string; worldview_id?: string; outline_id?: string }) =>
    apiClient.post('/api/search', data),

  getOutlineChapterState: (params: { world_id?: string; worldview_id?: string; outline_id?: string; page: number; page_size: number }) =>
    apiClient.get('/api/workflow/outline-chapter/state', { params }),
  
  // Agents used by the outline/chapter workflow. Persisted data is reloaded from DB-backed APIs after every call.
  queryAgent: (data: { query: string; agent_type: string; world_id?: string; worldview_id?: string; outline_id?: string; thread_id?: string; resume_input?: string }) =>
    apiClient.post('/api/agent/query', data),

  resumeAgent: (data: { feedback: string; agent_type: string; thread_id: string }) =>
    apiClient.post('/api/agent/feedback', data),
};
