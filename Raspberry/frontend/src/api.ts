const API_BASE = `http://${window.location.hostname || 'localhost'}:8000/api`;

export async function seekGame() {
  const response = await fetch(`${API_BASE}/game/seek`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

export async function cancelGame() {
  const response = await fetch(`${API_BASE}/game/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}
