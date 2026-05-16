import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Button,
  Card,
  Grid,
  Group,
  Loader,
  Paper,
  ScrollArea,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
  Tooltip,
  Badge,
  ActionIcon,
  Modal,
} from '@mantine/core';
import {
  IconPlus,
  IconEdit,
  IconRefresh,
  IconTrash,
  IconSettings,
  IconWorld,
} from '@tabler/icons-react';
import { api } from '../api/client';
import { useNavigate } from 'react-router-dom';

type World = {
  world_id: string;
  name: string;
  summary?: string;
};

type Worldview = {
  worldview_id: string;
  world_id: string;
  name: string;
  summary?: string;
};

const uniqueWorldsById = (items: World[]): World[] => {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (!item.world_id || seen.has(item.world_id)) return false;
    seen.add(item.world_id);
    return true;
  });
};

export const WorldviewManagement: React.FC = () => {
  const [worlds, setWorlds] = useState<World[]>([]);
  const [selectedWorldId, setSelectedWorldId] = useState<string | null>(null);
  const [worldviews, setWorldviews] = useState<Worldview[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newWv, setNewWv] = useState({ name: '', summary: '' });
  const navigate = useNavigate();

  const loadWorlds = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listWorlds();
      const nextWorlds = uniqueWorldsById(res.data || []);
      setWorlds(nextWorlds);
      if (nextWorlds.length > 0 && !selectedWorldId) {
        setSelectedWorldId(nextWorlds[0].world_id);
      }
    } catch (err) {
      console.error('Failed to load worlds', err);
    } finally {
      setLoading(false);
    }
  }, [selectedWorldId]);

  const loadWorldviews = useCallback(async () => {
    if (!selectedWorldId) return;
    setLoading(true);
    try {
      const res = await api.listWorldviews({ world_id: selectedWorldId, page: 1, page_size: 50 });
      setWorldviews(res.data || []);
    } catch (err) {
      console.error('Failed to load worldviews', err);
    } finally {
      setLoading(false);
    }
  }, [selectedWorldId]);

  useEffect(() => {
    loadWorlds();
  }, [loadWorlds]);

  useEffect(() => {
    if (selectedWorldId) {
      loadWorldviews();
    }
  }, [loadWorldviews, selectedWorldId]);

  const handleCreateWorldview = async () => {
    if (!selectedWorldId || !newWv.name) return;
    try {
      await api.createWorldview({
        world_id: selectedWorldId,
        name: newWv.name,
        summary: newWv.summary,
      });
      setCreateModalOpen(false);
      setNewWv({ name: '', summary: '' });
      loadWorldviews();
    } catch (err) {
      console.error('Failed to create worldview', err);
    }
  };

  const handleDeleteWorldview = async (id: string) => {
    if (!window.confirm('确认物理删除该世界观及旗下所有设定？此操作不可恢复。')) return;
    try {
      await api.deleteWorldview({ worldview_id: id, cascade: true });
      loadWorldviews();
    } catch (err) {
      console.error('Failed to delete worldview', err);
    }
  };

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Box>
          <Title order={2}>世界观容器管理</Title>
          <Text size="sm" c="dimmed">管理不同世界的独立世界观容器，每个容器拥有独立的知识库（Lore DB）。</Text>
        </Box>
        <Group>
          <Button leftSection={<IconRefresh size={16} />} variant="light" onClick={loadWorldviews}>刷新</Button>
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={() => navigate(`/workflow/worldview?action=create&world_id=${selectedWorldId}`)}
            disabled={!selectedWorldId}
          >
            创建世界观
          </Button>
        </Group>
      </Group>

      <Paper p="md" withBorder>
        <Group align="flex-end">
          <Select
            label="当前所属世界"
            placeholder="选择一个世界"
            data={worlds.map(w => ({ value: w.world_id, label: `${w.name} (${w.world_id})` }))}
            value={selectedWorldId}
            onChange={setSelectedWorldId}
            style={{ width: 300 }}
          />
        </Group>
      </Paper>

      {loading && worldviews.length === 0 ? (
        <Group justify="center" py="xl"><Loader /></Group>
      ) : (
        <Grid>
          {worldviews.map((wv) => (
            <Grid.Col key={wv.worldview_id} span={{ base: 12, md: 6, lg: 4 }}>
              <Card shadow="sm" padding="lg" radius="md" withBorder>
                <Group justify="space-between" mb="xs">
                  <Text fw={700} size="lg" c="cyan">{wv.name}</Text>
                  <Badge color="green" variant="light">Active</Badge>
                </Group>

                <Text size="sm" c="dimmed" mb="md" h={40} style={{ overflow: 'hidden' }}>
                  {wv.summary || '暂无背景简介...'}
                </Text>

                <Group justify="space-between" mt="md" pt="xs" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                  <Text size="xs" c="dimmed" ff="mono">{wv.worldview_id}</Text>
                  <Group gap="xs">
                    <Tooltip label="管理设定库">
                      <ActionIcon variant="light" color="cyan" onClick={() => navigate(`/lore?worldview_id=${wv.worldview_id}`)}>
                        <IconSettings size={16} />
                      </ActionIcon>
                    </Tooltip>
                    <Tooltip label="修改">
                      <ActionIcon
                        variant="light"
                        color="blue"
                        onClick={() => navigate(`/workflow/worldview?action=update&world_id=${wv.world_id}&id=${wv.worldview_id}&name=${encodeURIComponent(wv.name)}&summary=${encodeURIComponent(wv.summary || '')}`)}
                      >
                        <IconEdit size={16} />
                      </ActionIcon>
                    </Tooltip>
                    <Tooltip label="删除">
                      <ActionIcon variant="light" color="red" onClick={() => handleDeleteWorldview(wv.worldview_id)}>
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Tooltip>
                  </Group>
                </Group>
              </Card>
            </Grid.Col>
          ))}
          {worldviews.length === 0 && !loading && (
            <Grid.Col span={12}>
              <Paper p="xl" withBorder style={{ borderStyle: 'dashed', textAlign: 'center' }}>
                <Text c="dimmed italic">当前世界下暂无世界观容器，请先创建一个。</Text>
              </Paper>
            </Grid.Col>
          )}
        </Grid>
      )}

      <Modal opened={createModalOpen} onClose={() => setCreateModalOpen(false)} title="创建新世界观">
        <Stack gap="sm">
          <TextInput
            label="名称"
            placeholder="例如：赛博长城、万象星际..."
            required
            value={newWv.name}
            onChange={(e) => setNewWv({ ...newWv, name: e.currentTarget.value })}
          />
          <Textarea
            label="背景简介"
            placeholder="简要描述该世界观的核心设定..."
            minRows={3}
            value={newWv.summary}
            onChange={(e) => setNewWv({ ...newWv, summary: e.currentTarget.value })}
          />
          <Group justify="flex-end" mt="md">
            <Button variant="light" onClick={() => setCreateModalOpen(false)}>取消</Button>
            <Button color="cyan" onClick={handleCreateWorldview}>创建</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
};
