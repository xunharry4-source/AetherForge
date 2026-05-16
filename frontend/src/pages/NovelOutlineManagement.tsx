import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Modal,
  Pagination,
  Paper,
  ScrollArea,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import {
  IconArrowLeft,
  IconEdit,
  IconListTree,
  IconPlus,
  IconRefresh,
  IconTrash,
} from '@tabler/icons-react';
import { api } from '../api/client';

type Novel = {
  novel_id: string;
  world_id: string;
  name: string;
  summary?: string;
};

type Outline = {
  outline_id: string;
  id?: string;
  novel_id?: string;
  world_id?: string;
  worldview_id?: string;
  name?: string;
  title?: string;
  summary?: string;
  updated_at?: string;
  created_at?: string;
};

const pageSize = 20;

export const NovelOutlineManagement: React.FC = () => {
  const { novelId = '' } = useParams();
  const navigate = useNavigate();
  const [novel, setNovel] = useState<Novel | null>(null);
  const [outlines, setOutlines] = useState<Outline[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [deleteOutline, setDeleteOutline] = useState<Outline | null>(null);

  const hasNextPage = outlines.length === pageSize;
  const paginationTotal = Math.max(page + (hasNextPage ? 1 : 0), 1);

  const loadData = useCallback(async () => {
    if (!novelId) return;
    setLoading(true);
    setError(null);
    try {
      const [novelRes, outlineRes] = await Promise.all([
        api.getNovel({ novel_id: novelId }),
        api.listOutlines({ novel_id: novelId, page, page_size: pageSize }),
      ]);
      const nextNovel = novelRes.data.novel as Novel;
      const nextOutlines = ((outlineRes.data as Outline[]) || []).filter((outline) => outline.novel_id === novelId);
      setNovel(nextNovel);
      setOutlines(nextOutlines);
    } catch (err: any) {
      setError(err?.response?.data?.error || err?.message || String(err));
      setOutlines([]);
    } finally {
      setLoading(false);
    }
  }, [novelId, page]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const openCreateWorkflow = () => {
    if (!novel) return;
    const params = new URLSearchParams({
      action: 'create',
      world_id: novel.world_id,
      novel_id: novel.novel_id,
    });
    navigate(`/workflow/outline?${params.toString()}`);
  };

  const openUpdateWorkflow = (outline: Outline) => {
    if (!novel) return;
    const outlineId = outline.outline_id || outline.id || '';
    const params = new URLSearchParams({
      action: 'update',
      world_id: outline.world_id || novel.world_id,
      novel_id: novel.novel_id,
      id: outlineId,
      name: outline.name || outline.title || '',
      summary: outline.summary || '',
    });
    if (outline.worldview_id) params.set('worldview_id', outline.worldview_id);
    navigate(`/workflow/outline?${params.toString()}`);
  };

  const confirmDelete = async () => {
    if (!deleteOutline) return;
    const outlineId = deleteOutline.outline_id || deleteOutline.id || '';
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await api.deleteArchiveItem({ id: outlineId, type: 'outline', novel_id: novelId });
      const verifyRes = await api.listOutlines({ novel_id: novelId, outline_id: outlineId, page: 1, page_size: 10 });
      const remaining = ((verifyRes.data as Outline[]) || []).filter((outline) => (outline.outline_id || outline.id) === outlineId);
      if (remaining.length > 0) {
        throw new Error(`删除后仍能查询到大纲: ${outlineId}`);
      }
      setSuccess('大纲已删除，并完成真实接口回查。');
      setDeleteOutline(null);
      await loadData();
    } catch (err: any) {
      setError(err?.response?.data?.error || err?.message || String(err));
    } finally {
      setSaving(false);
    }
  };

  const title = useMemo(() => novel?.name || novelId, [novel?.name, novelId]);

  return (
    <Stack gap="md" style={{ height: 'calc(100vh - 96px)' }}>
      <Group justify="space-between" align="flex-start">
        <Box>
          <Group gap="xs">
            <IconListTree size={24} />
            <Title order={2}>大纲管理</Title>
            <Badge variant="light">{novelId}</Badge>
          </Group>
          <Text size="sm" c="dimmed">当前小说：{title}。新增和修改会跳转到大纲工作流页面。</Text>
        </Box>
        <Group gap="xs">
          <Button variant="light" leftSection={<IconArrowLeft size={16} />} onClick={() => navigate('/novels')}>返回小说列表</Button>
          <Button variant="light" leftSection={<IconRefresh size={16} />} loading={loading} onClick={loadData}>刷新</Button>
          <Button leftSection={<IconPlus size={16} />} onClick={openCreateWorkflow} disabled={!novel}>新增大纲</Button>
        </Group>
      </Group>

      {error && <Alert color="red" title="真实接口请求失败">{error}</Alert>}
      {success && <Alert color="green">{success}</Alert>}

      <Paper p="sm" withBorder style={{ overflow: 'hidden', flex: 1 }}>
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            {loading && <Loader size="sm" />}
            <Badge variant="light">第 {page} 页</Badge>
            <Badge variant="light">本页 {outlines.length} 条</Badge>
          </Group>
          <Pagination value={page} onChange={setPage} total={paginationTotal} />
        </Group>
        <ScrollArea h="calc(100vh - 245px)">
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>大纲 ID</Table.Th>
                <Table.Th>名称</Table.Th>
                <Table.Th>摘要</Table.Th>
                <Table.Th>世界观</Table.Th>
                <Table.Th>更新时间</Table.Th>
                <Table.Th>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {outlines.map((outline) => {
                const outlineId = outline.outline_id || outline.id || '';
                return (
                  <Table.Tr key={outlineId}>
                    <Table.Td><Text size="xs" truncate maw={180}>{outlineId}</Text></Table.Td>
                    <Table.Td><Text fw={700}>{outline.name || outline.title || ''}</Text></Table.Td>
                    <Table.Td><Text size="sm" truncate maw={520}>{outline.summary || ''}</Text></Table.Td>
                    <Table.Td><Text size="xs" truncate maw={180}>{outline.worldview_id || ''}</Text></Table.Td>
                    <Table.Td><Text size="xs" c="dimmed">{outline.updated_at || outline.created_at || ''}</Text></Table.Td>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <Button size="xs" variant="light" leftSection={<IconEdit size={14} />} onClick={() => openUpdateWorkflow(outline)}>修改</Button>
                        <Button size="xs" color="red" variant="light" leftSection={<IconTrash size={14} />} onClick={() => setDeleteOutline(outline)}>删除</Button>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
              {outlines.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={6}>
                    <Text ta="center" c="dimmed" py="xl">当前小说下暂无大纲。</Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Paper>

      <Modal opened={Boolean(deleteOutline)} onClose={() => setDeleteOutline(null)} title="删除大纲" size="md">
        <Stack gap="sm">
          <Alert color="red">删除会移除该大纲记录；如果章节仍引用该大纲，请先确认影响范围。</Alert>
          <Text fw={700}>{deleteOutline?.name || deleteOutline?.title}</Text>
          <Text size="xs" c="dimmed">{deleteOutline?.outline_id || deleteOutline?.id}</Text>
          <Group justify="flex-end">
            <Button variant="light" onClick={() => setDeleteOutline(null)}>取消</Button>
            <Button color="red" loading={saving} onClick={confirmDelete}>确认删除</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
};
