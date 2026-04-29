import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MainLayout } from './layout/MainLayout';
import { LoreDB } from './pages/LoreDB';
import { WorldviewVisualizer } from './pages/WorldviewVisualizer';
import { WorldHierarchy } from './pages/WorldHierarchy';
import { WorldviewManagement } from './pages/WorldviewManagement';
import { OutlineChapterWorkflow } from './pages/OutlineChapterWorkflow';
import {
  ChapterWorkflow,
  HierarchyWorkflow,
  NovelWorkflow,
  OutlineWorkflow,
  WorldWorkflow,
  WorldviewWorkflow,
} from './pages/HierarchyWorkflow';
import { MantineProvider } from '@mantine/core';
import '@mantine/core/styles.css';

function App() {
  return (
    <MantineProvider defaultColorScheme="dark">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<Navigate to="/worlds" replace />} />
            <Route path="worlds" element={<WorldHierarchy />} />
            <Route path="worldviews" element={<WorldviewManagement />} />
            <Route path="lore" element={<LoreDB />} />
            <Route path="visualizer" element={<WorldviewVisualizer />} />
            <Route path="novels" element={<OutlineChapterWorkflow />} />
            <Route path="workflow" element={<HierarchyWorkflow />} />
            <Route path="workflow/world" element={<WorldWorkflow />} />
            <Route path="workflow/worldview" element={<WorldviewWorkflow />} />
            <Route path="workflow/novel" element={<NovelWorkflow />} />
            <Route path="workflow/outline" element={<OutlineWorkflow />} />
            <Route path="workflow/chapter" element={<ChapterWorkflow />} />
            <Route path="*" element={<Navigate to="/worlds" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </MantineProvider>
  );
}

export default App;
