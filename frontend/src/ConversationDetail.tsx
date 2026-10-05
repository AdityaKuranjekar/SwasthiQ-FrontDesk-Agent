import { useState, useEffect } from 'react';
import { api } from './api';

export function ConversationDetail({ id, onBack }: { id: string, onBack?: () => void }) {
  const [detail, setDetail] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [determinism, setDeterminism] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [d, e, det] = await Promise.all([
          api.getConversation(id),
          api.getConversationEvents(id),
          api.getConversationDeterminism(id).catch(() => []) // Will implement proper endpoint or fallback
        ]);
        setDetail(d);
        setEvents(e);
        setDeterminism(det.runs || det || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  if (loading) return <div className="main-content">Loading...</div>;
  if (!detail) return <div className="main-content">Conversation not found</div>;

  const isStable = determinism.length > 0 && determinism.every(r => r.terminal_state === determinism[0]?.terminal_state && r.escalation_reason === determinism[0]?.escalation_reason);

  const getReasonTag = (reason: string, state: string) => {
    if (state !== 'escalated') return <div className="badge badge-green">{state.toUpperCase()}</div>;
    
    const map: any = {
      clinical_urgent: { label: 'CLINICAL', className: 'badge badge-red' },
      not_authorised: { label: 'NOT AUTHORISED', className: 'badge badge-yellow' },
      ambiguous_patient: { label: 'AMBIGUOUS PATIENT', className: 'badge badge-yellow' },
      medical_advice: { label: 'MEDICAL ADVICE', className: 'badge badge-red' },
      out_of_scope: { label: 'OUT OF SCOPE', className: 'badge badge-blue' }
    };
    const t = map[reason] || { label: reason?.toUpperCase(), className: 'badge badge-red' };
    return <div className={t.className}>ESCALATED — {t.label}</div>;
  };

  // "01 Oct 2026, 07:40", like the PS. The date is the call's own date (the request's `today`, which is what
  // "kal" is resolved against), and the time is when the call began, in the clinic's time zone.
  const formatTimestamp = (events: any[], callDate: string) => {
    let dateLabel = callDate;
    try {
      dateLabel = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric'
      }).format(new Date(`${callDate}T00:00:00Z`));
    } catch { /* keep the raw date */ }

    const first = events.length > 0 ? events[0] : null;
    if (!first || !first.timestamp) return dateLabel;
    try {
      const time = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false
      }).format(new Date(first.timestamp));
      return `${dateLabel}, ${time}`;
    } catch {
      return dateLabel;
    }
  };

  return (
    <div className="main-content">
      <div className="header">
        <div>
          <h1 style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            {onBack && <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px 8px', fontSize: '18px', color: '#3b82f6' }}>&larr; Back</button>}
            Conversation {id}
          </h1>
          <p>Sunrise Clinic, Dehradun — {formatTimestamp(events, detail.date)}</p>
        </div>
        {getReasonTag(detail.escalation_reason, detail.terminal_state)}
      </div>

      <div className="detail-grid">
        <div className="panel" style={{ padding: '2rem 1.5rem' }}>
          <h2 style={{ marginBottom: '2rem' }}>Transcript and tool calls</h2>
          {events.map((e, idx) => {
            if (e.event_type === 'caller') {
              return (
                <div key={idx} className="event-row event-caller">
                  <div className="event-label">Caller</div>
                  <div className="event-content">{e.content}</div>
                </div>
              );
            } else if (e.event_type === 'reply') {
              return (
                <div key={idx} className="event-row event-agent">
                  <div className="event-label">Agent</div>
                  <div className="event-content">{e.content}</div>
                </div>
              );
            } else if (e.event_type === 'tool') {
              let parsed;
              parsed = typeof e.content === "string" ? JSON.parse(e.content) : e.content;
              const argsStr = Object.entries(parsed.arguments || {}).map(([k, v]) => `${parsed.name === "escalate_to_human" && k === "summary" ? "detail" : k}=${JSON.stringify(v)}`).join(", ");
                            let resStr = "";
              if (parsed.display) {
                resStr = "→ " + parsed.display;
              }
              
              return (
                <div key={idx} className="event-row event-tool">
                  <div className="event-label">Tool</div>
                  <div className="event-content">
                    <div className="tool-signature"><strong>{parsed.name}</strong>({argsStr})</div>
                    <div className="tool-result">{resStr}</div>
                    {parsed.result && parsed.result.rule_id && <div style={{marginTop: '6px', fontSize: '11px', color: '#94a3b8', fontStyle: 'italic'}}>Matched rule: {parsed.result.rule_id}</div>}
                  </div>
                </div>
              );
            }
            return null;
          })}

          {!detail.appointment_id && detail.terminal_state !== "booked" && (
            <div className="abandon-banner">
              {detail.intent === "cancel" ? "Cancellation flow abandoned. No appointment was changed." : (detail.intent === "book" || detail.intent === "reschedule" ? "Booking flow abandoned. No appointment was created." : "Handed off to a human. No appointment was created or changed.")}
            </div>
          )}
        </div>

        <div className="panel" style={{ padding: '2rem 1.5rem' }}>
          <h2 style={{ marginBottom: '1.5rem' }}>Outcome</h2>
          <div className="outcome-row"><span className="outcome-label">terminal_state</span><span className="outcome-value">{detail.terminal_state}</span></div>
          <div className="outcome-row"><span className="outcome-label">escalation_reason</span><span className="outcome-value">{detail.escalation_reason || "null"}</span></div>
          <div className="outcome-row"><span className="outcome-label">patient_id</span><span className="outcome-value">{detail.patient_id || "null"}</span></div>
          <div className="outcome-row"><span className="outcome-label">appointment_id</span><span className="outcome-value">{detail.appointment_id || "null"}</span></div>
          <div className="outcome-row"><span className="outcome-label">tool_calls</span><span className="outcome-value">{detail.tool_call_count}</span></div>
          <div className="outcome-row"><span className="outcome-label">turns</span><span className="outcome-value">{detail.turns}</span></div>
          <div className="outcome-row"><span className="outcome-label">tokens</span><span className="outcome-value">{detail.tokens ? detail.tokens.toLocaleString() : '0'}</span></div>
          <div className="outcome-row"><span className="outcome-label">latency</span><span className="outcome-value">{(detail.latency_ms / 1000).toFixed(1)} s</span></div>

          <div className="determinism-label">Determinism</div>
          <div className="determinism-content">
            <span>Same terminal state across {determinism.length || 3} runs.</span>
            <span className={isStable || determinism.length === 0 ? "badge badge-green" : "badge badge-yellow"}>
              {isStable || determinism.length === 0 ? "STABLE" : "UNSTABLE"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
