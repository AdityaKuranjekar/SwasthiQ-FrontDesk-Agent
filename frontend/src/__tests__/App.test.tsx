import App from '../App';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { HandoffQueue } from '../HandoffQueue';
import { ConversationDetail } from '../ConversationDetail';

// Mock the API responses
vi.mock('../api', () => ({
  api: {
    getHandoffs: vi.fn().mockResolvedValue([
      { conversation_id: "cv_1", caller_said: "clinical test", escalation_reason: "clinical_urgent", created_at: "2026-10-04T00:00:00Z", resolved: 0 },
      { conversation_id: "cv_2", caller_said: "auth test", escalation_reason: "not_authorised", created_at: "2026-10-04T00:00:00Z", resolved: 0 },
      { conversation_id: "cv_3", caller_said: "ambiguous test", escalation_reason: "ambiguous_patient", created_at: "2026-10-04T00:00:00Z", resolved: 0 },
      { conversation_id: "cv_4", caller_said: "medical test", escalation_reason: "medical_advice", created_at: "2026-10-04T00:00:00Z", resolved: 0 },
      { conversation_id: "cv_5", caller_said: "scope test", escalation_reason: "out_of_scope", created_at: "2026-10-04T00:00:00Z", resolved: 0 },
    ]),
    // The API's real field names.
    getHandoffsSummary: vi.fn().mockResolvedValue({
      total_conversations: 10, completed_by_agent: 5, escalated: 5, still_open: 5, urgent_unresolved: 1
    }),
    resolveHandoff: vi.fn().mockResolvedValue({ status: 409 }),
    getConversation: vi.fn().mockResolvedValue({
      conversation_id: "cv_1", date: "2026-10-04", time: "10:00", intent: "book",
      terminal_state: "escalated", escalation_reason: "clinical_urgent",
      patient_id: "pt_1", appointment_id: null, tool_call_count: 1, turns: 2, tokens: 100, latency_ms: 1000
    }),
    getConversationEvents: vi.fn().mockResolvedValue([]),
    getConversationDeterminism: vi.fn().mockResolvedValue([])
  }
}));



describe('Frontend Tests', () => {
  it('renders HandoffQueue and checks reason tags', async () => {
    render(<HandoffQueue onSelect={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Handoff Queue')).toBeTruthy();
    });
    // Check reason tags
    expect(screen.getByText('CLINICAL')).toBeTruthy();
    expect(screen.getByText('NOT AUTHORISED')).toBeTruthy();
    expect(screen.getByText('AMBIGUOUS PATIENT')).toBeTruthy();
    expect(screen.getByText('MEDICAL ADVICE')).toBeTruthy();
    expect(screen.getByText('OUT OF SCOPE')).toBeTruthy();
  });

  it('shows already resolved on 409', async () => {
    render(<HandoffQueue onSelect={() => {}} />);
    await waitFor(() => screen.getByText('cv_1'));
    
    // Click resolve for cv_1
    const resolveBtns = screen.getAllByText('Resolve');
    fireEvent.click(resolveBtns[0]);
    
    // Fill form
    const byInput = screen.getByPlaceholderText('By');
    fireEvent.change(byInput, { target: { value: 'User' } });
    
    const saveBtn = screen.getByText('Save');
    fireEvent.click(saveBtn);
    
    await waitFor(() => {
      expect(screen.getByText('already resolved')).toBeTruthy();
    });
  });

  it('renders ConversationDetail and shows abandoned banner', async () => {
    render(<ConversationDetail id="cv_1" />);
    await waitFor(() => {
      expect(screen.getByText('Conversation cv_1')).toBeTruthy();
    });
    
    // Banner test
    expect(screen.getByText('Booking flow abandoned. No appointment was created.')).toBeTruthy();
  });

  it('banner wording follows the conversation intent', async () => {
    const { api } = await import('../api');
    const base = {
      conversation_id: "cv_x", date: "2026-10-04", time: "10:00", terminal_state: "escalated",
      escalation_reason: "not_authorised", patient_id: null, appointment_id: null,
      tool_call_count: 1, turns: 2, tokens: 0, latency_ms: 10,
    };
    const cases: Array<[string | null, string]> = [
      ["cancel", "Cancellation flow abandoned. No appointment was changed."],
      ["reschedule", "Booking flow abandoned. No appointment was created."],
      [null, "Handed off to a human. No appointment was created or changed."],
    ];
    for (const [intent, text] of cases) {
      (api.getConversation as any).mockResolvedValueOnce({ ...base, intent });
      const { unmount } = render(<ConversationDetail id="cv_x" />);
      await waitFor(() => expect(screen.getByText(text)).toBeTruthy());
      unmount();
    }
  });

  it('header shows one date and time like the PS, without a scripted suffix', async () => {
    const { api } = await import('../api');
    (api.getConversation as any).mockResolvedValueOnce({
      conversation_id: "cv_z", date: "2026-10-01", time: "10:00", intent: "book",
      terminal_state: "escalated", escalation_reason: "clinical_urgent", patient_id: null, appointment_id: null,
      tool_call_count: 1, turns: 2, tokens: 0, latency_ms: 10,
    });
    (api.getConversationEvents as any).mockResolvedValueOnce([
      { event_type: "caller", position: 0, timestamp: "2026-10-05T06:10:00+00:00", content: "hello" },
    ]);
    render(<ConversationDetail id="cv_z" />);
    // 06:10 UTC is 11:40 in Kolkata.
    await waitFor(() => expect(screen.getByText(/01 Oct 2026, 11:40/)).toBeTruthy());
    expect(screen.queryByText(/Scripted/)).toBeNull();
  });

  it('shows no banner when an appointment was booked', async () => {
    const { api } = await import('../api');
    (api.getConversation as any).mockResolvedValueOnce({
      conversation_id: "cv_y", date: "2026-10-04", time: "10:00", intent: "book",
      terminal_state: "booked", escalation_reason: null, patient_id: "pt_1", appointment_id: "ap_0031",
      tool_call_count: 3, turns: 3, tokens: 0, latency_ms: 10,
    });
    render(<ConversationDetail id="cv_y" />);
    await waitFor(() => expect(screen.getByText('Conversation cv_y')).toBeTruthy());
    expect(screen.queryByText(/flow abandoned/)).toBeNull();
    expect(screen.queryByText(/Handed off to a human/)).toBeNull();
  });
});



  it('navigates back to queue via sidebar', async () => {
    render(<App />);
    await waitFor(() => screen.getByText('cv_1'));
    
    // Click row to go to detail
    fireEvent.click(screen.getByText('cv_1'));
    await waitFor(() => screen.getByText('Conversation cv_1'));
    
    // Click sidebar handoff dot
    const dots = screen.getAllByTitle('Handoff Queue');
    fireEvent.click(dots[0]);
    
    await waitFor(() => screen.getByText('Handoff Queue'));
  });