import React, { useEffect, useState } from "react";

export default function AuditDashboard({ apiRequest, setError }) {
  const [verification, setVerification] = useState(null);
  const [events, setEvents] = useState([]);
  useEffect(() => {
    Promise.all([apiRequest("/admin/ledger/verify"), apiRequest("/admin/ledger/audit-events?limit=100")])
      .then(([integrity, auditEvents]) => { setVerification(integrity); setEvents(auditEvents); })
      .catch((error) => setError(error.message));
  }, []);
  return <section className="panel asset-panel">
    <div className="panel-heading"><div><h2>Audit and Ledger Integrity</h2><p>Integrity hashes are database controls, not decentralised consensus.</p></div><span className={`status-badge ${verification?.integrity === "VALID" ? "approved" : "rejected"}`}>{verification?.integrity || "CHECKING"}</span></div>
    {!verification ? <div className="empty-state">Verifying recorded chains…</div> : <div className="result-grid">
      <div><dt>Audit events checked</dt><dd>{verification.audit_chain.records_checked}</dd></div>
      <div><dt>Audit chain failures</dt><dd>{verification.audit_chain.failure_count}</dd></div>
      <div><dt>Token transactions checked</dt><dd>{verification.transaction_chains.records_checked}</dd></div>
      <div><dt>Transaction chain failures</dt><dd>{verification.transaction_chains.failure_count}</dd></div>
      <div className="full-width"><dt>Integrity limitation</dt><dd>{verification.limitations}</dd></div>
    </div>}
    <h3>Recent Audit Events</h3>
    {events.length === 0 ? <div className="empty-state">No audit records are available.</div> : <div className="table-wrapper"><table className="asset-table"><thead><tr><th>Event ID</th><th>Action</th><th>Entity</th><th>Actor ID</th><th>Timestamp</th><th>Hash</th></tr></thead><tbody>{events.map((event) => <tr key={event.event_id}><td>{event.event_id}</td><td>{event.action}</td><td>{event.entity_type} {event.entity_id}</td><td>{event.user_id ?? "System"}</td><td>{new Date(event.created_at).toLocaleString()}</td><td className="reference-text">{event.event_hash}</td></tr>)}</tbody></table></div>}
  </section>;
}
