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
  Select,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import {
  IconArrowLeft,
  IconEdit,
  IconFileText,
  IconPlus,
  IconRefresh,
  IconTrash,
} from '@tabler/icons-react';
import { api } from '../api/client';

type Novel = {
  novel_id: string;
  world_id: string;
  name: string;
};

type Outline = {
  outline_id: string;
  novel_id?: string;
  world_id?: string;
  worldview_id?: string;
  name?: string;
  title?: string;
};

type Chapter = {
  id: string;
  scene_id?: string;
  prose_id?: string;
  type?: string;
  name?: string;
  title?: string;
  content?: string;
  outline_id?: string;
  novel_id?: string;
  worldview_id?: string;
  world_id?: string;
  updated_at?: string;
  created_at?: string;
};

const pageSize = 20;

export const NovelChapterManagement: React.FC = () => {
  const { novelId = '' } = useParams();
  const navigate = useNavigate();
  const [novel, setNovel] = useState<Novel | null>(null);
  const [outlines, setOutlines] = useState<Outline[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedOutlineId, setSelectedOutlineId] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [deleteChapter, setDeleteChapter] = useState<Chapter | null>(null);

  const selectedOutline = useMemo(
    () => outlines.find((outline) => outline.outline_id === selectedOutlineId),
    [outlines, selectedOutlineId],
  );
  const hasNextPage = chapters.length === pageSize;
  const paginationTotal = Math.max(page + (hasNextPage ? 1 : 0), 1);

  const loadData = useCallback(async () => {
    if (!novelId) return;
    setLoading(true);
    setError(null);
    try {
      const novelRes = await api.getNovel({ novel_id: novelId });
      const nextNovel = novelRes.data.novel as Novel;
      const outlineRes = await api.listOutlines({ novel_id: novelId, page: 1, page_size: 100 });
      const nextOutlines = ((outlineRes.data as Outline[]) || []).filter((outline) => outline.novel_id === novelId);
      const loreRes = await api.listLore({
        world_id: nextNovel.world_id,
        novel_id: novelId,
        outline_id: selectedOutlineId || undefined,
        page,
        page_size: pageSize,
      });
      const nextChapters = ((loreRes.data as Chapter[]) || []).filter((chapter) => chapter.type === 'prose' && chapter.novel_id === novelId);
      setNovel(nextNovel);
      setOutlines(nextOutlines);
      setChapters(nextChapters);
    } catch (err: any) {
      setError(err?.response?.data?.error || err?.message || String(err));
      setChapters([]);
    } finally {
      setLoading(false);
    }
  }, [novelId, page, selectedOutlineId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const openCreateWorkflow = () => {
    const targetOutline = selectedOutline || outlines[0];
    if (!novel || !targetOutline) return;
    const params = new URLSearchParams({
      action: 'create',
      world_id: novel.world_id,
      novel_id: novel.novel_id,
      outline_id: targetOutline.outline_id,
    });
    if (targetOutline.worldview_id) params.set('worldview_id', targetOutline.worldview_id);
    navigate(`/workflow/chapter?${params.toString()}`);
  };

  const openUpdateWorkflow = (chapter: Chapter) => {
    if (!novel) return;
    const chapterId = chapter.id || chapter.scene_id || chapter.prose_id || '';
    const outlineId = chapter.outline_id || selectedOutlineId;
    const outline = outlines.find((item) => item.outline_id === outlineId);
    const params = new URLSearchParams({
      action: 'update',
      world_id: chapter.world_id || novel.world_id,
      novel_id: novel.novel_id,
      outline_id: outlineId,
      id: chapterId,
      name: chapter.name || chapter.title || '',
      content: chapter.content || '',
    });
    if (chapter.worldview_id || outline?.worldview_id) {
      params.set('worldview_id', chapter.worldview_id || outline?.worldview_id || '');
    }
    navigate(`/workflow/chapter?${params.toString()}`);
  };

  const confirmDelete = async () => {
    if (!deleteChapter || !novel) return;
    const chapterId = deleteChapter.id || deleteChapter.scene_id || deleteChapter.prose_id || '';
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await api.deleteArchiveItem({
        id: chapterId,
        type: 'prose',
        world_id: deleteChapter.world_id || novel.world_id,
        novel_id: novel.novel_id,
        outline_id: deleteChapter.outline_id,
      });
      const verifyRes = await api.listLore({
        world_id: novel.world_id,
        novel_id: novel.novel_id,
        outline_id: deleteChapter.outline_id,
        page: 1,
        page_size: 100,
      });
      const remaining = ((verifyRes.data as Chapter[]) || []).filter((chapter) => (chapter.id || chapter.scene_id || chapter.prose_id) === chapterId);
      if (remaining.length > 0) {
        throw new Error(`删除后仍能查询到章节: ${chapterId}`);
      }
      setSuccess('章节已删除，并完成真实接口回查。');
      setDeleteChapter(null);
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
            <IconFileText size={24} />
            <Title order={2}>章节管理</Title>
            <Badge variant="light">{novelId}</Badge>
          </Group>
          <Text size="sm" c="dimmed">当前小说：{title}。新增和修改会跳转到章节工作流页面。</Text>
        </Box>
        <Group gap="xs">
          <Button variant="light" leftSection={<IconArrowLeft size={16} />} onClick={() => navigate('/novels')}>返回小说列表</Button>
          <Button variant="light" leftSection={<IconRefresh size={16} />} loading={loading} onClick={loadData}>刷新</Button>
          <Button leftSection={<IconPlus size={16} />} onClick={openCreateWorkflow} disabled={!novel || outlines.length === 0}>新增章节</Button>
        </Group>
      </Group>

      {error && <Alert color="red" title="真实接口请求失败">{error}</Alert>}
      {success && <Alert color="green">{success}</Alert>}

      <Paper p="md" withBorder>
        <Group justify="space-between" align="flex-end">
          <Select
            label="大纲筛选"
            data={outlines.map((outline) => ({ value: outline.outline_id, label: `${outline.name || outline.title || outline.outline_id} (${outline.outline_id})` }))}
            value={selectedOutlineId || null}
            onChange={(value) => { setSelectedOutlineId(value || ''); setPage(1); }}
            clearable
            searchable
            placeholder="全部大纲"
            style={{ minWidth: 420 }}
          />
          <Group gap="xs">
            {loading && <Loader size="sm" />}
            <Badge variant="light">第 {page} 页</Badge>
            <Badge variant="light">本页 {chapters.length} 条</Badge>
          </Group>
        </Group>
        {!selectedOutlineId && <Text size="xs" c="dimmed" mt="xs">未选择大纲时表格显示全部章节；新增章节会默认使用当前小说下第一条大纲。</Text>}
      </Paper>

      <Paper p="sm" withBorder style={{ overflow: 'hidden', flex: 1 }}>
        <Group justify="flex-end" mb="sm">
          <Pagination value={page} onChange={setPage} total={paginationTotal} />
        </Group>
        <ScrollArea h="calc(100vh - 310px)">
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>章节 ID</Table.Th>
                <Table.Th>标题</Table.Th>
                <Table.Th>所属大纲</Table.Th>
                <Table.Th>正文摘要</Table.Th>
                <Table.Th>更新时间</Table.Th>
                <Table.Th>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {chapters.map((chapter) => {
                const chapterId = chapter.id || chapter.scene_id || chapter.prose_id || '';
                return (
                  <Table.Tr key={chapterId}>
                    <Table.Td><Text size="xs" truncate maw={180}>{chapterId}</Text></Table.Td>
                    <Table.Td><Text fw={700}>{chapter.name || chapter.title || ''}</Text></Table.Td>
                    <Table.Td><Text size="xs" truncate maw={170}>{chapter.outline_id || ''}</Text></Table.Td>
                    <Table.Td><Text size="sm" truncate maw={520}>{chapter.content || ''}</Text></Table.Td>
                    <Table.Td><Text size="xs" c="dimmed">{chapter.updated_at || chapter.created_at || ''}</Text></Table.Td>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <Button size="xs" variant="light" leftSection={<IconEdit size={14} />} onClick={() => openUpdateWorkflow(chapter)}>修改</Button>
                        <Button size="xs" color="red" variant="light" leftSection={<IconTrash size={14} />} onClick={() => setDeleteChapter(chapter)}>删除</Button>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
              {chapters.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={6}>
                    <Text ta="center" c="dimmed" py="xl">当前筛选下暂无章节。</Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Paper>

      <Modal opened={Boolean(deleteChapter)} onClose={() => setDeleteChapter(null)} title="删除章节" size="md">
        <Stack gap="sm">
          <Alert color="red">删除会移除该章节正文记录。</Alert>
          <Text fw={700}>{deleteChapter?.name || deleteChapter?.title}</Text>
          <Text size="xs" c="dimmed">{deleteChapter?.id || deleteChapter?.scene_id || deleteChapter?.prose_id}</Text>
          <Group justify="flex-end">
            <Button variant="light" onClick={() => setDeleteChapter(null)}>取消</Button>
            <Button color="red" loading={saving} onClick={confirmDelete}>确认删除</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
};
