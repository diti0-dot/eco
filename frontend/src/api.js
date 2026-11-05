const BASE = "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    ...options,
    headers: { "Content-Type": "application/json" },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const resourceFileUrl = (id, download = false) =>
  `${BASE}/resources/${id}/file${download ? "?download=1" : ""}`;

export const submissionFileUrl = (studentId, resourceId, download = false) =>
  `${BASE}/students/${studentId}/resources/${resourceId}/submission/file${download ? "?download=1" : ""}`;

export const uploadReportFile = async (sjId, docType, file) => {
  const form = new FormData();
  form.append("doc_type", docType);
  form.append("file", file);
  const res = await fetch(`${BASE}/sent-journeys/${sjId}/report-documents`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }
  return res.json();
};

const post = (path, body) => request(path, { method: "POST", body });
const patch = (path, body) => request(path, { method: "PATCH", body });
export const fileUrl = (docId) => `${BASE}/documents/${docId}/file`;

export const api = {
  login: (email) => post("/auth/login", { email }),
  cities: (kind) => request(`/cities?kind=${kind}`),
  search: (originId, destId, date) =>
    request(`/search?origin_id=${originId}&destination_id=${destId}&travel_date=${date}`),
  saveJourney: (body) => post("/journeys", body),
  deleteJourney: (id) => request(`/journeys/${id}`, { method: "DELETE" }),
  studentJourneys: (id) => request(`/students/${id}/journeys`),
  sendJourney: (id) => post(`/journeys/${id}/send`),
  studentSent: (id) => request(`/students/${id}/sent-journeys`),
  todo: (id) => request(`/students/${id}/todo`),
  uploadDoc: (legId, body) => post(`/journey-legs/${legId}/documents`, body),
  uploadFile: async (legId, docType, file) => {
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file);
    const res = await fetch(`${BASE}/journey-legs/${legId}/upload`, { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  },
  submitReport: (sjId, body) => post(`/sent-journeys/${sjId}/final-report`, body),
  studentResources: (id) => request(`/students/${id}/resources`),
  sign: (studentId, resourceId, name) =>
  post(`/students/${studentId}/resources/${resourceId}/sign`, { signed_name: name }),
  uniJourneys: (userId) => request(`/university/${userId}/journey-requests`),
  uniGrants: (userId) => request(`/university/${userId}/grant-requests`),
  review: (sjId, body) => patch(`/sent-journeys/${sjId}/review`, body),
  uploadResource: (userId, body) => post(`/university/${userId}/resources`, body),
  uniResources: (uniId) => request(`/universities/${uniId}/resources`),
  uploadResourceFile: async (userId, { title, type, required, file }) => {
    const form = new FormData();
    form.append("title", title);
    form.append("type", type);
    form.append("required", String(required));
    form.append("file", file);
    const res = await fetch(`${BASE}/university/${userId}/resources/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  },
  allCities: () => request("/cities"),
  providers: (mode) => request(`/providers?mode=${mode}`),
  journey: (id) => request(`/journeys/${id}`),
  updateJourney: (id, body) => request(`/journeys/${id}`, { method: "PUT", body }),
  resubmitReport: (sjId, summary) => post(`/sent-journeys/${sjId}/resubmit`, { summary }),
  uploadReportFile,
  uniTickets: (userId) => request(`/university/${userId}/tickets`),
  ticket: (id) => request(`/tickets/${id}`),
  deleteDocument: (id) => request(`/documents/${id}`, { method: "DELETE" }),
    uploadSubmission: async (studentId, resourceId, file) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(
      `${BASE}/students/${studentId}/resources/${resourceId}/submission`,
      { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  },
    replaceResource: async (userId, resourceId, file) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/university/${userId}/resources/${resourceId}/replace`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Replace failed (${res.status})`);
    }
    return res.json();
  },
  deleteResource: (userId, resourceId) =>
    request(`/university/${userId}/resources/${resourceId}`, { method: "DELETE" }),
};