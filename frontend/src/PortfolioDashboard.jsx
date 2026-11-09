import React, { useEffect, useState } from "react";

export default function PortfolioDashboard({ apiRequest, setError }) {
  const [portfolio, setPortfolio] = useState(null);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    Promise.all([
      apiRequest("/tokens/portfolio"),
      apiRequest("/tokens/transactions")
    ]).then(([summary, transactions]) => {
      setPortfolio(summary);
      setHistory(transactions);
    }).catch((error) => setError(error.message));
  }, []);

  if (!portfolio) return <div className="empty-state">Loading portfolio…</div>;
  return (
    <section className="panel asset-panel">
      <div className="panel-heading"><div><h2>Investment Portfolio</h2><p>Balances and value are derived from issuance, purchase and transfer ledger entries.</p></div><span className="tag">{portfolio.account_status}</span></div>
      <section className="stats-grid">
        <div className="stat-card"><span className="stat-label">INVESTOR</span><h3>{portfolio.investor}</h3><p>Account holder</p></div>
        <div className="stat-card"><span className="stat-label">TOTAL TOKENS</span><h3>{portfolio.total_tokens_held}</h3><p>Across active property issuances</p></div>
        <div className="stat-card"><span className="stat-label">PORTFOLIO VALUE</span><h3>{Object.entries(portfolio.total_investment_value_by_currency).map(([currency, value]) => `${currency} ${value}`).join(" · ") || "0"}</h3><p>Acquisition-price estimate by currency</p></div>
        <div className="stat-card"><span className="stat-label">RESTRICTED TOKENS</span><h3>{portfolio.restricted_balance}</h3><p>No separate lock-up balance configured</p></div>
      </section>
      <h3>Holdings by Property</h3>
      {portfolio.holdings_by_property.length === 0 ? <div className="empty-state">No token holdings are recorded.</div> : (
        <div className="table-wrapper"><table className="asset-table"><thead><tr><th>Property</th><th>Token</th><th>Balance</th><th>Investment value</th><th>Available</th></tr></thead><tbody>
          {portfolio.holdings_by_property.map((holding) => <tr key={holding.issuance_id}><td>{holding.asset_name}</td><td>{holding.token_symbol}</td><td>{holding.balance}</td><td>{holding.currency} {holding.holding_value}</td><td>{holding.balance}</td></tr>)}
        </tbody></table></div>
      )}
      <h3>Acquisition and Transfer History</h3>
      {history.length === 0 ? <div className="empty-state">No acquisition or transfer transactions are recorded.</div> : (
        <div className="table-wrapper"><table className="asset-table"><thead><tr><th>Reference</th><th>Type</th><th>Property</th><th>Quantity</th><th>Direction</th><th>Date</th></tr></thead><tbody>
          {history.map((item) => <tr key={item.transaction_ref}><td>{item.transaction_ref}</td><td>{item.transaction_type}</td><td>{item.asset_name}</td><td>{item.amount}</td><td>{item.direction}</td><td>{new Date(item.created_at).toLocaleString()}</td></tr>)}
        </tbody></table></div>
      )}
    </section>
  );
}
