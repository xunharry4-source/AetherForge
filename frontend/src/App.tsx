import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MainLayout } from './layout/MainLayout';
import { LoreDB } from './pages/LoreDB';
import { WorldviewVisualizer } from './pages/WorldviewVisualizer';
import { WorldHierarchy } from './pages/WorldHierarchy';
import { OutlineChapterWorkflow } from './pages/OutlineChapterWorkflow';
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
            <Route path="lore" element={<LoreDB />} />
            <Route path="visualizer" element={<WorldviewVisualizer />} />
            <Route path="outlines" element={<OutlineChapterWorkflow />} />
            <Route path="*" element={<Navigate to="/worlds" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </MantineProvider>
  );
}

export default App;
