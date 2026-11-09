import React, { useEffect, useState } from "react";

export default function PropertyManagerDashboard({ apiRequest, setError, setSuccess }) {
  const [properties, setProperties] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [dashboard, setDashboard] = useState(null);
  const [form, setForm] = useState({ record_type: "MAINTENANCE", description: "", amount: "", currency: "USD" });
  const [maintenanceFile, setMaintenanceFile] = useState(null);
  const [saving, setSaving] = useState(false);

  const loadProperties = async () => {
    const rows = await apiRequest("/property-management/properties");
    setProperties(rows);
    if (!selectedId && rows.length) setSelectedId(String(rows[0].id));
  };
  const loadRecords = async (id) => {
    if (!id) { setDashboard(null); return; }
    setDashboard(await apiRequest(`/property-management/properties/${id}/records`));
  };

  useEffect(() => { loadProperties().catch((error) => setError(error.message)); }, []);
  useEffect(() => { loadRecords(selectedId).catch((error) => setError(error.message)); }, [selectedId]);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      let documentIds = [];
      if (maintenanceFile) {
        const body = new FormData();
        body.append("document", maintenanceFile);
        const uploaded = await apiRequest(`/property-management/properties/${selectedId}/documents`, { method: "POST", body });
        documentIds = [uploaded.id];
      }
      await apiRequest(`/property-management/properties/${selectedId}/records`, {
        method: "POST",
        body: JSON.stringify({
          record_type: form.record_type,
          description: form.description,
          amount: form.amount || null,
          currency: form.amount ? form.currency : null,
          document_ids: documentIds
        })
      });
      setSuccess("Property management activity recorded.");
      setForm({ ...form, description: "", amount: "" });
      setMaintenanceFile(null);
      await loadRecords(selectedId);
    } catch (error) {
      setError(error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="panel asset-panel">
      <div className="panel-heading"><div><h2>Property Management</h2><p>Only properties explicitly assigned to your account are available here.</p></div><span className="tag">PROPERTY MANAGER</span></div>
      {properties.length === 0 ? <div className="empty-state">No properties are assigned to your account.</div> : <>
        <div className="form-group"><label htmlFor="managed-property">Assigned property</label><select id="managed-property" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{properties.map((property) => <option key={property.id} value={property.id}>{property.name} · {property.location}</option>)}</select></div>
        {dashboard && <section className="stats-grid">
          <div className="stat-card"><span className="stat-label">RENTAL INCOME</span><h3>{Object.entries(dashboard.performance.rental_income_by_currency).map(([currency, amount]) => `${currency} ${amount}`).join(" · ") || "0"}</h3><p>Recorded income by currency</p></div>
          <div className="stat-card"><span className="stat-label">OPERATING EXPENSES</span><h3>{Object.entries(dashboard.performance.operating_expenses_by_currency).map(([currency, amount]) => `${currency} ${amount}`).join(" · ") || "0"}</h3><p>Recorded expenses by currency</p></div>
          <div className="stat-card"><span className="stat-label">NET OPERATING RESULT</span><h3>{Object.entries(dashboard.performance.net_operating_result_by_currency).map(([currency, amount]) => `${currency} ${amount}`).join(" · ") || "0"}</h3><p>From recorded entries, by currency</p></div>
          <div className="stat-card"><span className="stat-label">MAINTENANCE RECORDS</span><h3>{dashboard.performance.maintenance_count}</h3><p>Activity entries</p></div>
        </section>}
        <form onSubmit={save}>
          <div className="form-grid">
            <div className="form-group"><label>Activity type</label><select value={form.record_type} onChange={(event) => setForm({ ...form, record_type: event.target.value })}><option value="MAINTENANCE">Maintenance</option><option value="RENTAL_INCOME">Rental income</option><option value="OPERATING_EXPENSE">Operating expense</option><option value="PROPERTY_UPDATE">Property update</option></select></div>
            <div className="form-group"><label>Description</label><input required minLength="3" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></div>
            <div className="form-group"><label>Amount (income/expense)</label><input type="number" min="0" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} /></div>
            <div className="form-group"><label>Currency</label><input maxLength="10" value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })} /></div>
            <div className="form-group"><label>Maintenance document (PDF/PNG/JPEG)</label><input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(event) => setMaintenanceFile(event.target.files?.[0] || null)} /></div>
          </div>
          <button type="submit" className="primary-button" disabled={saving}>{saving ? "Saving…" : "Record activity"}</button>
        </form>
        <h3>Management Activity History</h3>
        {dashboard?.records?.length === 0 ? <div className="empty-state">No management records are available.</div> : <div className="table-wrapper"><table className="asset-table"><thead><tr><th>Type</th><th>Description</th><th>Amount</th><th>Documents</th><th>Recorded</th></tr></thead><tbody>{dashboard?.records?.map((record) => <tr key={record.id}><td>{record.record_type}</td><td>{record.description}</td><td>{record.amount ? `${record.currency} ${record.amount}` : "—"}</td><td>{record.document_ids.map((id) => <a key={id} href="#" onClick={async (event) => { event.preventDefault(); try { const response = await fetch(`${import.meta.env.VITE_API_URL || "http://localhost:8001"}/property-management/documents/${id}/download`, { headers: { Authorization: `Bearer ${localStorage.getItem("nexa_token") || sessionStorage.getItem("nexa_token")}` } }); if (!response.ok) throw new Error("Document download failed."); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `maintenance-${id}`; link.click(); URL.revokeObjectURL(url); } catch (error) { setError(error.message); } }}>Document {id}</a>)}</td><td>{new Date(record.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>}
      </>}
    </section>
  );
}
