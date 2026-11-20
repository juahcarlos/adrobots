import { Link, Route, Routes } from "react-router-dom";

import CreatePage from "./pages/CreatePage";
import EditorPage from "./pages/EditorPage";

export default function App() {
  return (
    <div className="layout">
      <nav className="nav">
        <Link to="/">Создать кампанию</Link>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<CreatePage />} />
          <Route path="/campaigns/:keitaroId" element={<EditorPage />} />
        </Routes>
      </main>
    </div>
  );
}