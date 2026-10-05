import handoffsFixture from "./fixtures/handoffs.json";
import summaryFixture from "./fixtures/handoffs_summary.json";
import detailFixture from "./fixtures/conversation_detail.json";
import eventsFixture from "./fixtures/conversation_events.json";
import determinismFixture from "./fixtures/conversation_determinism.json";

const USE_FIXTURES = import.meta.env.VITE_USE_FIXTURES === "true";
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const api = {
  getHandoffs: async (status: string = "open") => {
    if (USE_FIXTURES) {
      if (status === "open") return handoffsFixture.filter(h => h.resolved === 0);
      return handoffsFixture;
    }
    const res = await fetch(`${API_URL}/handoffs?status=${status}`);
    return res.json();
  },
  
  getHandoffsSummary: async (date?: string) => {
    if (USE_FIXTURES) return summaryFixture;
    const query = date ? `?date=${encodeURIComponent(date)}` : "";
    const res = await fetch(`${API_URL}/handoffs/summary${query}`);
    return res.json();
  },
  
  resolveHandoff: async (conversation_id: string, resolved_by: string, note: string) => {
    if (USE_FIXTURES) {
      return { status: 200, json: async () => ({ status: "success" }) };
    }
    return fetch(`${API_URL}/handoffs/${conversation_id}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolved_by, note })
    });
  },
  
  getConversation: async (conversation_id: string) => {
    if (USE_FIXTURES) return detailFixture;
    const res = await fetch(`${API_URL}/conversations/${conversation_id}`);
    return res.json();
  },
  
  getConversationEvents: async (conversation_id: string) => {
    if (USE_FIXTURES) return eventsFixture;
    const res = await fetch(`${API_URL}/conversations/${conversation_id}/events`);
    return res.json();
  },
  
  getConversationDeterminism: async (conversation_id: string) => {
    if (USE_FIXTURES) return determinismFixture;
    const res = await fetch(`${API_URL}/conversations/${conversation_id}/determinism`);
    return res.json();
  }
};
