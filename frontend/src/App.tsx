import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { MainLayout } from './layout/MainLayout';
import { Typography } from '@mui/material';
import { Workflow } from './pages/Workflow';

// Placeholder Pages
const Dashboard = () => <Typography variant="h4">仪表盘 (建设中)</Typography>;
const Drafts = () => <Typography variant="h4">实体草案 (建设中)</Typography>;
const LoreDB = () => <Typography variant="h4">世界观库 (建设中)</Typography>;
const Outlines = () => <Typography variant="h4">小说大纲 (建设中)</Typography>;
const Brain = () => <Typography variant="h4">万象大脑 (建设中)</Typography>;
const Settings = () => <Typography variant="h4">设置 (建设中)</Typography>;

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Workflow />} /> {/* Setting Workflow as the initial page */}
          <Route path="workflow" element={<Workflow />} />
          <Route path="drafts" element={<Drafts />} />
          <Route path="lore" element={<LoreDB />} />
          <Route path="outlines" element={<Outlines />} />
          <Route path="brain" element={<Brain />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
