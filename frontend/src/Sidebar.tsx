export function Sidebar({ onNavigate }: { onNavigate: (page: string) => void }) {
  return (
    <div className="sidebar" role="navigation" aria-label="Main Navigation">
      <button className="sidebar-dot" title="Dashboard" aria-label="Dashboard"></button>
      <button className="sidebar-dot" title="Patients" aria-label="Patients"></button>
      <button className="sidebar-dot active" title="Handoff Queue" aria-label="Handoff Queue" onClick={() => onNavigate('queue')}></button>
      <button className="sidebar-dot" title="Metrics" aria-label="Metrics"></button>
      <button className="sidebar-dot" title="Settings" aria-label="Settings"></button>
    </div>
  );
}