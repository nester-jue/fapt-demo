import React, { useEffect, useState } from "react";

export default function PropertyDistributionDashboard({ apiRequest, setError }) {
  const [properties, setProperties] = useState([]);
  const [assetId, setAssetId] = useState("");
  const [distribution, setDistribution] = useState(null);
  useEffect(() => {
    apiRequest("/assets/").then((rows) => {
      setProperties(rows);
      if (rows.length) setAssetId(String(rows[0].id));
    }).catch((error) => setError(error.message));
  }, []);
  useEffect(() => {
    if (!assetId) { setDistribution(null); return; }
    apiRequest(`/properties/${assetId}/token-distribution`)
      .then(setDistribution)
      .catch((error) => setError(error.message));
  }, [assetId]);
  return <section className="panel asset-panel">
    <div className="panel-heading"><div><h2>Property Token Distribution</h2><p>Current token balances are derived from issuance and transfer ledger entries.</p></div><span className="tag">PROPERTY OWNER</span></div>
    {properties.length === 0 ? <div className="empty-state">No properties are available in your account.</div> : <>
      <div className="form-group"><label htmlFor="distribution-property">Property</label><select id="distribution-property" value={assetId} onChange={(event) => setAssetId(event.target.value)}>{properties.map((property) => <option key={property.id} value={property.id}>{property.name} · {property.asset_code}</option>)}</select></div>
      {distribution && <><p>Total issued supply: <strong>{distribution.total_supply}</strong></p>{distribution.distribution.length === 0 ? <div className="empty-state">No token allocation records exist.</div> : <div className="table-wrapper"><table className="asset-table"><thead><tr><th>Holder</th><th>User reference</th><th>Token balance</th></tr></thead><tbody>{distribution.distribution.map((holder) => <tr key={holder.user_id}><td>{holder.investor_name}</td><td>{holder.user_id}</td><td>{holder.balance}</td></tr>)}</tbody></table></div>}</>}
    </>}
  </section>;
}
