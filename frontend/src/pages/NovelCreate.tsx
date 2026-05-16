import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Badge,
  Box,
  Button,
  Grid,
  Group,
  Loader,
  Paper,
  ScrollArea,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import {
  IconArrowLeft,
  IconBook,
  IconDeviceFloppy,
  IconPlus,
  IconSettings,
  IconShieldCheck,
} from '@tabler/icons-react';
import { api } from '../api/client';

type World = {
  world_id: string;
  name: string;
};

type SettingRow = {
  id: string;
  key: string;
  value: string;
};

const uniqueWorldsById = (items: World[]): World[] => {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (!item.world_id || seen.has(item.world_id)) return false;
    seen.add(item.world_id);
    return true;
  });
};

const parseSettingValue = (value: string): unknown => {
  const trimmed = value.trim();
  if (!trimmed) return '';
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
};

export const NovelCreate: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [worlds, setWorlds] = useState<World[]>([]);
  const [worldId, setWorldId] = useState(searchParams.get('world_id') || '');
  const [name, setName] = useState('');
  const [introduction, setIntroduction] = useState('');
  const [summary, setSummary] = useState('');
  const [rules, setRules] = useState<string[]>([]);
  const [newRule, setNewRule] = useState('');
  const [settings, setSettings] = useState<SettingRow[]>([]);
  const [newSettingKey, setNewSettingKey] = useState('');
  const [newSettingValue, setNewSettingValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadWorlds = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.listWorlds();
      const nextWorlds = uniqueWorldsById((response.data as World[]) || []);
      setWorlds(nextWorlds);
      setWorldId((current) => current || nextWorlds[0]?.world_id || '');
    } catch (err: any) {
      setError(err?.response?.data?.error || err?.message || String(err));
      setWorlds([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorlds();
  }, [loadWorlds]);

  const basicSettings = useMemo(() => {
    const next: Record<string, unknown> = {};
    settings.forEach((item) => {
      const key = item.key.trim();
      if (key) {
        next[key] = parseSettingValue(item.value);
      }
    });
    return next;
  }, [settings]);

  const addRule = () => {
    const value = newRule.trim();
    if (!value) return;
    setRules((current) => [...current, value]);
    setNewRule('');
  };

  const addSetting = () => {
    const key = newSettingKey.trim();
    if (!key) return;
    setSettings((current) => [
      ...current.filter((item) => item.key.trim() !== key),
      { id: `${key}-${Date.now()}`, key, value: newSettingValue },
    ]);
    setNewSettingKey('');
    setNewSettingValue('');
  };

  const createNovel = async () => {
    setSaving(true);
    setError(null);
    try {
      const response = await api.createNovel({
        world_id: worldId,
        name: name.trim(),
        introduction,
        summary,
        forbidden_rules: rules.map((item) => item.trim()).filter(Boolean),
        basic_settings: basicSettings,
      });
      const novelId = response.data.novel_id as string;
      await api.getNovel({ novel_id: novelId });
      navigate(`/novels/${encodeURIComponent(novelId)}`);
    } catch (err: any) {
      setError(err?.response?.data?.error || err?.message || String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Stack gap="md" style={{ minHeight: 'calc(100vh - 96px)' }}>
      <Group justify="space-between" align="flex-start">
        <Box>
          <Group gap="xs">
            <IconBook size={24} />
            <Title order={2}>新增小说</Title>
            <Badge variant="light">CREATE</Badge>
          </Group>
          <Text size="sm" c="dimmed">创建小说时直接填写介绍、简介、小说禁止规则与小说设定规则。</Text>
        </Box>
        <Group gap="xs">
          <Button variant="light" leftSection={<IconArrowLeft size={16} />} onClick={() => navigate('/novels')}>返回小说列表</Button>
          <Button leftSection={<IconDeviceFloppy size={16} />} loading={saving} disabled={!worldId || !name.trim()} onClick={createNovel}>创建小说</Button>
        </Group>
      </Group>

      {error && <Alert color="red" title="真实接口请求失败">{error}</Alert>}
      {loading && <Loader />}

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Paper p="md" withBorder>
            <Stack gap="md">
              <Group gap="xs">
                <IconBook size={18} />
                <Text fw={800}>小说基础信息</Text>
              </Group>
              <Select
                label="所属世界"
                data={worlds.map((world) => ({ value: world.world_id, label: `${world.name} (${world.world_id})` }))}
                value={worldId || null}
                onChange={(value) => setWorldId(value || '')}
                searchable
              />
              <TextInput label="小说名称" value={name} onChange={(event) => setName(event.currentTarget.value)} />
              <Textarea label="小说介绍" minRows={4} value={introduction} onChange={(event) => setIntroduction(event.currentTarget.value)} />
              <Textarea label="小说简介" minRows={8} value={summary} onChange={(event) => setSummary(event.currentTarget.value)} />
            </Stack>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack gap="md">
            <Paper p="md" withBorder>
              <Stack gap="sm">
                <Group justify="space-between">
                  <Group gap="xs">
                    <IconShieldCheck size={18} />
                    <Text fw={800}>小说禁止规则</Text>
                  </Group>
                  <Badge variant="light">{rules.length} 条</Badge>
                </Group>
                <ScrollArea h={220}>
                  <Stack gap="xs">
                    {rules.map((rule, index) => (
                      <Textarea
                        key={`rule-${index}`}
                        label={`禁止规则 ${index + 1}`}
                        minRows={2}
                        value={rule}
                        onChange={(event) => setRules((current) => current.map((item, itemIndex) => (itemIndex === index ? event.currentTarget.value : item)))}
                      />
                    ))}
                    {rules.length === 0 && <Text size="sm" c="dimmed">当前还没有小说禁止规则。</Text>}
                  </Stack>
                </ScrollArea>
                <Textarea label="新增禁止规则" minRows={2} value={newRule} onChange={(event) => setNewRule(event.currentTarget.value)} />
                <Button variant="light" leftSection={<IconPlus size={16} />} onClick={addRule}>新增禁止规则</Button>
              </Stack>
            </Paper>

            <Paper p="md" withBorder>
              <Stack gap="sm">
                <Group justify="space-between">
                  <Group gap="xs">
                    <IconSettings size={18} />
                    <Text fw={800}>小说设定规则</Text>
                  </Group>
                  <Badge variant="light">{settings.length} 项</Badge>
                </Group>
                <ScrollArea h={260}>
                  <Stack gap="xs">
                    {settings.map((setting, index) => (
                      <Grid key={setting.id} gutter="xs" align="flex-start">
                        <Grid.Col span={{ base: 12, md: 4 }}>
                          <TextInput
                            label={`设定键 ${index + 1}`}
                            value={setting.key}
                            onChange={(event) => setSettings((current) => current.map((item) => (item.id === setting.id ? { ...item, key: event.currentTarget.value } : item)))}
                          />
                        </Grid.Col>
                        <Grid.Col span={{ base: 12, md: 8 }}>
                          <Textarea
                            label="设定值"
                            minRows={2}
                            value={setting.value}
                            onChange={(event) => setSettings((current) => current.map((item) => (item.id === setting.id ? { ...item, value: event.currentTarget.value } : item)))}
                          />
                        </Grid.Col>
                      </Grid>
                    ))}
                    {settings.length === 0 && <Text size="sm" c="dimmed">当前还没有小说设定规则。</Text>}
                  </Stack>
                </ScrollArea>
                <Grid gutter="xs" align="flex-end">
                  <Grid.Col span={{ base: 12, md: 4 }}>
                    <TextInput label="新增设定键" value={newSettingKey} onChange={(event) => setNewSettingKey(event.currentTarget.value)} />
                  </Grid.Col>
                  <Grid.Col span={{ base: 12, md: 8 }}>
                    <Textarea label="新增设定值" minRows={2} value={newSettingValue} onChange={(event) => setNewSettingValue(event.currentTarget.value)} />
                  </Grid.Col>
                </Grid>
                <Button variant="light" leftSection={<IconPlus size={16} />} onClick={addSetting}>新增或覆盖设定规则</Button>
              </Stack>
            </Paper>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
};
