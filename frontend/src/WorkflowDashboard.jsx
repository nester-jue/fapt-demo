import React, { useEffect, useState } from "react";

const today = new Date().toISOString().slice(0, 10);

function WorkflowDashboard({ user, token, apiRequest, setError, setSuccess }) {
  const [records, setRecords] = useState([]);
  const [valuationHistory, setValuationHistory] = useState([]);
  const [valuationsToReview, setValuationsToReview] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [history, setHistory] = useState([]);
  const [legalDetails, setLegalDetails] = useState(null);
  const [complianceHistory, setComplianceHistory] = useState([]);
  const [documentFile, setDocumentFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [compliance, setCompliance] = useState(null);
  const [complianceForm, setComplianceForm] = useState({
    kyc_status: "PENDING",
    aml_status: "PENDING",
    identity_verification_status: "PENDING",
    decision: "APPROVE",
    comments: "Manual review in demonstration environment.",
    identity_document: "REQUIRED",
    address_document: "REQUIRED"
  });
  const [legalForm, setLegalForm] = useState({
    jurisdiction: "",
    jurisdiction_requirements: "",
    proposed_tokenisation_arrangements: "",
    token_rights_description: "",
    legal_risks: "",
    comments: "",
    decision: "APPROVED"
  });
  const [valuationForm, setValuationForm] = useState({
    amount: "",
    currency: "USD",
    valuation_date: today,
    valid_until: "",
    methodology: ""
  });
  const [proposalForm, setProposalForm] = useState({
    token_name: "",
    token_symbol: "",
    token_price: "1",
    total_supply: "",
    decimal_precision: 0,
    currency: "USD",
    minimum_investment: "1",
    maximum_investment: "",
    issuance_date: today,
    issuance_terms: "",
    restrictions: "",
    disclosures: "",
    proposed_tokenisation_arrangements: "",
    token_rights_description: ""
  });

  const role = user?.role;
  const isSuperAdmin = ["admin", "super_admin"].includes(role);
  const isValuer = role === "property_valuer";
  const isLegal = role === "legal_advisor";
  const isCompliance = role === "compliance_officer";
  const isTokenOfficer = role === "tokenization_officer";
  const isInvestor = ["investor", "property_owner"].includes(role);

  const refresh = async () => {
    setError("");
    try {
      if (isInvestor) {
        setCompliance(await apiRequest("/workflow/compliance/me"));
      } else if (isValuer) {
        const [pending, past] = await Promise.all([
          apiRequest("/workflow/valuations/pending"),
          apiRequest("/workflow/valuations/history")
        ]);
        setRecords(pending);
        setValuationHistory(past);
      } else if (isLegal) {
        setRecords(await apiRequest("/workflow/legal/pending"));
      } else if (isCompliance) {
        setRecords(await apiRequest("/workflow/compliance/users"));
      } else if (isSuperAdmin || isTokenOfficer) {
        const [dashboard, valuationQueue] = await Promise.all([
          apiRequest("/workflow/approvals"),
          isSuperAdmin
            ? apiRequest("/workflow/valuations/review-queue")
            : Promise.resolve([])
        ]);
        setRecords(dashboard);
        setValuationsToReview(valuationQueue);
      }
    } catch (error) {
      setError(error.message);
    }
  };

  const viewLegalDetails = async (assetId) => {
    try {
      setLegalDetails(await apiRequest(`/workflow/properties/${assetId}/review-details`));
    } catch (error) {
      setError(error.message);
    }
  };

  const viewComplianceHistory = async (userId) => {
    try {
      setComplianceHistory(await apiRequest(`/workflow/compliance/users/${userId}/history`));
    } catch (error) {
      setError(error.message);
    }
  };

  const downloadDocument = async (documentId) => {
    try {
      const base = import.meta.env.VITE_API_URL || "http://localhost:8001";
      const response = await fetch(`${base}/workflow/documents/${documentId}/download`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Download failed (${response.status})`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `workflow-document-${documentId}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setError(error.message);
    }
  };

  useEffect(() => {
    refresh();
  }, [role]);

  const sendDecision = async (endpoint, decision, comments) => {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await apiRequest(endpoint, {
        method: "POST",
        body: JSON.stringify({ decision, comments })
      });
      setSuccess(`Decision recorded: ${decision}.`);
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  };

  const uploadDocument = async (assetId, type) => {
    if (!documentFile) throw new Error("Choose a PDF, PNG, or JPEG document.");
    if (documentFile.size > 10 * 1024 * 1024) {
      throw new Error("Workflow documents must be 10 MB or smaller.");
    }
    const body = new FormData();
    body.append("document_type", type);
    body.append("document", documentFile);
    return apiRequest(`/workflow/properties/${assetId}/documents`, {
      method: "POST",
      body
    });
  };

  const submitValuation = async (event) => {
    event.preventDefault();
    if (!selectedId) return setError("Select a verified property.");
    setBusy(true);
    setError("");
    try {
      const report = await uploadDocument(Number(selectedId), "VALUATION_REPORT");
      const result = await apiRequest(`/workflow/properties/${selectedId}/valuations`, {
        method: "POST",
        body: JSON.stringify({
          ...valuationForm,
          amount: valuationForm.amount,
          report_document_ids: [report.id]
        })
      });
      setSuccess(`Valuation #${result.id} submitted for independent review.`);
      setDocumentFile(null);
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  };

  const submitLegalReview = async (event) => {
    event.preventDefault();
    if (!selectedId) return setError("Select a property.");
    setBusy(true);
    setError("");
    try {
      const agreement = documentFile
        ? await uploadDocument(Number(selectedId), "LEGAL_AGREEMENT")
        : null;
      const result = await apiRequest(`/workflow/properties/${selectedId}/legal-reviews`, {
        method: "POST",
        body: JSON.stringify({
          ...legalForm,
          supporting_document_ids: agreement ? [agreement.id] : []
        })
      });
      setSuccess(`Legal review #${result.id} recorded.`);
      setDocumentFile(null);
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  };

  const submitCompliance = async (event) => {
    event.preventDefault();
    if (!selectedId) return setError("Select an investor or property owner.");
    setBusy(true);
    setError("");
    try {
      const response = await apiRequest(`/workflow/compliance/users/${selectedId}/decision`, {
        method: "POST",
        body: JSON.stringify({
          decision: complianceForm.decision,
          kyc_status: complianceForm.kyc_status,
          aml_status: complianceForm.aml_status,
          identity_verification_status: complianceForm.identity_verification_status,
          required_documents: [
            { name: "Identity evidence", status: complianceForm.identity_document },
            { name: "Proof of address", status: complianceForm.address_document }
          ],
          comments: complianceForm.comments
        })
      });
      setSuccess(`Compliance status recorded: ${response.eligibility_status}.`);
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  };

  const submitProposal = async (event) => {
    event.preventDefault();
    if (!selectedId) return setError("Select a property.");
    setBusy(true);
    setError("");
    try {
      await uploadDocument(Number(selectedId), "PROPOSAL_DISCLOSURE");
      const result = await apiRequest(`/workflow/properties/${selectedId}/proposals`, {
        method: "POST",
        body: JSON.stringify({
          ...proposalForm,
          token_symbol: proposalForm.token_symbol.toUpperCase(),
          maximum_investment: proposalForm.maximum_investment || null
        })
      });
      setSuccess(`Proposal #${result.id} submitted for review.`);
      setDocumentFile(null);
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  };

  const issueApprovedProposal = async (item) => {
    const proposal = item.proposal;
    if (!proposal) return;
    setBusy(true);
    setError("");
    try {
      const result = await apiRequest(`/admin/token-issuances/${item.property.id}`, {
        method: "POST",
        body: JSON.stringify({
          token_name: proposal.token_name,
          token_symbol: proposal.token_symbol,
          token_price: proposal.token_price,
          total_supply: proposal.total_supply,
          decimal_precision: proposal.decimal_precision,
          currency: proposal.currency,
          minimum_investment: proposal.minimum_investment,
          maximum_investment: proposal.maximum_investment,
          issuance_date: proposal.issuance_date,
          issuance_terms: proposal.issuance_terms,
          restrictions: proposal.restrictions,
          proposed_tokenisation_arrangements: proposal.proposed_tokenisation_arrangements,
          token_rights_description: proposal.token_rights_description
        })
      });
      setSuccess(`Database-backed simulated issuance recorded (#${result.issuance_id}).`);
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  };

  const viewValuationHistory = async (assetId) => {
    try {
      setHistory(await apiRequest(`/workflow/properties/${assetId}/valuations`));
    } catch (error) {
      setError(error.message);
    }
  };

  const field = (label, value, onChange, options = {}) => (
    <div className="form-group" key={label}>
      <label>{label}</label>
      {options.multiline ? (
        <textarea value={value} onChange={(event) => onChange(event.target.value)} required={options.required !== false} rows={options.rows || 3} />
      ) : (
        <input
          type={options.type || "text"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          required={options.required !== false}
          min={options.min}
          step={options.step}
        />
      )}
    </div>
  );

  if (isInvestor) {
    return (
      <section className="panel asset-panel">
        <div className="panel-heading">
          <div>
            <h2>Investor Eligibility</h2>
            <p>Restricted token activities require an approved compliance review.</p>
          </div>
          <button className="secondary-button" onClick={refresh}>Refresh</button>
        </div>
        <div className="stats-grid">
          {[
            ["KYC review", compliance?.kyc_status],
            ["AML review", compliance?.aml_status],
            ["Identity status", compliance?.identity_verification_status],
            ["Eligibility", compliance?.eligibility_status]
          ].map(([label, value]) => (
            <div className="stat-card" key={label}>
              <span className="stat-label">{label.toUpperCase()}</span>
              <h3>{value || "Loading"}</h3>
            </div>
          ))}
        </div>
        <p>Identity and compliance decisions are manually recorded for demonstration only. This is not a real KYC, AML, or identity-verification service. Do not upload identity documents or enter sensitive personal information.</p>
        <h3>Required document tracking</h3>
        <ul>
          {(compliance?.required_documents || []).map((document) => (
            <li key={document.name}>{document.name}: {document.status}</li>
          ))}
          {!compliance?.required_documents?.length && <li>No document checklist has been assigned.</li>}
        </ul>
      </section>
    );
  }

  return (
    <>
      {isValuer && (
        <>
          <section className="panel asset-panel">
            <div className="panel-heading">
              <div><h2>Properties Awaiting Valuation</h2><p>Verified properties requiring a valuation report and methodology.</p></div>
              <button className="secondary-button" onClick={refresh}>Refresh</button>
            </div>
            <div className="table-wrapper">
              <table className="asset-table"><thead><tr><th>PROPERTY</th><th>REFERENCE</th><th>ESTIMATE</th><th>HISTORY</th></tr></thead>
                <tbody>{records.map((item) => <tr key={item.id}>
                  <td>{item.name}</td><td>{item.asset_code}</td><td>{item.estimated_value} {item.currency}</td>
                  <td><button className="secondary-button" onClick={() => viewValuationHistory(item.id)}>View</button></td>
                </tr>)}</tbody>
              </table>
            </div>
            <label>Property to value</label>
            <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}><option value="">Select verified property</option>{records.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.asset_code})</option>)}</select>
            <form onSubmit={submitValuation}>
              <div className="form-grid">
                {field("Market value", valuationForm.amount, (value) => setValuationForm({ ...valuationForm, amount: value }), { type: "number", min: "0.01", step: "0.01" })}
                {field("Currency", valuationForm.currency, (value) => setValuationForm({ ...valuationForm, currency: value.toUpperCase() }))}
                {field("Valuation date", valuationForm.valuation_date, (value) => setValuationForm({ ...valuationForm, valuation_date: value }), { type: "date" })}
                {field("Valid until", valuationForm.valid_until, (value) => setValuationForm({ ...valuationForm, valid_until: value }), { type: "date" })}
                {field("Methodology", valuationForm.methodology, (value) => setValuationForm({ ...valuationForm, methodology: value }), { multiline: true })}
                <div className="form-group"><label>Valuation report (PDF, PNG, JPEG)</label><input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(event) => setDocumentFile(event.target.files?.[0] || null)} required /></div>
              </div>
              <button className="primary-button" disabled={busy}>Submit valuation for review</button>
            </form>
          </section>
          {!!history.length && <section className="panel asset-panel"><h3>Selected property valuation history</h3>{history.map((item) => <p key={item.id}>#{item.id}: {item.amount} {item.currency} — {item.status}, valid to {item.valid_until}; {item.review_comments || "No review comments."}</p>)}</section>}
          <section className="panel asset-panel"><h3>Historical valuations</h3><div className="table-wrapper"><table className="asset-table"><thead><tr><th>PROPERTY</th><th>VALUATION</th><th>DATE / VALIDITY</th><th>STATUS</th><th>REPORTS</th></tr></thead><tbody>
            {valuationHistory.map((item) => <tr key={item.id}><td>{item.asset_name} ({item.asset_code})</td><td>{item.amount} {item.currency}</td><td>{item.valuation_date} / {item.valid_until}</td><td>{item.status}<br />{item.review_comments}</td><td>{item.report_document_ids.map((id) => <button key={id} className="secondary-button" onClick={() => downloadDocument(id)}>Report #{id}</button>)}</td></tr>)}
          </tbody></table></div></section>
        </>
      )}

      {isLegal && (
        <section className="panel asset-panel">
          <div className="panel-heading"><div><h2>Legal Review</h2><p>Review jurisdiction-specific requirements, valuation, rights and risks.</p></div><button className="secondary-button" onClick={refresh}>Refresh</button></div>
          <div className="table-wrapper"><table className="asset-table"><thead><tr><th>PROPERTY</th><th>JURISDICTION</th><th>APPROVED VALUATION</th><th>DETAILS</th></tr></thead><tbody>
            {records.map((item) => <tr key={item.property.id}><td>{item.property.name}</td><td>{item.property.jurisdiction}</td><td>{item.valuation?.amount} {item.valuation?.currency}</td><td><button className="secondary-button" onClick={() => viewLegalDetails(item.property.id)}>Review details</button></td></tr>)}
          </tbody></table></div>
          {legalDetails && <section className="stat-card">
            <h3>{legalDetails.property.name} — review materials</h3>
            <p>Registered owner: {legalDetails.property.owner_name}</p>
            <p>Jurisdiction: {legalDetails.property.jurisdiction}</p>
            <p>Approved valuation: {legalDetails.valuation?.amount} {legalDetails.valuation?.currency} ({legalDetails.valuation?.methodology})</p>
            <h4>Verification results</h4>
            {(legalDetails.verification_history || []).map((item) => <p key={item.id}>{item.decision}: {item.comments}</p>)}
            <h4>Legal agreement documents</h4>
            {(legalDetails.legal_documents || []).map((item) => <button key={item.id} className="secondary-button" onClick={() => downloadDocument(item.id)}>Download {item.original_filename}</button>)}
            <h4>Prior legal decisions</h4>
            {(legalDetails.legal_review_history || []).map((item) => <p key={item.id}>{item.jurisdiction}: {item.decision} — {item.comments}</p>)}
          </section>}
          <label>Property</label><select value={selectedId} onChange={(event) => { setSelectedId(event.target.value); const selected = records.find((row) => String(row.property.id) === event.target.value); if (selected) setLegalForm({ ...legalForm, jurisdiction: selected.property.jurisdiction || "" }); }}><option value="">Select property</option>{records.map((item) => <option key={item.property.id} value={item.property.id}>{item.property.name}</option>)}</select>
          <form onSubmit={submitLegalReview}><div className="form-grid">
            {field("Jurisdiction", legalForm.jurisdiction, (value) => setLegalForm({ ...legalForm, jurisdiction: value }))}
            {field("Applicable jurisdiction requirements", legalForm.jurisdiction_requirements, (value) => setLegalForm({ ...legalForm, jurisdiction_requirements: value }), { multiline: true })}
            {field("Proposed tokenisation arrangements", legalForm.proposed_tokenisation_arrangements, (value) => setLegalForm({ ...legalForm, proposed_tokenisation_arrangements: value }), { multiline: true })}
            {field("Rights represented by token (not direct property ownership)", legalForm.token_rights_description, (value) => setLegalForm({ ...legalForm, token_rights_description: value }), { multiline: true })}
            {field("Legal risks", legalForm.legal_risks, (value) => setLegalForm({ ...legalForm, legal_risks: value }), { multiline: true })}
            {field("Review comments", legalForm.comments, (value) => setLegalForm({ ...legalForm, comments: value }), { multiline: true })}
            <div className="form-group"><label>Decision</label><select value={legalForm.decision} onChange={(event) => setLegalForm({ ...legalForm, decision: event.target.value })}><option value="APPROVED">Approve</option><option value="REJECTED">Reject</option><option value="REQUEST_CHANGES">Request changes</option><option value="ADDITIONAL_DOCUMENTATION">Request additional documents</option></select></div>
            <div className="form-group"><label>Legal agreement (PDF, PNG, JPEG)</label><input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(event) => setDocumentFile(event.target.files?.[0] || null)} required={legalForm.decision === "APPROVED"} /></div>
          </div><button className="primary-button" disabled={busy}>Record legal review</button></form>
        </section>
      )}

      {isCompliance && (
        <section className="panel asset-panel">
          <div className="panel-heading"><div><h2>Investor Eligibility Review</h2><p>Track status and required document checklist only; do not enter sensitive personal information.</p></div><button className="secondary-button" onClick={refresh}>Refresh</button></div>
          <div className="table-wrapper"><table className="asset-table"><thead><tr><th>ACCOUNT</th><th>ROLE</th><th>KYC</th><th>AML</th><th>ELIGIBILITY</th><th>HISTORY</th></tr></thead><tbody>{records.map((item) => <tr key={item.user_id}><td>{item.full_name}</td><td>{item.role}</td><td>{item.kyc_status}</td><td>{item.aml_status}</td><td>{item.eligibility_status}</td><td><button className="secondary-button" onClick={() => viewComplianceHistory(item.user_id)}>View</button></td></tr>)}</tbody></table></div>
          {!!complianceHistory.length && <section className="stat-card"><h3>Compliance history</h3>{complianceHistory.map((item) => <p key={item.id}>{item.decision} — reviewer #{item.reviewer_user_id} — {item.created_at}: {item.comments}</p>)}</section>}
          <label>Account</label><select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}><option value="">Select account</option>{records.map((item) => <option key={item.user_id} value={item.user_id}>{item.full_name} — {item.eligibility_status}</option>)}</select>
          <form onSubmit={submitCompliance}><div className="form-grid">
            {["kyc_status", "aml_status", "identity_verification_status"].map((key) => <div className="form-group" key={key}><label>{key.replaceAll("_", " ")}</label><select value={complianceForm[key]} onChange={(event) => setComplianceForm({ ...complianceForm, [key]: event.target.value })}>{["NOT_STARTED", "PENDING", "UNDER_REVIEW", "APPROVED", "REJECTED", "SUSPENDED", "EXPIRED"].map((value) => <option key={value}>{value}</option>)}</select></div>)}
            <div className="form-group"><label>Compliance decision</label><select value={complianceForm.decision} onChange={(event) => setComplianceForm({ ...complianceForm, decision: event.target.value })}>{[["APPROVE", "Approve"], ["REJECT", "Reject"], ["REQUEST_CHANGES", "Request information"], ["SUSPEND", "Suspend"], ["EXPIRE", "Mark expired"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
            {[["identity_document", "Identity evidence"], ["address_document", "Proof of address"]].map(([key, label]) => <div className="form-group" key={key}><label>{label} checklist status</label><select value={complianceForm[key]} onChange={(event) => setComplianceForm({ ...complianceForm, [key]: event.target.value })}>{["REQUIRED", "SUBMITTED", "ACCEPTED", "REJECTED"].map((value) => <option key={value}>{value}</option>)}</select></div>)}
            {field("Comments (no sensitive personal details)", complianceForm.comments, (value) => setComplianceForm({ ...complianceForm, comments: value }), { multiline: true })}
          </div><button className="primary-button" disabled={busy}>Record manual compliance review</button></form>
          <p>These are manual demonstration statuses, not a real KYC, AML, or identity-verification service. Identity documents and sensitive personal data are not stored by this module.</p>
        </section>
      )}

      {(isSuperAdmin || isTokenOfficer) && (
        <>
          {isTokenOfficer && (
            <section className="panel asset-panel">
              <div className="panel-heading"><div><h2>Tokenisation Proposal</h2><p>Complete prerequisites, attach a disclosure, then submit the configured structure for review.</p></div><button className="secondary-button" onClick={refresh}>Refresh</button></div>
              <label>Property</label><select value={selectedId} onChange={(event) => {
                const id = event.target.value;
                setSelectedId(id);
                const selected = records.find((item) => String(item.property.id) === id);
                if (selected) setProposalForm({
                  ...proposalForm,
                  currency: selected.approved_valuation?.currency || "USD",
                  proposed_tokenisation_arrangements: selected.legal_review?.proposed_tokenisation_arrangements || "",
                  token_rights_description: selected.legal_review?.token_rights_description || ""
                });
              }}><option value="">Select ready property</option>{records.filter((item) => item.stages.slice(0, 5).every((stage) => stage.complete) && item.property.status === "Verified").map((item) => <option key={item.property.id} value={item.property.id}>{item.property.name} — approved value {item.approved_valuation?.amount} {item.approved_valuation?.currency}</option>)}</select>
              <form onSubmit={submitProposal}><div className="form-grid">
                {field("Token name", proposalForm.token_name, (value) => setProposalForm({ ...proposalForm, token_name: value }))}
                {field("Token symbol", proposalForm.token_symbol, (value) => setProposalForm({ ...proposalForm, token_symbol: value.toUpperCase() }))}
                {field("Token price", proposalForm.token_price, (value) => setProposalForm({ ...proposalForm, token_price: value }), { type: "number", min: "0.00000001", step: "0.00000001" })}
                {field("Total supply", proposalForm.total_supply, (value) => setProposalForm({ ...proposalForm, total_supply: value }), { type: "number", min: "0.00000001", step: "any" })}
                {field("Decimal precision (0–8)", proposalForm.decimal_precision, (value) => setProposalForm({ ...proposalForm, decimal_precision: Number(value) }), { type: "number", min: 0, step: 1 })}
                {field("Currency", proposalForm.currency, (value) => setProposalForm({ ...proposalForm, currency: value.toUpperCase() }))}
                {field("Minimum investment", proposalForm.minimum_investment, (value) => setProposalForm({ ...proposalForm, minimum_investment: value }), { type: "number", min: 0, step: "0.01" })}
                {field("Maximum investment (optional)", proposalForm.maximum_investment, (value) => setProposalForm({ ...proposalForm, maximum_investment: value }), { type: "number", min: "0.01", step: "0.01", required: false })}
                {field("Issuance date", proposalForm.issuance_date, (value) => setProposalForm({ ...proposalForm, issuance_date: value }), { type: "date" })}
                {field("Issuance terms", proposalForm.issuance_terms, (value) => setProposalForm({ ...proposalForm, issuance_terms: value }), { multiline: true })}
                {field("Restrictions", proposalForm.restrictions, (value) => setProposalForm({ ...proposalForm, restrictions: value }), { multiline: true })}
                {field("Investor disclosures", proposalForm.disclosures, (value) => setProposalForm({ ...proposalForm, disclosures: value }), { multiline: true })}
                <div className="form-group"><label>Legal-approved tokenisation arrangements</label><textarea value={proposalForm.proposed_tokenisation_arrangements} readOnly rows={3} /></div>
                <div className="form-group"><label>Legal-approved token rights</label><textarea value={proposalForm.token_rights_description} readOnly rows={3} /></div>
                <div className="form-group"><label>Disclosure document (PDF, PNG, JPEG)</label><input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(event) => setDocumentFile(event.target.files?.[0] || null)} required /></div>
              </div><button className="primary-button" disabled={busy}>Submit proposal</button></form>
            </section>
          )}

          {isSuperAdmin && valuationsToReview.length > 0 && (
            <section className="panel asset-panel"><h2>Valuations Awaiting Review</h2><div className="table-wrapper"><table className="asset-table"><thead><tr><th>PROPERTY</th><th>VALUE</th><th>VALUER / METHOD</th><th>REPORT</th><th>DECISION</th></tr></thead><tbody>
              {valuationsToReview.map((item) => <tr key={item.id}><td>#{item.asset_id}</td><td>{item.amount} {item.currency}</td><td>{item.valuer_user_id}<br />{item.methodology}</td><td>{item.report_document_ids.map((id) => <button key={id} className="secondary-button" onClick={() => downloadDocument(id)}>Report #{id}</button>)}</td><td><button className="approve-button" disabled={busy} onClick={() => sendDecision(`/workflow/valuations/${item.id}/decision`, "APPROVED", "Valuation independently reviewed.")}>Approve</button> <button className="reject-button" disabled={busy} onClick={() => sendDecision(`/workflow/valuations/${item.id}/decision`, "REJECTED", "Valuation requires correction.")}>Reject</button></td></tr>)}
            </tbody></table></div></section>
          )}

          <section className="panel asset-panel">
            <div className="panel-heading"><div><h2>Tokenisation Approval Dashboard</h2><p>Each mandatory gate is enforced by the API before final authorisation and issuance.</p></div><button className="secondary-button" onClick={refresh}>Refresh</button></div>
            <div className="table-wrapper"><table className="asset-table"><thead><tr><th>PROPERTY</th><th>STAGE</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>
              {records.map((item) => item.stages.map((stage) => {
                const proposal = item.proposal;
                const proposalPending = isSuperAdmin && stage.stage === "TOKENISATION_PROPOSAL" && proposal?.status === "PENDING_REVIEW";
                const finalReady = isSuperAdmin && stage.stage === "FINAL_AUTHORIZATION" && item.stages.slice(0, -1).every((part) => part.complete);
                const issueReady = isTokenOfficer && stage.stage === "FINAL_AUTHORIZATION" && stage.status === "APPROVED" && proposal?.status === "APPROVED" && item.property.status !== "Tokenised";
                return <tr key={`${item.property.id}-${stage.stage}`}><td>{item.property.name}</td><td>{stage.stage.replaceAll("_", " ")}</td><td>{stage.status}{proposalPending && <div><p>{proposal.token_name} ({proposal.token_symbol}) — {proposal.total_supply} at {proposal.token_price} {proposal.currency}</p><p>Arrangements: {proposal.proposed_tokenisation_arrangements}</p><p>Token rights: {proposal.token_rights_description}</p><p>{proposal.disclosures}</p><p>{proposal.issuance_terms}</p><p>{proposal.restrictions}</p>{item.approvals.filter((approval) => approval.stage === "AGREEMENTS_DISCLOSURES").flatMap((approval) => approval.supporting_document_ids).map((id) => <button key={id} className="secondary-button" onClick={() => downloadDocument(id)}>Review document #{id}</button>)}</div>}</td><td>
                  {proposalPending && <><button className="approve-button" disabled={busy} onClick={() => sendDecision(`/workflow/proposals/${proposal.id}/decision`, "APPROVED", "Proposal and supporting materials reviewed.")}>Approve</button> <button className="reject-button" disabled={busy} onClick={() => sendDecision(`/workflow/proposals/${proposal.id}/decision`, "REJECTED", "Proposal is rejected; return to the proposal stage.")}>Reject</button> <button className="secondary-button" disabled={busy} onClick={() => sendDecision(`/workflow/proposals/${proposal.id}/decision`, "REQUEST_CHANGES", "Return the proposal for changes.")}>Request changes</button> <button className="secondary-button" disabled={busy} onClick={() => sendDecision(`/workflow/proposals/${proposal.id}/decision`, "ADDITIONAL_DOCUMENTATION", "Additional supporting documentation is required.")}>Request documents</button></>}
                  {finalReady && <><button className="approve-button" disabled={busy} onClick={() => sendDecision(`/workflow/properties/${item.property.id}/final-authorization`, "APPROVED", "Final authorisation granted.")}>Final authorise</button> <button className="reject-button" disabled={busy} onClick={() => sendDecision(`/workflow/properties/${item.property.id}/final-authorization`, "REJECTED", "Return to the proposal stage for correction.")}>Reject</button> <button className="secondary-button" disabled={busy} onClick={() => sendDecision(`/workflow/properties/${item.property.id}/final-authorization`, "REQUEST_CHANGES", "Return the proposal for changes.")}>Request changes</button> <button className="secondary-button" disabled={busy} onClick={() => sendDecision(`/workflow/properties/${item.property.id}/final-authorization`, "ADDITIONAL_DOCUMENTATION", "Additional documentation required.")}>Request documents</button></>}
                  {issueReady && <button className="primary-button" disabled={busy} onClick={() => issueApprovedProposal(item)}>Issue database-backed tokens</button>}
                </td></tr>;
              }))}</tbody></table></div>
          </section>
        </>
      )}
    </>
  );
}

export default WorkflowDashboard;
