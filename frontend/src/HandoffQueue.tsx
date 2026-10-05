import { useState, useEffect } from 'react';
import { api } from './api';

export function HandoffQueue({ onSelect }: { onSelect: (id: string) => void }) {
  const [handoffs, setHandoffs] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<string | null>(null);
  const [resolveForm, setResolveForm] = useState<{ id: string, by: string, note: string } | null>(null);
  const [errorMap, setErrorMap] = useState<Record<string, string>>({});

  useEffect(() => {
    const load = async () => {
      try {
        const [h, s] = await Promise.all([
          api.getHandoffs("open"),
          api.getHandoffsSummary()
        ]);
        setHandoffs(h);
        // Map the API's field names onto the names the screen uses.
        setSummary(s && {
          total: s.total_conversations ?? 0,
          completed: s.completed_by_agent ?? 0,
          escalated: s.escalated ?? 0,
          open: s.still_open ?? 0,
          urgent: s.urgent_unresolved ?? 0,
        });
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleResolve = async (e: React.FormEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!resolveForm || !resolveForm.by) return;
    
    setResolving(id);
    try {
      const res = await api.resolveHandoff(id, resolveForm.by, resolveForm.note);
      if (res.status === 409) {
        setErrorMap(prev => ({ ...prev, [id]: "already resolved" }));
      } else if ((res as any).ok || res.status === 200) {
        setHandoffs(prev => prev.filter(h => h.conversation_id !== id));
        setResolveForm(null);
      }
    } catch (err) {
      setErrorMap(prev => ({ ...prev, [id]: "error resolving" }));
    } finally {
      setResolving(null);
    }
  };

  if (loading) return <div className="main-content">Loading...</div>;

  const getReasonTag = (reason: string) => {
    const map: any = {
      clinical_urgent: { label: 'CLINICAL', className: 'badge badge-red' },
      not_authorised: { label: 'NOT AUTHORISED', className: 'badge badge-yellow' },
      ambiguous_patient: { label: 'AMBIGUOUS PATIENT', className: 'badge badge-yellow' },
      medical_advice: { label: 'MEDICAL ADVICE', className: 'badge badge-red' },
      out_of_scope: { label: 'OUT OF SCOPE', className: 'badge badge-blue' }
    };
    const t = map[reason] || { label: reason?.toUpperCase(), className: 'badge badge-blue' };
    return <span className={t.className}>{t.label}</span>;
  };

  return (
    <div className="main-content">
      <div className="header">
        <div>
          <h1>Handoff Queue</h1>
          <p>Sunrise Clinic, Dehradun  conversations the agent escalated</p>
        </div>
        <div className="badge badge-blue">{summary?.open || 0} OPEN</div>
      </div>
      
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-card-title">Conversations</div>
          <div className="stat-card-value">{summary?.total || 0}</div>
          <div className="stat-card-sub">today</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-title">Completed by agent</div>
          <div className="stat-card-value">{summary?.completed || 0}</div>
          <div className="stat-card-sub">{summary?.total ? Math.round((summary.completed/summary.total)*100) : 0}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-title">Escalated</div>
          <div className="stat-card-value">{summary?.escalated || 0}</div>
          <div className="stat-card-sub blue">{summary?.open || 0} still open</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-title">Urgent</div>
          <div className="stat-card-value">{summary?.urgent || 0}</div>
          <div className="stat-card-sub red">clinical, unresolved</div>
        </div>
      </div>

      <div className="table-container">
        <div className="table-header">Open handoffs</div>
        <table>
          <thead>
            <tr>
              <th>Conversation</th>
              <th>Caller Said</th>
              <th>Reason</th>
              <th>Time</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {handoffs.length === 0 && <tr><td colSpan={5}>No open handoffs</td></tr>}
            {handoffs.map(h => {
              const time = new Date(h.created_at).toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false });
              return (
                <tr key={h.conversation_id} className="clickable" onClick={() => onSelect(h.conversation_id)}>
                  <td>{h.conversation_id}</td>
                  <td>"{h.caller_said}"</td>
                  <td>{getReasonTag(h.escalation_reason)}</td>
                  <td>{time}</td>
                  <td onClick={e => e.stopPropagation()}>
                    {resolveForm?.id === h.conversation_id ? (
                      <form className="resolve-form" onSubmit={(e) => handleResolve(e, h.conversation_id)}>
                        <input className="resolve-input" placeholder="By" value={resolveForm?.by || ''} onChange={e => setResolveForm(prev => prev ? {...prev, by: e.target.value} : null)} />
                        <input className="resolve-input" placeholder="Note" value={resolveForm?.note || ''} onChange={e => setResolveForm(prev => prev ? {...prev, note: e.target.value} : null)} />
                        <button type="submit" className="btn btn-primary" disabled={resolving === h.conversation_id}>Save</button>
                        <button type="button" className="btn btn-outline" onClick={() => setResolveForm(null)}>Cancel</button>
                      </form>
                    ) : (
                      <button className="btn btn-outline" onClick={() => setResolveForm({id: h.conversation_id, by: '', note: ''})}>Resolve</button>
                    )}
                    {errorMap[h.conversation_id] && <div className="resolve-error">{errorMap[h.conversation_id]}</div>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

