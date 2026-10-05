import { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { HandoffQueue } from './HandoffQueue';
import { ConversationDetail } from './ConversationDetail';
import './index.css';

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('id');
  });

  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      setSelectedId(params.get('id'));
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const handleSelect = (id: string | null) => {
    setSelectedId(id);
    if (id) {
      window.history.pushState({ id }, '', `?id=${id}`);
    } else {
      window.history.pushState({}, '', window.location.pathname);
    }
  };

  return (
    <div className="app-container">
      <Sidebar onNavigate={(p) => { if (p === 'queue') handleSelect(null); }} />
      {selectedId ? (
        <ConversationDetail id={selectedId} onBack={() => handleSelect(null)} />
      ) : (
        <HandoffQueue onSelect={id => handleSelect(id)} />
      )}
    </div>
  );
}