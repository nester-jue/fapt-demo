import React, { useEffect, useState } from "react";

export default function PropertyManagerAssignments({ apiRequest, setError, setSuccess }) {
  const [properties, setProperties] = useState([]);
  const [managers, setManagers] = useState([]);
  const [assetId, setAssetId] = useState("");
  const [managerId, setManagerId] = useState("");
  const [assignments, setAssignments] = useState([]);
  const loadAssignments = async (id) => {
    if (!id) { setAssignments([]); return; }
    setAssignments(await apiRequest(`/admin/properties/${id}/managers`));
  };
  useEffect(() => {
    Promise.all([apiRequest("/assets/admin/all"), apiRequest("/admin/users?limit=100")])
      .then(([assets, users]) => {
        setProperties(assets);
        setManagers(users.filter((user) => user.role === "property_manager" && user.is_active));
        if (assets.length) setAssetId(String(assets[0].id));
      }).catch((error) => setError(error.message));
  }, []);
  useEffect(() => {
    loadAssignments(assetId).catch((error) => setError(error.message));
  }, [assetId]);
  const assign = async (event) => {
    event.preventDefault();
    try {
      await apiRequest(`/admin/properties/${assetId}/managers`, {
        method: "POST",
        body: JSON.stringify({ manager_user_id: Number(managerId) })
      });
      setSuccess("Property manager assigned and notified.");
      setManagerId("");
      await loadAssignments(assetId);
    } catch (error) { setError(error.message); }
  };
  return <section className="panel asset-panel">
    <div className="panel-heading"><div><h2>Property Manager Assignments</h2><p>Only active property manager accounts can be assigned.</p></div><span className="tag">SUPER ADMIN</span></div>
    <form onSubmit={assign}>
      <div className="form-grid">
        <div className="form-group"><label>Property</label><select required value={assetId} onChange={(event) => setAssetId(event.target.value)}><option value="">Select a property</option>{properties.map((asset) => <option key={asset.id} value={asset.id}>{asset.name} · {asset.asset_code}</option>)}</select></div>
        <div className="form-group"><label>Property manager</label><select required value={managerId} onChange={(event) => setManagerId(event.target.value)}><option value="">Select a manager</option>{managers.map((manager) => <option key={manager.id} value={manager.id}>{manager.full_name} · {manager.email}</option>)}</select></div>
      </div>
      <button className="primary-button" type="submit" disabled={!assetId || !managerId}>Assign manager</button>
    </form>
    <h3>Active assignments</h3>
    {assignments.length === 0 ? <div className="empty-state">No managers are assigned to this property.</div> : <div className="table-wrapper"><table className="asset-table"><thead><tr><th>Manager</th><th>Email</th></tr></thead><tbody>{assignments.map((entry) => <tr key={entry.assignment_id}><td>{entry.manager_name}</td><td>{entry.email}</td></tr>)}</tbody></table></div>}
  </section>;
}
