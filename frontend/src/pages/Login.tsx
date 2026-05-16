import React, { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import LoginIcon from '@mui/icons-material/Login';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import { useLocation, useNavigate } from 'react-router-dom';
import { api, clearAuthToken, setApiKey, setAuthToken } from '../api/client';

type AuthMode = 'login' | 'register';

export const Login: React.FC<{ mode: AuthMode }> = ({ mode }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const redirectPath = params.get('redirect') || '/me';
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [apiKey, setApiKeyInput] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const title = mode === 'login' ? '登录' : '注册账号';

  const switchMode = (_: React.SyntheticEvent, nextMode: AuthMode) => {
    setError('');
    navigate(`/${nextMode}?redirect=${encodeURIComponent(redirectPath)}`, { replace: true });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');

    try {
      const response =
        mode === 'login'
          ? await api.login({ username, password })
          : await api.register({
              username,
              password,
              display_name: displayName || username,
              email,
            });

      const responseApiKey = response.data.api_key || response.data.user.api_key;
      setAuthToken(response.data.token);
      if (responseApiKey) {
        setApiKey(responseApiKey);
      }
      navigate(redirectPath, { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.error || '请求失败，请检查输入后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const useApiKey = () => {
    const value = apiKey.trim();
    if (!value) {
      setError('请输入 API Key');
      return;
    }
    clearAuthToken();
    setApiKey(value);
    navigate(redirectPath, { replace: true });
  };

  return (
    <Box sx={{ maxWidth: 520, mx: 'auto', mt: 6 }}>
      <Paper
        component="form"
        onSubmit={handleSubmit}
        sx={{
          p: 4,
          bgcolor: 'background.paper',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 2,
        }}
      >
        <Stack spacing={3}>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 800 }}>
              {title}
            </Typography>
          </Box>

          <Tabs value={mode} onChange={switchMode} aria-label="认证方式">
            <Tab icon={<LoginIcon />} iconPosition="start" label="登录" value="login" />
            <Tab icon={<PersonAddIcon />} iconPosition="start" label="注册" value="register" />
          </Tabs>

          {error && <Alert severity="error">{error}</Alert>}

          <TextField
            label="用户名"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
            fullWidth
          />
          {mode === 'register' && (
            <>
              <TextField
                label="显示名称"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                autoComplete="name"
                fullWidth
              />
              <TextField
                label="邮箱"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                fullWidth
              />
            </>
          )}
          <TextField
            label="密码"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            helperText={mode === 'register' ? '至少 6 位' : undefined}
            required
            fullWidth
          />
          <Button
            type="submit"
            variant="contained"
            startIcon={mode === 'login' ? <LoginIcon /> : <PersonAddIcon />}
            disabled={submitting}
            size="large"
          >
            {submitting ? '提交中' : title}
          </Button>

          <Box>
            <Stack spacing={2}>
              <TextField
                label="API Key"
                value={apiKey}
                onChange={(event) => setApiKeyInput(event.target.value)}
                autoComplete="off"
                fullWidth
              />
              <Button type="button" variant="outlined" onClick={useApiKey}>
                使用 API Key 访问
              </Button>
            </Stack>
          </Box>
        </Stack>
      </Paper>
    </Box>
  );
};
