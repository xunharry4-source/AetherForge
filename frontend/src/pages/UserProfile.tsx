import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import LogoutIcon from '@mui/icons-material/Logout';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useNavigate } from 'react-router-dom';
import { api, AuthUser, clearAuthCredentials } from '../api/client';

const formatValue = (value?: string) => value || '-';

export const UserProfile: React.FC = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadUser = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.getCurrentUser();
      setUser(response.data.user);
    } catch (err: any) {
      clearAuthCredentials();
      setError(err?.response?.data?.error || '登录状态已失效，请重新登录');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUser();
  }, []);

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      clearAuthCredentials();
      navigate('/login', { replace: true });
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Stack spacing={3}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, alignItems: 'center' }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800 }}>
            用户信息
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button startIcon={<RefreshIcon />} onClick={loadUser}>
            刷新
          </Button>
          <Button color="error" variant="outlined" startIcon={<LogoutIcon />} onClick={logout}>
            退出登录
          </Button>
        </Stack>
      </Box>

      {error && (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" onClick={() => navigate('/login', { replace: true })}>
              去登录
            </Button>
          }
        >
          {error}
        </Alert>
      )}

      {user && (
        <Paper
          sx={{
            p: 3,
            bgcolor: 'background.paper',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 2,
          }}
        >
          <Stack spacing={2}>
            {[
              ['用户 ID', user.user_id],
              ['用户名', user.username],
              ['显示名称', user.display_name],
              ['邮箱', formatValue(user.email)],
              ['API Key', formatValue(user.api_key)],
              ['创建时间', formatValue(user.created_at)],
              ['更新时间', formatValue(user.updated_at)],
              ['最近登录', formatValue(user.last_login_at)],
            ].map(([label, value]) => (
              <Box
                key={label}
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: '140px 1fr' },
                  gap: 1,
                  py: 1,
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                <Typography color="text.secondary">{label}</Typography>
                <Typography sx={{ wordBreak: 'break-word' }}>{value}</Typography>
              </Box>
            ))}
          </Stack>
        </Paper>
      )}
    </Stack>
  );
};
