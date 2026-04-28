import axios from 'axios';

const API_BASE_URL = 'http://localhost:5005';

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
  
  // Agents
  runBrain: (data: { worldview_id: string; outline_id?: string }) => 
    apiClient.post('/api/agent/brain', data),
    
  queryAgent: (data: { query: string; agent_type: string; worldview_id?: string; outline_id?: string }) =>
    apiClient.post('/api/agent/query', data),
};
