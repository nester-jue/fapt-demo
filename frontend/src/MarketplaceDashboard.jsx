import React, { useEffect, useRef, useState } from "react";

export default function MarketplaceDashboard({ apiRequest, setError, setSuccess }) {
  const [filters, setFilters] = useState({ search: "", location: "", property_type: "" });
  const [items, setItems] = useState([]);
  const [quantities, setQuantities] = useState({});
  const [loading, setLoading] = useState(true);
  const [buyingId, setBuyingId] = useState(null);
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const requestKeys = useRef({});

  const load = async (start = 0, append = false) => {
    setLoading(true);
    try {
      const query = new URLSearchParams();
      query.set("skip", String(start));
      query.set("limit", "20");
      Object.entries(filters).forEach(([key, value]) => {
        if (value.trim()) query.set(key, value.trim());
      });
      const result = await apiRequest(`/marketplace/opportunities?${query.toString()}`);
      setItems((current) => append ? [...current, ...(result.items || [])] : (result.items || []));
      setSkip(start);
      setHasMore(Boolean(result.has_more));
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(0, false);
  }, []);

  const search = async (event) => {
    event.preventDefault();
    await load(0, false);
  };

  const buy = async (opportunity) => {
    setError("");
    setSuccess("");
    const quantity = quantities[opportunity.issuance_id] || "";
    if (!quantity || Number(quantity) <= 0) {
      setError("Enter a positive token quantity.");
      return;
    }
    if (!window.confirm(
      `Record a demonstration allocation of ${quantity} ${opportunity.token_symbol}? No payment will be processed or confirmed.`
    )) return;
    const intent = `${opportunity.issuance_id}:${quantity}`;
    const idempotencyKey = requestKeys.current[intent] || window.crypto.randomUUID();
    requestKeys.current[intent] = idempotencyKey;
    setBuyingId(opportunity.issuance_id);
    try {
      const result = await apiRequest("/marketplace/purchases", {
        method: "POST",
        body: JSON.stringify({
          issuance_id: opportunity.issuance_id,
          quantity,
          idempotency_key: idempotencyKey
        })
      });
      setSuccess(
        `${result.message} Reference: ${result.transaction_ref}. Payment status: ${result.payment_status}.`
      );
      delete requestKeys.current[intent];
      setQuantities((current) => ({ ...current, [opportunity.issuance_id]: "" }));
      await load(0, false);
    } catch (error) {
      setError(error.message);
    } finally {
      setBuyingId(null);
    }
  };

  return (
    <section className="panel asset-panel">
      <div className="panel-heading">
        <div>
          <h2>Investment Marketplace</h2>
          <p>Approved opportunities only. This environment records demonstration allocations; it does not process payments.</p>
        </div>
        <span className="tag">INVESTOR</span>
      </div>
      <form className="form-grid marketplace-filters" onSubmit={search}>
        <div className="form-group">
          <label htmlFor="market-search">Search properties</label>
          <input id="market-search" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
        </div>
        <div className="form-group">
          <label htmlFor="market-location">Location</label>
          <input id="market-location" value={filters.location} onChange={(event) => setFilters({ ...filters, location: event.target.value })} />
        </div>
        <div className="form-group">
          <label htmlFor="market-type">Property type</label>
          <input id="market-type" value={filters.property_type} onChange={(event) => setFilters({ ...filters, property_type: event.target.value })} />
        </div>
        <button className="primary-button" type="submit" disabled={loading}>Search</button>
      </form>

      {loading ? <div className="empty-state">Loading approved opportunities…</div> : null}
      {!loading && items.length === 0 ? <div className="empty-state">No approved opportunities match those filters.</div> : null}
      <div className="marketplace-grid">
        {items.map((item) => (
          <article className="marketplace-card" key={item.issuance_id}>
            <div className="marketplace-card-heading">
              <div><p className="eyebrow">{item.property_type} · {item.location || item.country || "Location not listed"}</p><h3>{item.name}</h3></div>
              <span className="status-badge approved">APPROVED</span>
            </div>
            <p>{item.description || "No property description supplied."}</p>
            <dl className="marketplace-details">
              <div><dt>Approved valuation</dt><dd>{item.valuation.currency} {item.valuation.amount}</dd></div>
              <div><dt>Token price</dt><dd>{item.currency} {item.token_price} / {item.token_symbol}</dd></div>
              <div><dt>Available supply</dt><dd>{item.available_supply} tokens</dd></div>
              <div><dt>Minimum investment</dt><dd>{item.currency} {item.minimum_investment}</dd></div>
              {item.maximum_investment && <div><dt>Maximum investment</dt><dd>{item.currency} {item.maximum_investment}</dd></div>}
            </dl>
            <details><summary>Investment terms and eligibility</summary><p>{item.investment_terms}</p><p>{item.eligibility_requirements}</p><p>{item.restrictions}</p></details>
            <details><summary>Legal disclosures and risks</summary><p>{item.disclosures}</p><p><strong>Token rights:</strong> {item.legal_rights}</p><p><strong>Applicable risks:</strong> {item.legal_risks}</p></details>
            <div className="demo-payment-note">{item.payment_notice}</div>
            <div className="purchase-row">
              <label>
                Quantity
                <input type="number" min="0.00000001" step="0.00000001" max={item.available_supply} value={quantities[item.issuance_id] || ""} onChange={(event) => setQuantities({ ...quantities, [item.issuance_id]: event.target.value })} />
              </label>
              <button className="primary-button" type="button" disabled={buyingId === item.issuance_id || Number(item.available_supply) <= 0} onClick={() => buy(item)}>
                {buyingId === item.issuance_id ? "Allocating…" : "Demo Allocate"}
              </button>
            </div>
          </article>
        ))}
      </div>
      {hasMore && <button className="secondary-button" type="button" disabled={loading} onClick={() => load(skip + 20, true)}>{loading ? "Loading…" : "Load more opportunities"}</button>}
    </section>
  );
}
