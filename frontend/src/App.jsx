import React, { useEffect, useRef, useState } from "react";
import AuthScreen from "./AuthScreen";
import WorkflowDashboard from "./WorkflowDashboard";
import MarketplaceDashboard from "./MarketplaceDashboard";
import PortfolioDashboard from "./PortfolioDashboard";
import PropertyManagerDashboard from "./PropertyManagerDashboard";
import PropertyDistributionDashboard from "./PropertyDistributionDashboard";
import NotificationCenter from "./NotificationCenter";
import AuditDashboard from "./AuditDashboard";
import PropertyManagerAssignments from "./PropertyManagerAssignments";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001";

function parseDecimal(value) {
  const match = String(value ?? "").trim().match(/^(\d+)(?:\.(\d+))?$/);
  if (!match) return null;

  const fraction = match[2] || "";
  return {
    coefficient: BigInt(`${match[1]}${fraction}`),
    scale: fraction.length
  };
}

function exactTokenSupply(assetValue, tokenPrice) {
  const asset = parseDecimal(assetValue);
  const price = parseDecimal(tokenPrice);
  if (!asset || !price || price.coefficient <= 0n) return null;

  const numerator =
    asset.coefficient * 10n ** BigInt(price.scale + 8);
  const denominator =
    price.coefficient * 10n ** BigInt(asset.scale);
  if (numerator % denominator !== 0n) return null;

  const units = numerator / denominator;
  const whole = units / 100000000n;
  const fraction = String(units % 100000000n).padStart(8, "0");
  return `${whole}.${fraction}`;
}

function formatDecimalString(value, maximumFractionDigits = 8) {
  const decimal = parseDecimal(value);
  if (!decimal) return String(value ?? "0");

  let coefficient = decimal.coefficient;
  let scale = decimal.scale;
  if (scale > maximumFractionDigits) {
    const divisor = 10n ** BigInt(scale - maximumFractionDigits);
    const remainder = coefficient % divisor;
    coefficient /= divisor;
    if (remainder * 2n >= divisor) coefficient += 1n;
    scale = maximumFractionDigits;
  }

  const divisor = 10n ** BigInt(scale);
  const whole = (coefficient / divisor).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const fraction = String(coefficient % divisor)
    .padStart(scale, "0")
    .replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}

function addDecimalStrings(values) {
  const decimals = values.map(parseDecimal).filter(Boolean);
  if (decimals.length === 0) return "0";

  const scale = Math.max(...decimals.map((value) => value.scale));
  const total = decimals.reduce(
    (sum, value) =>
      sum + value.coefficient * 10n ** BigInt(scale - value.scale),
    0n
  );
  const divisor = 10n ** BigInt(scale);
  const whole = total / divisor;
  const fraction = String(total % divisor)
    .padStart(scale, "0")
    .replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : String(whole);
}

function compareDecimalStrings(left, right) {
  const a = parseDecimal(left);
  const b = parseDecimal(right);
  if (!a || !b) return null;

  const scale = Math.max(a.scale, b.scale);
  const leftUnits = a.coefficient * 10n ** BigInt(scale - a.scale);
  const rightUnits = b.coefficient * 10n ** BigInt(scale - b.scale);
  return leftUnits === rightUnits ? 0 : leftUnits > rightUnits ? 1 : -1;
}

function App() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);

    const [backendStatus, setBackendStatus] = useState("Checking...");
  const [assets, setAssets] = useState([]);
  const [pendingAssets, setPendingAssets] = useState([]);
const [issuanceApprovedAssets, setIssuanceApprovedAssets] = useState([]);
  const [issuanceResult, setIssuanceResult] = useState(null);
  const [isIssuing, setIsIssuing] = useState(false);
  const [isTransferring, setIsTransferring] = useState(false);
  const [managedUsers, setManagedUsers] = useState([]);
  const [auditEvents, setAuditEvents] = useState([]);
  const [documentFile, setDocumentFile] = useState(null);
  const [draftAsset, setDraftAsset] = useState(null);
  const [selectedProperty, setSelectedProperty] = useState(null);

const [issuanceForm, setIssuanceForm] = useState({
  asset_id: "",
  token_name: "",
  token_symbol: "",
  token_price: "1"
});

  // Tokenisation and portfolio data
  const [holdings, setHoldings] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [investors, setInvestors] = useState([]);
  const [ledgerSearch, setLedgerSearch] = useState("");
  const [ledgerTypeFilter, setLedgerTypeFilter] = useState("");
  const [ledgerAssetFilter, setLedgerAssetFilter] = useState("");
  const [ledgerSortOrder, setLedgerSortOrder] = useState("newest");

  // Token transfer form
  const [transferForm, setTransferForm] = useState({
    issuance_id: "",
    recipient_user_id: "",
    amount: ""
  });
  const transferRequestKeys = useRef({});

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [activePage, setActivePage] = useState("overview");
  const [reviewHistory, setReviewHistory] = useState([]);
  const [selectedAsset, setSelectedAsset] = useState(null);
  const [historyAssetId, setHistoryAssetId] = useState("");

  const [form, setForm] = useState({
    name: "",
    category: "Real Estate",
    description: "",
    location: "",
    country: "",
    jurisdiction: "",
    registration_number: "",
    property_size: "",
    property_size_unit: "sqm",
    estimated_value: "",
    currency: "USD",
    owner_name: ""
  });

  const isAdmin = ["admin", "super_admin"].includes(user?.role);
  const isVerifier = isAdmin || user?.role === "property_verifier";
  const canRegisterProperty = ["investor", "property_owner"].includes(user?.role);
  const canAccessWorkflows = [
    "admin",
    "super_admin",
    "property_valuer",
    "legal_advisor",
    "compliance_officer",
    "tokenization_officer",
    "investor",
    "property_owner"
  ].includes(user?.role);

  // Check backend and restore authentication session
  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((response) => {
        if (!response.ok) throw new Error();
        setBackendStatus("Connected");
      })
      .catch(() => setBackendStatus("Offline"));

    const savedToken =
      localStorage.getItem("nexa_token") ||
      sessionStorage.getItem("nexa_token");

    if (!savedToken) {
      setCheckingSession(false);
      return;
    }

    fetch(`${API_URL}/auth/me`, {
      headers: {
        Authorization: `Bearer ${savedToken}`
      }
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Session expired");
        return response.json();
      })
      .then((profile) => {
        setUser(profile);
        setToken(savedToken);
      })
      .catch(() => {
        localStorage.removeItem("nexa_token");
        sessionStorage.removeItem("nexa_token");
      })
      .finally(() => setCheckingSession(false));
  }, []);

  // Central API request function
  const apiRequest = async (endpoint, options = {}) => {
    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.body && !(options.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...options.headers
      }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      const message = Array.isArray(data.detail)
        ? data.detail.map((item) => item.msg).join(", ")
        : data.detail;

      const requestError = new Error(
        message || `Request failed (${response.status})`
      );
      requestError.status = response.status;
      throw requestError;
    }

    return data;
  };

  // Load dashboard information
  const loadDashboard = async () => {
    if (!token || !user) return;

    setLoading(true);
    setError("");

    try {
      const [registeredAssets, pending] = await Promise.all([
        isAdmin
          ? apiRequest("/assets/admin/all")
          : canRegisterProperty
          ? apiRequest("/assets/")
          : Promise.resolve([]),
        isVerifier
          ? apiRequest("/admin/assets/pending")
          : Promise.resolve([])
      ]);
      setAssets(registeredAssets);
      setPendingAssets(pending);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  // Load approved assets available for token issuance
  const loadApprovedAssets = async () => {
    try {
      const data = await apiRequest("/assets/admin/all");
      const approved = data.filter((asset) =>
        ["approved", "verified"].includes(asset.status?.toLowerCase())
      );
      setIssuanceApprovedAssets(approved);
    } catch (err) {
      setError(err.message);
    }
  };

  const loadUsers = async () => {
    try {
      const [users, events] = await Promise.all([
        apiRequest("/admin/users?limit=100"),
        apiRequest("/admin/users/audit-events?limit=50")
      ]);
      setManagedUsers(users);
      setAuditEvents(events);
    } catch (err) {
      setError(err.message);
    }
  };

  // Token issuance now requires the staged workflow dashboard.
  const issueTokens = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("Complete the staged approval workflow before issuing tokens.");
    setActivePage("workflows");
  };

  // Load investor portfolio holdings
  const loadHoldings = async () => {
    try {
      const data = await apiRequest("/tokens/holdings");
      setHoldings(data);
    } catch (err) {
      setError(err.message);
    }
  };

  // Load registered investors for token transfers
  const loadInvestors = async () => {
    try {
      const data = await apiRequest("/tokens/investors");
      setInvestors(data);
    } catch (err) {
      setError(err.message);
    }
  };

  // Load transaction history
  const loadTransactions = async () => {
    try {
      const endpoint = isAdmin
        ? "/admin/token-transactions"
        : "/tokens/transactions";

      const data = await apiRequest(endpoint);
      setTransactions(data);
    } catch (err) {
      setError(err.message);
    }
  };
  // Transfer tokens to another investor
  const transferTokens = async (event) => {
    event.preventDefault();
    if (isTransferring) return;

    setError("");
    setSuccess("");

    if (
      !transferForm.issuance_id ||
      !transferForm.recipient_user_id ||
      !transferForm.amount
    ) {
      setError("Please complete all transfer fields.");
      return;
    }

    const amount = parseDecimal(transferForm.amount);
    if (!amount || amount.coefficient <= 0n) {
      setError("Transfer amount must be greater than zero.");
      return;
    }

    const holding = holdings.find(
      (item) => String(item.issuance_id) === transferForm.issuance_id
    );
    if (!holding) {
      setError("Select a token that is currently in your portfolio.");
      return;
    }
    if (compareDecimalStrings(transferForm.amount, holding.balance) > 0) {
      setError("The transfer amount exceeds your available token balance.");
      return;
    }

    setIsTransferring(true);
    const transferIntent = `${transferForm.issuance_id}:${transferForm.recipient_user_id}:${transferForm.amount.trim()}`;
    const idempotencyKey =
      transferRequestKeys.current[transferIntent] || window.crypto.randomUUID();
    transferRequestKeys.current[transferIntent] = idempotencyKey;
    try {
      const result = await apiRequest("/tokens/transfers", {
        method: "POST",
        body: JSON.stringify({
          issuance_id: Number(transferForm.issuance_id),
          recipient_user_id: Number(transferForm.recipient_user_id),
          amount: transferForm.amount.trim(),
          idempotency_key: idempotencyKey
        })
      });

      setSuccess(
        `Transfer successful. Transaction reference: ${result.transaction_ref}`
      );
      delete transferRequestKeys.current[transferIntent];

      setTransferForm({
        issuance_id: "",
        recipient_user_id: "",
        amount: ""
      });

      await Promise.all([
        loadHoldings(),
        loadTransactions()
      ]);

    } catch (err) {
      setError(err.message);
    } finally {
      setIsTransferring(false);
    }
  };

  

  useEffect(() => {
    if (token && user) {
      loadDashboard();
    }
  }, [token, user]);

  // Authentication completed
  const handleAuthenticated = (profile, accessToken) => {
    setUser(profile);
    setToken(accessToken);
  };

// Load data when a tokenisation page is opened
useEffect(() => {
  if (!token || !user) return;

  if (activePage === "overview") {
    if (isAdmin || user.role === "investor") loadTransactions();
    if (user.role === "investor") loadHoldings();
  }

  if (activePage === "tokens") {
    if (isAdmin) {
      loadApprovedAssets();
      loadTransactions();
    } else {
      loadHoldings();
      loadInvestors();
    }
  }

  if (activePage === "ledger") {
    loadTransactions();
  }

  if (activePage === "users" && isAdmin) {
    loadUsers();
  }
}, [activePage, token, user]);  // Logout
  const handleLogout = () => {
    localStorage.removeItem("nexa_token");
    localStorage.removeItem("nexa_user");
    sessionStorage.removeItem("nexa_token");
    sessionStorage.removeItem("nexa_user");

    setUser(null);
    setToken(null);
    setAssets([]);
    setPendingAssets([]);
    setIssuanceApprovedAssets([]);
    setIssuanceResult(null);
    setHoldings([]);
    setTransactions([]);
    setInvestors([]);
    setIssuanceForm({
      asset_id: "",
      token_name: "",
      token_symbol: "",
      token_price: "1"
    });
    setTransferForm({
      issuance_id: "",
      recipient_user_id: "",
      amount: ""
    });
    setReviewHistory([]);
    setSelectedAsset(null);
    setSelectedProperty(null);
    setManagedUsers([]);
    setAuditEvents([]);
    setDocumentFile(null);
    setDraftAsset(null);
    setActivePage("overview");
    setError("");
    setSuccess("");
  };

  // Handle registration form changes
  const handleChange = (event) => {
    setForm({
      ...form,
      [event.target.name]: event.target.value
    });
  };

  const finishDraftSubmission = async (assetId) => {
    if (!documentFile) {
      throw new Error("Choose a supporting property document to continue.");
    }
    if (documentFile.size > 10 * 1024 * 1024) {
      throw new Error("Property documents must be 10 MB or smaller.");
    }

    const body = new FormData();
    body.append("document", documentFile);
    await apiRequest(`/assets/${assetId}/documents`, {
      method: "POST",
      body
    });
    await apiRequest(`/assets/${assetId}/submit`, { method: "POST" });
    setDraftAsset(null);
    setDocumentFile(null);
    setSuccess("Property submitted for verification.");
    setForm({
      name: "",
      category: "Real Estate",
      description: "",
      location: "",
      country: "",
      jurisdiction: "",
      registration_number: "",
      property_size: "",
      property_size_unit: "sqm",
      estimated_value: "",
      currency: "USD",
      owner_name: ""
    });
    await loadDashboard();
  };

  // Register a property, attach its first document, then submit it.
  const registerAsset = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    let createdAsset = null;

    try {
      createdAsset = await apiRequest("/assets/", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          estimated_value: form.estimated_value,
          property_size: form.property_size
        })
      });
      setDraftAsset(createdAsset);
      await finishDraftSubmission(createdAsset.id);
    } catch (err) {
      setError(
        createdAsset
          ? `Draft ${createdAsset.asset_code} was saved. ${err.message} Select a valid supporting document and retry.`
          : err.message
      );
      if (createdAsset) await loadDashboard();
    }
  };

  const retryDraftSubmission = async () => {
    if (!draftAsset) return;
    setError("");
    try {
      await finishDraftSubmission(draftAsset.id);
    } catch (err) {
      setError(err.message);
    }
  };

  // Approve asset
  const approveAsset = async (assetId) => {
    if (!window.confirm("Are you sure you want to approve this asset?")) {
      return;
    }

    setError("");
    setSuccess("");

    try {
      await apiRequest(`/admin/assets/${assetId}/approve`, {
        method: "POST",
        body: JSON.stringify({
          reason: "Approved following administrator review."
        })
      });

      setSuccess(`Property ${assetId} verification approved.`);
      setSelectedProperty(null);
      setActivePage("reviews");
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  };

  // Reject asset
  const rejectAsset = async (assetId) => {
    const reason = window.prompt(
      "Enter the reason for rejecting this asset:"
    );

    if (reason === null) return;

    if (reason.trim().length < 5) {
      setError("Rejection reason must contain at least 5 characters.");
      return;
    }

    setError("");
    setSuccess("");

    try {
      await apiRequest(`/admin/assets/${assetId}/reject`, {
        method: "POST",
        body: JSON.stringify({
          reason: reason.trim()
        })
      });

      setSuccess(`Property ${assetId} verification rejected.`);
      setSelectedProperty(null);
      setActivePage("reviews");
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  };

  const openPropertyReview = async (assetId) => {
    setError("");
    try {
      const property = await apiRequest(`/admin/assets/${assetId}`);
      setSelectedProperty(property);
      setActivePage("review-detail");
    } catch (err) {
      setError(err.message);
    }
  };

  const requestAdditionalDocuments = async (assetId) => {
    const comments = window.prompt(
      "Describe the additional information or documents required:"
    );
    if (comments === null) return;
    if (comments.trim().length < 3) {
      setError("Please enter a clear request with at least 3 characters.");
      return;
    }
    try {
      await apiRequest(`/admin/assets/${assetId}/request-documents`, {
        method: "POST",
        body: JSON.stringify({ comments: comments.trim() })
      });
      setSuccess(`Additional information requested for property ${assetId}.`);
      setSelectedProperty(null);
      setActivePage("reviews");
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  };

  const downloadPropertyDocument = async (propertyDocument) => {
    try {
      const response = await fetch(`${API_URL}${propertyDocument.download_url}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `Download failed (${response.status}).`);
      }
      const url = URL.createObjectURL(await response.blob());
      const link = window.document.createElement("a");
      link.href = url;
      link.download = propertyDocument.original_filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    }
  };

  const updateManagedUser = async (managedUser, changes) => {
    setError("");
    setSuccess("");
    try {
      if (changes.role) {
        await apiRequest(`/admin/users/${managedUser.id}/role`, {
          method: "PATCH",
          body: JSON.stringify({ role: changes.role })
        });
      } else {
        await apiRequest(`/admin/users/${managedUser.id}/status`, {
          method: "PATCH",
          body: JSON.stringify({ is_active: changes.is_active })
        });
      }
      setSuccess(`Updated account for ${managedUser.full_name}.`);
      await loadUsers();
    } catch (err) {
      setError(err.message);
    }
  };

  // Retrieve review history
  const showHistory = async (assetId) => {
    if (!assetId) {
      setError("Please enter a valid asset ID.");
      return;
    }

    setError("");
    setSelectedAsset(assetId);
    setHistoryAssetId(String(assetId));

    try {
      const history = await apiRequest(
        `/admin/assets/${assetId}/history`
      );

      setReviewHistory(history);
      setActivePage("history");
    } catch (err) {
      setError(err.message);
    }
  };

  // Loading screen
  if (checkingSession) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h2>Loading NEXA...</h2>
          <p>Checking authentication.</p>
        </div>
      </div>
    );
  }

  // Login screen
  if (!user || !token) {
    return <AuthScreen onAuthenticated={handleAuthenticated} />;
  }

  const totalAssets = assets.length;

  const approvedAssets = assets.filter((asset) =>
    ["approved", "verified"].includes(asset.status?.toLowerCase())
  ).length;

  const pendingAssetCount = assets.filter((asset) =>
    ["draft", "submitted", "pending review", "under verification"].includes(
      asset.status?.toLowerCase()
    )
  ).length;

  const rejectedAssetCount = assets.filter(
    (asset) => asset.status?.toLowerCase() === "rejected"
  ).length;

  const tokenisedAssets = assets.filter(
    (asset) =>
      ["tokenised", "tokenized"].includes(
        asset.status?.toLowerCase()
      )
  ).length;

  const issuanceCount = transactions.filter(
    (transaction) => transaction.transaction_type?.toUpperCase() === "ISSUANCE"
  ).length;

  const portfolioValueByCurrency = holdings.reduce((totals, holding) => {
    const currency = holding.currency || "USD";
    totals[currency] = addDecimalStrings([
      totals[currency] || "0",
      String(holding.holding_value)
    ]);
    return totals;
  }, {});

  const portfolioValueLabel =
    Object.entries(portfolioValueByCurrency)
      .map(([currency, value]) => `${currency} ${formatDecimalString(value, 2)}`)
      .join(" · ") || "—";

  const tokenBalancesBySymbol = holdings.reduce((totals, holding) => {
    const symbol = `${holding.token_symbol || holding.token_name} (${holding.asset_code})`;
    totals[symbol] = addDecimalStrings([
      totals[symbol] || "0",
      String(holding.balance)
    ]);
    return totals;
  }, {});

  const tokenHoldingsLabel =
    Object.entries(tokenBalancesBySymbol)
      .map(([symbol, balance]) => `${formatDecimalString(balance)} ${symbol}`)
      .join(" · ") || "0";

  const filteredTransactions = transactions
    .filter((transaction) => {
      const search = ledgerSearch.trim().toLowerCase();
      const referenceMatches =
        !search ||
        transaction.transaction_ref?.toLowerCase().includes(search);
      const typeMatches =
        !ledgerTypeFilter ||
        transaction.transaction_type?.toUpperCase() === ledgerTypeFilter;
      const assetMatches =
        !ledgerAssetFilter ||
        `${transaction.asset_name} ${transaction.token_symbol}` === ledgerAssetFilter;
      return referenceMatches && typeMatches && assetMatches;
    })
    .sort((left, right) => {
      const dateDifference =
        new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
      return ledgerSortOrder === "oldest" ? dateDifference : -dateDifference;
    });

  const money = (asset) =>
    `${asset.currency || "USD"} ${formatDecimalString(asset.estimated_value, 2)}`;

  const statusClass = (status) => {
    const value = status?.toLowerCase().replace(/\s+/g, "-");
    return `status-badge ${value || "unknown"}`;
  };

  return (
    <div className="app">

      {/* SIDEBAR */}

      <aside className="sidebar">

        <div className="brand">
          <div className="brand-icon">N</div>
          <div>
            <h2>NEXA</h2>
            <span>ASSET TOKENISATION</span>
          </div>
        </div>

        <nav>
          <p className="nav-label">WORKSPACE</p>

          <button
            className={activePage === "overview" ? "nav-link active" : "nav-link"}
            onClick={() => setActivePage("overview")}
          >
            Overview
          </button>

          {(isAdmin || canRegisterProperty) && <button
            className={activePage === "assets" ? "nav-link active" : "nav-link"}
            onClick={() => setActivePage("assets")}
          >
            Asset Registry
            </button>}

            {user.role === "investor" && <>
              <p className="nav-label second-label">INVESTMENT</p>
              <button className={activePage === "marketplace" ? "nav-link active" : "nav-link"} onClick={() => setActivePage("marketplace")}>Marketplace</button>
              <button className={activePage === "portfolio" ? "nav-link active" : "nav-link"} onClick={() => setActivePage("portfolio")}>My Portfolio</button>
            </>}

            {user.role === "property_owner" && (
              <button className={activePage === "distribution" ? "nav-link active" : "nav-link"} onClick={() => setActivePage("distribution")}>Token Distribution</button>
            )}

            {user.role === "property_manager" && (
              <button className={activePage === "management" ? "nav-link active" : "nav-link"} onClick={() => setActivePage("management")}>Property Management</button>
            )}

            {canRegisterProperty && (
            <button
              className={activePage === "register" ? "nav-link active" : "nav-link"}
              onClick={() => setActivePage("register")}
            >
              Register Asset
            </button>
          )}

          {isVerifier && (
            <>
              <p className="nav-label second-label">ADMINISTRATION</p>

              <button
                className={activePage === "reviews" ? "nav-link active" : "nav-link"}
                onClick={() => setActivePage("reviews")}
              >
                Asset Reviews
              </button>

              <button
                className={activePage === "history" ? "nav-link active" : "nav-link"}
                onClick={() => setActivePage("history")}
              >
                Review History
              </button>
              {isAdmin && (
                <button
                  className={activePage === "users" ? "nav-link active" : "nav-link"}
                  onClick={() => setActivePage("users")}
                >
                  User Management
                </button>
              )}
            </>
          )}

          {(isAdmin || user.role === "investor") && <>
          <p className="nav-label second-label">TOKEN OPERATIONS</p>

          <button
            className={activePage === "tokens" ? "nav-link active" : "nav-link"}
            onClick={() => setActivePage("tokens")}
          >
            Tokenisation
          </button>

          <button
            className={activePage === "ledger" ? "nav-link active" : "nav-link"}
            onClick={() => setActivePage("ledger")}
          >
            Transaction Ledger
          </button>
          </>}
          {(user.role === "super_admin" || user.role === "auditor") && (
            <button className={activePage === "audit" ? "nav-link active" : "nav-link"} onClick={() => setActivePage("audit")}>Audit Integrity</button>
          )}
          {user.role === "super_admin" && (
            <button className={activePage === "manager-assignments" ? "nav-link active" : "nav-link"} onClick={() => setActivePage("manager-assignments")}>Manager Assignments</button>
          )}
          {canAccessWorkflows && (
            <button
              className={activePage === "workflows" ? "nav-link active" : "nav-link"}
              onClick={() => setActivePage("workflows")}
            >
              {["investor", "property_owner"].includes(user.role)
                ? "Eligibility"
                : "Valuation & Approvals"}
            </button>
          )}
          <button className={activePage === "notifications" ? "nav-link active" : "nav-link"} onClick={() => setActivePage("notifications")}>Notifications</button>
        </nav>

        <div className="sidebar-footer">
          <span className="status-dot"></span>
          Demonstration Environment
        </div>

      </aside>

      {/* MAIN CONTENT */}

      <main className="main-content">

        <header className="topbar">

          <div>
            <p className="eyebrow">NEXA PLATFORM / WORKSPACE</p>
            <h1>
              {isAdmin
                ? "Administrator Dashboard"
                : user.role === "property_verifier"
                ? "Property Verifier Dashboard"
                : user.role === "property_owner"
                ? "Property Owner Dashboard"
                : user.role === "property_valuer"
                ? "Property Valuer Dashboard"
                : user.role === "legal_advisor"
                ? "Legal Advisor Dashboard"
                : user.role === "compliance_officer"
                ? "Compliance Officer Dashboard"
                : user.role === "tokenization_officer"
                ? "Tokenization Officer Dashboard"
                : user.role === "property_manager"
                ? "Property Manager Dashboard"
                : user.role === "auditor"
                ? "Auditor Dashboard"
                : "Investor Dashboard"}
            </h1>
          </div>

          <div className="topbar-right">

            <span className="environment">DEMO ENVIRONMENT</span>

            <div className="avatar">
              {user.full_name?.charAt(0).toUpperCase() || "N"}
            </div>

            <div>
              <strong>{user.full_name}</strong>
              <p>{user.role}</p>
            </div>

            <button className="logout-button" onClick={handleLogout}>
              Logout
            </button>

          </div>

        </header>

        <section className="welcome">
          <div>
            <p className="eyebrow">DIGITAL ASSET INFRASTRUCTURE</p>

            <h2>Welcome to NEXA, {user.full_name}</h2>

            <p>
              {isAdmin
                ? "Manage asset verification, approval and platform oversight."
                : "Register, manage and monitor your digital asset submissions."}
            </p>
          </div>

          <div className="welcome-symbol">NEXA</div>
        </section>

        {error && <div className="error-message">{error}</div>}
        {success && <div className="success-message">{success}</div>}

        {activePage === "workflows" && canAccessWorkflows && (
          <WorkflowDashboard
            user={user}
            token={token}
            apiRequest={apiRequest}
            setError={setError}
            setSuccess={setSuccess}
          />
        )}

        {activePage === "marketplace" && user.role === "investor" && (
          <MarketplaceDashboard apiRequest={apiRequest} setError={setError} setSuccess={setSuccess} />
        )}
        {activePage === "portfolio" && user.role === "investor" && (
          <PortfolioDashboard apiRequest={apiRequest} setError={setError} />
        )}
        {activePage === "distribution" && user.role === "property_owner" && (
          <PropertyDistributionDashboard apiRequest={apiRequest} setError={setError} />
        )}
        {activePage === "management" && user.role === "property_manager" && (
          <PropertyManagerDashboard apiRequest={apiRequest} setError={setError} setSuccess={setSuccess} />
        )}
        {activePage === "notifications" && (
          <NotificationCenter apiRequest={apiRequest} setError={setError} />
        )}
        {activePage === "audit" && ["super_admin", "auditor"].includes(user.role) && (
          <AuditDashboard apiRequest={apiRequest} setError={setError} />
        )}
        {activePage === "manager-assignments" && user.role === "super_admin" && (
          <PropertyManagerAssignments apiRequest={apiRequest} setError={setError} setSuccess={setSuccess} />
        )}

        {/* OVERVIEW */}

        {activePage === "overview" && (
          <>
            <section className="section-heading">
              <div>
                <h2>Platform Summary</h2>
                <p>Your workspace at a glance.</p>
              </div>

              <button className="secondary-button" onClick={loadDashboard}>
                Refresh Data
              </button>
            </section>

            <section className="stats-grid">
              <div className="stat-card">
                <span className="stat-label">{isAdmin ? "PLATFORM ASSETS" : "MY ASSETS"}</span>
                <h3>{totalAssets}</h3>
                <p>{isAdmin ? "All registered assets" : "Assets in your account"}</p>
              </div>

              <div className="stat-card">
                <span className="stat-label">APPROVED ASSETS</span>
                <h3>{approvedAssets}</h3>
                <p>{isAdmin ? "Approved across the platform" : "Approved in your account"}</p>
              </div>

              <div className="stat-card">
                <span className="stat-label">PENDING ASSETS</span>
                <h3>{pendingAssetCount}</h3>
                <p>{isAdmin ? "Awaiting administrator review" : "Awaiting review"}</p>
              </div>

              <div className="stat-card">
                <span className="stat-label">REJECTED ASSETS</span>
                <h3>{rejectedAssetCount}</h3>
                <p>Rejected asset submissions</p>
              </div>

              <div className="stat-card">
                <span className="stat-label">TOKENISED ASSETS</span>
                <h3>{tokenisedAssets}</h3>
                <p>Assets with issued tokens</p>
              </div>

              {isAdmin && (
                <div className="stat-card">
                  <span className="stat-label">TOKEN ISSUANCES</span>
                  <h3>{issuanceCount}</h3>
                  <p>Recorded issuance transactions</p>
                </div>
              )}

              <div className="stat-card">
                <span className="stat-label">TOKEN TRANSACTIONS</span>
                <h3>{transactions.length}</h3>
                <p>{isAdmin ? "Platform-wide ledger records" : "Your ledger records"}</p>
              </div>

              {!isAdmin && (
                <>
                  <div className="stat-card">
                    <span className="stat-label">TOKEN HOLDINGS</span>
                    <h3 className="stat-value-compact">{tokenHoldingsLabel}</h3>
                    <p>Balances grouped by token symbol</p>
                  </div>
                  <div className="stat-card">
                    <span className="stat-label">PORTFOLIO VALUE</span>
                    <h3 className="stat-value-compact">{portfolioValueLabel}</h3>
                    <p>Grouped by currency; no currency conversion applied</p>
                  </div>
                </>
              )}
            </section>

            {isAdmin && (
              <section className="panel asset-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Pending Asset Reviews</h2>
                    <p>Submissions awaiting your decision.</p>
                  </div>

                  <button
                    className="secondary-button"
                    onClick={() => setActivePage("reviews")}
                  >
                    View Reviews
                  </button>
                </div>

                {pendingAssets.length === 0 ? (
                  <p className="empty-state">
                    There are currently no pending assets.
                  </p>
                ) : (
                  <div className="table-wrapper">
                    <table className="asset-table">
                      <thead>
                        <tr>
                          <th>ASSET CODE</th>
                          <th>NAME</th>
                          <th>VALUE</th>
                          <th>STATUS</th>
                        </tr>
                      </thead>

                      <tbody>
                        {pendingAssets.slice(0, 5).map((asset) => (
                          <tr key={asset.id}>
                            <td>{asset.asset_code}</td>
                            <td>{asset.name}</td>
                            <td>{money(asset)}</td>
                            <td>
                              <span className={statusClass(asset.status)}>
                                {asset.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}

            <section className="panel system-panel">
              <div className="panel-heading">
                <div>
                  <h2>System Health</h2>
                  <p>Application connectivity.</p>
                </div>
              </div>

              <div className="health-item">
                <div>
                  <h3>Frontend</h3>
                  <p>React application</p>
                </div>
                <span className="connected">Running</span>
              </div>

              <div className="health-item">
                <div>
                  <h3>Backend API</h3>
                  <p>FastAPI service</p>
                </div>

                <span className={
                  backendStatus === "Connected"
                    ? "connected"
                    : "disconnected"
                }>
                  {backendStatus}
                </span>
              </div>
            </section>
          </>
        )}

        {/* ASSET REGISTRY */}

        {activePage === "assets" && (
          <section className="panel asset-panel">

            <div className="panel-heading">
              <div>
                <h2>Asset Registry</h2>
                <p>Your registered assets.</p>
              </div>

              <span className="tag">{assets.length} ASSETS</span>
            </div>

            {loading ? (
              <p className="empty-state">Loading assets...</p>
            ) : assets.length === 0 ? (
              <p className="empty-state">
                No assets registered under this account.
              </p>
            ) : (
              <div className="table-wrapper">
                <table className="asset-table">
                  <thead>
                    <tr>
                      <th>ASSET CODE</th>
                      <th>NAME</th>
                      <th>CATEGORY</th>
                      <th>VALUE</th>
                      <th>STATUS</th>
                    </tr>
                  </thead>

                  <tbody>
                    {assets.map((asset) => (
                      <tr key={asset.id}>
                        <td>{asset.asset_code}</td>
                        <td>{asset.name}</td>
                        <td>{asset.category}</td>
                        <td>{money(asset)}</td>
                        <td>
                          <span className={statusClass(asset.status)}>
                            {asset.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

          </section>
        )}

        {/* REGISTER ASSET */}

        {activePage === "register" && canRegisterProperty && (
          <section className="panel asset-panel">

            <div className="panel-heading">
              <div>
                <h2>Register New Asset</h2>
                <p>Save property details, upload evidence, then submit for verification.</p>
              </div>

              <span className="tag">ACTIVE MODULE</span>
            </div>

            {draftAsset && (
              <div className="auth-alert error">
                <p>
                  Draft {draftAsset.asset_code} is saved and not yet submitted.
                  Select a supporting document to continue.
                </p>
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  onChange={(event) =>
                    setDocumentFile(event.target.files?.[0] || null)
                  }
                />
                <button
                  className="primary-button"
                  type="button"
                  disabled={!documentFile}
                  onClick={retryDraftSubmission}
                >
                  Upload Document and Submit Draft
                </button>
              </div>
            )}

            <form onSubmit={registerAsset}>
              <div className="form-grid">

                <div className="form-field">
                  <label>ASSET NAME</label>
                  <input
                    name="name"
                    value={form.name}
                    onChange={handleChange}
                    required
                  />
                </div>

                <div className="form-field">
                  <label>CATEGORY</label>
                  <select
                    name="category"
                    value={form.category}
                    onChange={handleChange}
                  >
                    <option>Real Estate</option>
                    <option>Agriculture</option>
                    <option>Vehicles</option>
                    <option>Equipment</option>
                    <option>Commodities</option>
                    <option>Other</option>
                  </select>
                </div>

                <div className="form-field">
                  <label>LOCATION</label>
                  <input
                    name="location"
                    value={form.location}
                    onChange={handleChange}
                    required
                  />
                </div>

                <div className="form-field">
                  <label>COUNTRY</label>
                  <input
                    name="country"
                    value={form.country}
                    onChange={handleChange}
                    maxLength="100"
                    required
                  />
                </div>

                <div className="form-field">
                  <label>JURISDICTION</label>
                  <input
                    name="jurisdiction"
                    value={form.jurisdiction}
                    onChange={handleChange}
                    maxLength="100"
                    required
                  />
                </div>

                <div className="form-field">
                  <label>PROPERTY REGISTRATION NUMBER</label>
                  <input
                    name="registration_number"
                    value={form.registration_number}
                    onChange={handleChange}
                    maxLength="100"
                    required
                  />
                </div>

                <div className="form-field">
                  <label>PROPERTY SIZE</label>
                  <input
                    type="number"
                    name="property_size"
                    value={form.property_size}
                    onChange={handleChange}
                    min="0.01"
                    step="0.01"
                    required
                  />
                </div>

                <div className="form-field">
                  <label>SIZE UNIT</label>
                  <input
                    name="property_size_unit"
                    value={form.property_size_unit}
                    onChange={handleChange}
                    maxLength="30"
                    required
                  />
                </div>

                <div className="form-field">
                  <label>ESTIMATED VALUE</label>
                  <input
                    type="number"
                    name="estimated_value"
                    min="0.01"
                    step="0.01"
                    value={form.estimated_value}
                    onChange={handleChange}
                    required
                  />
                </div>

                <div className="form-field">
                  <label>CURRENCY</label>
                  <select
                    name="currency"
                    value={form.currency}
                    onChange={handleChange}
                  >
                    <option>USD</option>
                    <option>ZWL</option>
                    <option>ZIG</option>
                  </select>
                </div>

                <div className="form-field">
                  <label>ASSET OWNER</label>
                  <input
                    name="owner_name"
                    value={form.owner_name}
                    onChange={handleChange}
                    required
                  />
                </div>

                <div className="form-field full-width">
                  <label>DESCRIPTION</label>
                  <textarea
                    name="description"
                    rows="4"
                    value={form.description}
                    onChange={handleChange}
                    required
                  />
                </div>

                <div className="form-field full-width">
                  <label>OWNERSHIP DOCUMENT (PDF, PNG OR JPEG; MAX 10 MB)</label>
                  <input
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg"
                    onChange={(event) =>
                      setDocumentFile(event.target.files?.[0] || null)
                    }
                    required={!draftAsset}
                  />
                </div>

              </div>

              <button
                className="primary-button"
                type="submit"
                disabled={Boolean(draftAsset)}
              >
                Submit Asset for Review
              </button>
            </form>

          </section>
        )}

        {/* ADMIN REVIEW QUEUE */}

        {activePage === "reviews" && isVerifier && (
          <section className="panel asset-panel">

            <div className="panel-heading">
              <div>
                <h2>Asset Verification Centre</h2>
                <p>Review and make decisions on submitted assets.</p>
              </div>

              <span className="tag">
                {pendingAssets.length} PENDING
              </span>
            </div>

            {loading ? (
              <p className="empty-state">Loading pending assets...</p>
            ) : pendingAssets.length === 0 ? (
              <p className="empty-state">
                No assets are awaiting review.
              </p>
            ) : (
              <div className="table-wrapper">
                <table className="asset-table">
                  <thead>
                    <tr>
                      <th>CODE</th>
                      <th>ASSET</th>
                      <th>CATEGORY</th>
                      <th>VALUE</th>
                      <th>ACTIONS</th>
                    </tr>
                  </thead>

                  <tbody>
                    {pendingAssets.map((asset) => (
                      <tr key={asset.id}>
                        <td>{asset.asset_code}</td>
                        <td>{asset.name}</td>
                        <td>{asset.category}</td>
                        <td>{money(asset)}</td>

                        <td className="action-cell">
                          <button
                            className="secondary-button"
                            onClick={() => openPropertyReview(asset.id)}
                          >
                            Review Details
                          </button>

                          <button
                            className="approve-button"
                            onClick={() => approveAsset(asset.id)}
                          >
                            Approve
                          </button>

                          <button
                            className="reject-button"
                            onClick={() => rejectAsset(asset.id)}
                          >
                            Reject
                          </button>

                          <button
                            className="secondary-button"
                            onClick={() => showHistory(asset.id)}
                          >
                            History
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

          </section>
        )}

        {/* REVIEW HISTORY */}

        {activePage === "history" && isVerifier && (
          <section className="panel asset-panel">

            <div className="panel-heading">
              <div>
                <h2>Asset Review History</h2>
                <p>
                  Audit records for asset {selectedAsset || "selected"}.
                </p>
              </div>
            </div>

            <div className="form-field history-lookup">
              <label>ASSET ID</label>

              <input
                type="number"
                min="1"
                value={historyAssetId}
                onChange={(event) => setHistoryAssetId(event.target.value)}
              />

              <button
                className="primary-button"
                onClick={() => showHistory(Number(historyAssetId))}
              >
                Retrieve History
              </button>
            </div>

            {reviewHistory.length === 0 ? (
              <p className="empty-state">
                No review records loaded.
              </p>
            ) : (
              <div className="table-wrapper">
                <table className="asset-table">
                  <thead>
                    <tr>
                      <th>AUDIT ID</th>
                      <th>ACTION</th>
                      <th>VERIFIER</th>
                      <th>COMMENTS</th>
                      <th>DATE</th>
                    </tr>
                  </thead>

                  <tbody>
                    {reviewHistory.map((record) => (
                      <tr key={record.id}>
                        <td>{record.id}</td>
                        <td>{record.action}</td>
                        <td>
                          {record.verifier_name
                            ? `${record.verifier_name} (#${record.verifier_user_id})`
                            : `User #${record.verifier_user_id}`}
                        </td>
                        <td>{record.comments || record.reason || "Not provided"}</td>
                        <td>
                          {new Date(record.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

          </section>
        )}

        {activePage === "review-detail" && isVerifier && selectedProperty && (
          <section className="panel asset-panel">
            <div className="panel-heading">
              <div>
                <h2>{selectedProperty.property.name}</h2>
                <p>
                  {selectedProperty.property.asset_code} ·{" "}
                  {selectedProperty.property.status}
                </p>
              </div>
              <button
                className="secondary-button"
                onClick={() => setActivePage("reviews")}
              >
                Back to Review Queue
              </button>
            </div>

            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-label">REGISTERED OWNER</span>
                <h3>{selectedProperty.property.owner_name}</h3>
              </div>
              <div className="stat-card">
                <span className="stat-label">PROPERTY LOCATION</span>
                <h3>
                  {selectedProperty.property.location},{" "}
                  {selectedProperty.property.country}
                </h3>
              </div>
              <div className="stat-card">
                <span className="stat-label">REGISTRATION</span>
                <h3>{selectedProperty.property.registration_number}</h3>
              </div>
              <div className="stat-card">
                <span className="stat-label">SUBMITTED VALUE</span>
                <h3>{money(selectedProperty.property)}</h3>
              </div>
            </div>

            <p>{selectedProperty.property.description}</p>

            <h3>Supporting documents</h3>
            {selectedProperty.documents.length === 0 ? (
              <p className="empty-state">No documents have been uploaded.</p>
            ) : (
              <div className="table-wrapper">
                <table className="asset-table">
                  <thead>
                    <tr>
                      <th>DOCUMENT</th>
                      <th>TYPE</th>
                      <th>SIZE</th>
                      <th>SHA-256</th>
                      <th>ACTION</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedProperty.documents.map((item) => (
                      <tr key={item.id}>
                        <td>{item.original_filename}</td>
                        <td>{item.content_type}</td>
                        <td>{formatDecimalString(item.file_size, 0)} bytes</td>
                        <td>{item.sha256}</td>
                        <td>
                          <button
                            className="secondary-button"
                            onClick={() => downloadPropertyDocument(item)}
                          >
                            Download
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="action-cell">
              <button
                className="approve-button"
                onClick={() => approveAsset(selectedProperty.property.id)}
              >
                Approve Verification
              </button>
              <button
                className="reject-button"
                onClick={() => rejectAsset(selectedProperty.property.id)}
              >
                Reject
              </button>
              <button
                className="secondary-button"
                onClick={() =>
                  requestAdditionalDocuments(selectedProperty.property.id)
                }
              >
                Request Documents
              </button>
            </div>
          </section>
        )}

        {activePage === "users" && isAdmin && (
          <>
            <section className="panel asset-panel">
              <div className="panel-heading">
                <div>
                  <h2>User Management</h2>
                  <p>Assign roles and manage account access.</p>
                </div>
                <button className="secondary-button" onClick={loadUsers}>
                  Refresh
                </button>
              </div>
              <div className="table-wrapper">
                <table className="asset-table">
                  <thead>
                    <tr>
                      <th>USER</th>
                      <th>EMAIL</th>
                      <th>ROLE</th>
                      <th>STATUS</th>
                      <th>ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {managedUsers.map((managedUser) => (
                      <tr key={managedUser.id}>
                        <td>{managedUser.full_name}</td>
                        <td>{managedUser.email}</td>
                        <td>
                          <select
                            value={managedUser.role}
                            disabled={managedUser.id === user.id}
                            onChange={(event) =>
                              updateManagedUser(managedUser, {
                                role: event.target.value
                              })
                            }
                          >
                            {managedUser.role === "admin" && (
                              <option value="admin" disabled>
                                Super Admin (legacy)
                              </option>
                            )}
                            {[
                              ["super_admin", "Super Admin"],
                              ["property_owner", "Property Owner"],
                              ["property_verifier", "Property Verifier"],
                              ["property_valuer", "Property Valuer"],
                              ["legal_advisor", "Legal Advisor"],
                              ["compliance_officer", "Compliance Officer"],
                              ["tokenization_officer", "Tokenization Officer"],
                              ["investor", "Investor"],
                              ["property_manager", "Property Manager"],
                              ["auditor", "Auditor"]
                            ].map(([value, label]) => (
                              <option key={value} value={value}>{label}</option>
                            ))}
                          </select>
                        </td>
                        <td>{managedUser.is_active ? "Active" : "Suspended"}</td>
                        <td>
                          <button
                            className={
                              managedUser.is_active
                                ? "reject-button"
                                : "approve-button"
                            }
                            disabled={managedUser.id === user.id}
                            onClick={() =>
                              updateManagedUser(managedUser, {
                                is_active: !managedUser.is_active
                              })
                            }
                          >
                            {managedUser.is_active ? "Suspend" : "Activate"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="panel asset-panel">
              <div className="panel-heading">
                <div>
                  <h2>Recent Audit Events</h2>
                  <p>Account registration, role, and status changes.</p>
                </div>
              </div>
              <div className="table-wrapper">
                <table className="asset-table">
                  <thead>
                    <tr>
                      <th>ACTION</th>
                      <th>ENTITY</th>
                      <th>USER ID</th>
                      <th>DATE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditEvents.map((event) => (
                      <tr key={event.id}>
                        <td>{event.action}</td>
                        <td>{event.entity_type} #{event.entity_id}</td>
                        <td>{event.user_id ?? "System"}</td>
                        <td>{new Date(event.created_at).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
        {/* TOKENISATION AND TRANSACTION MODULES */}

        {activePage === "tokens" && (
          <section className="panel asset-panel">

            <div className="panel-heading">
              <div>
                <h2>
                  {isAdmin ? "Token Issuance" : "My Token Portfolio"}
                </h2>

                <p>
                  {isAdmin
                    ? "View issuance records. New issuance must pass the staged approval workflow."
                    : "View your token holdings and transfer tokens to other investors."}
                </p>
              </div>

              <span className="tag">
                {isAdmin ? "ADMINISTRATOR" : "INVESTOR"}
              </span>
            </div>
            {isAdmin && (
              <div className="form-hint">
                Token issuance is now gated by approved valuation, legal and compliance
                reviews, a reviewed proposal, and separate final authorisation. Use the
                Valuation &amp; Approvals workspace for the complete workflow.
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setActivePage("workflows")}
                >
                  Open approval workflow
                </button>
              </div>
            )}

            {isAdmin ? (

              <>
                <h3>Issue New Tokens</h3>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={loadApprovedAssets}
                  disabled={isIssuing}
                >
                  Refresh Approved Assets
                </button>

                {issuanceApprovedAssets.length === 0 ? (
                  <div className="empty-state">
                    No approved assets are currently available for token issuance.
                  </div>
                ) : (
                  <form onSubmit={issueTokens}>
                    <div className="form-grid">
                      <div className="form-group">
                        <label>Select Approved Asset</label>
                        <select
                          value={issuanceForm.asset_id}
                          onChange={(event) =>
                            setIssuanceForm({
                              ...issuanceForm,
                              asset_id: event.target.value
                            })
                          }
                          required
                        >
                          <option value="">Select an asset</option>
                          {issuanceApprovedAssets.map((asset) => (
                            <option key={asset.id} value={asset.id}>
                              {asset.name} - {asset.asset_code}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="form-group">
                        <label>Token Name</label>

                        <input
                          type="text"
                          value={issuanceForm.token_name}
                          onChange={(event) =>
                            setIssuanceForm({
                              ...issuanceForm,
                              token_name: event.target.value
                            })
                          }
                          placeholder="e.g. NEXA Property Token"
                          required
                        />
                      </div>

                      <div className="form-group">
                        <label>Token Symbol</label>

                        <input
                          type="text"
                          value={issuanceForm.token_symbol}
                          onChange={(event) =>
                            setIssuanceForm({
                              ...issuanceForm,
                              token_symbol: event.target.value.toUpperCase()
                            })
                          }
                          placeholder="e.g. NPT"
                          maxLength={20}
                          required
                        />
                      </div>

                      <div className="form-group">
                        <label>
                          Price Per Token (
                          {issuanceApprovedAssets.find(
                            (asset) => String(asset.id) === issuanceForm.asset_id
                          )?.currency || "asset currency"}
                          )
                        </label>
                        <input
                          type="number"
                          min="0.00000001"
                          step="0.00000001"
                          value={issuanceForm.token_price}
                          onChange={(event) =>
                            setIssuanceForm({
                              ...issuanceForm,
                              token_price: event.target.value
                            })
                          }
                          required
                        />
                      </div>
                    </div>

                    <p className="form-hint" aria-live="polite">
                      Calculated token supply:{" "}
                      {(() => {
                        const selected = issuanceApprovedAssets.find(
                          (asset) => String(asset.id) === issuanceForm.asset_id
                        );
                        if (!selected || !issuanceForm.token_price) {
                          return "Select an asset and enter a price.";
                        }
                        return exactTokenSupply(
                          selected.estimated_value,
                          issuanceForm.token_price
                        ) || "Price does not divide the asset value exactly to 8 decimals.";
                      })()}
                    </p>

                    <button
                      type="submit"
                      className="primary-button"
                      disabled={isIssuing || issuanceApprovedAssets.length === 0}
                    >
                      {isIssuing ? "Issuing Tokens..." : "Issue Tokens"}
                    </button>
                  </form>
                )}

                {issuanceResult && (
                  <section className="success-panel" aria-live="polite">
                    <h3>Issuance Completed</h3>
                    <dl className="result-grid">
                      <div><dt>Asset</dt><dd>{issuanceResult.asset_name}</dd></div>
                      <div><dt>Updated Asset Status</dt><dd>{issuanceResult.asset_status || "Tokenised"}</dd></div>
                      <div><dt>Token</dt><dd>{issuanceResult.token_name}</dd></div>
                      <div><dt>Symbol</dt><dd>{issuanceResult.token_symbol}</dd></div>
                      <div>
                        <dt>Token Price</dt>
                        <dd>{issuanceResult.currency} {issuanceResult.token_price}</dd>
                      </div>
                      <div><dt>Total Supply</dt><dd>{issuanceResult.total_supply}</dd></div>
                      <div>
                        <dt>Allocated Owner</dt>
                        <dd>{issuanceResult.allocated_to?.full_name || "Unavailable"}</dd>
                      </div>
                      <div className="full-width">
                        <dt>Transaction Reference</dt>
                        <dd className="reference-text">{issuanceResult.transaction_ref}</dd>
                      </div>
                    </dl>
                  </section>
                )}

                <h3>Approved Assets Available</h3>

                <div className="table-wrapper">
                  <table className="asset-table">
                    <thead>
                      <tr>
                        <th>Asset</th>
                        <th>Asset Code</th>
                        <th>Owner</th>
                        <th>Estimated Value</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {issuanceApprovedAssets.map((asset) => (
                        <tr key={asset.id}>
                          <td>{asset.name}</td>
                          <td>{asset.asset_code}</td>
                          <td>{asset.owner_name}</td>
                          <td>
                            {asset.currency} {formatDecimalString(asset.estimated_value, 2)}
                          </td>
                          <td>
                            <span className="tag">Approved</span>
                          </td>
                        </tr>
                      ))}

                      {issuanceApprovedAssets.length === 0 && (
                        <tr>
                          <td colSpan="5">
                            No approved assets available.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

              </>

            ) : (

              <>
                <h3>My Token Holdings</h3>

                <section className="stats-grid portfolio-summary">
                  <div className="stat-card">
                    <span className="stat-label">TOTAL TOKEN HOLDINGS</span>
                    <h3 className="stat-value-compact">{tokenHoldingsLabel}</h3>
                    <p>Balances grouped by token symbol</p>
                  </div>
                  <div className="stat-card">
                    <span className="stat-label">TOKENISED ASSETS</span>
                    <h3>
                      {new Set(holdings.map((holding) => holding.asset_id)).size}
                    </h3>
                    <p>Assets represented in your portfolio</p>
                  </div>
                  <div className="stat-card">
                    <span className="stat-label">PORTFOLIO VALUE</span>
                    <h3 className="stat-value-compact">{portfolioValueLabel}</h3>
                    <p>Grouped by currency; no currency conversion applied</p>
                  </div>
                </section>

                <div className="table-wrapper">
                  <table className="asset-table">
                    <thead>
                      <tr>
                        <th>Asset</th>
                        <th>Asset Code</th>
                        <th>Token Name</th>
                        <th>Symbol</th>
                        <th>Balance</th>
                        <th>Price Per Token</th>
                        <th>Holding Value</th>
                        <th>Last Updated</th>
                      </tr>
                    </thead>

                    <tbody>
                      {holdings.map((holding) => (
                        <tr key={holding.holding_id}>
                          <td>{holding.asset_name}</td>
                          <td>{holding.asset_code}</td>
                          <td>{holding.token_name}</td>
                          <td>{holding.token_symbol}</td>
                          <td>
                            {formatDecimalString(holding.balance, 8)}
                          </td>
                          <td>
                            {holding.currency} {formatDecimalString(holding.token_price, 8)}
                          </td>
                          <td>
                            {holding.currency} {formatDecimalString(holding.holding_value, 2)}
                          </td>
                          <td>
                            {holding.updated_at
                              ? new Date(holding.updated_at).toLocaleString()
                              : "Not available"}
                          </td>
                        </tr>
                      ))}

                      {holdings.length === 0 && (
                        <tr>
                          <td colSpan="8">
                            You currently have no token holdings.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                <h3>Transfer Tokens</h3>

                <form onSubmit={transferTokens}>

                  <div className="form-grid">

                    <div className="form-group">
                      <label>Select Token</label>

                      <select
                        value={transferForm.issuance_id}
                        onChange={(event) =>
                          setTransferForm({
                            ...transferForm,
                            issuance_id: event.target.value
                          })
                        }
                        required
                      >
                        <option value="">Select token</option>

                        {holdings
                          .filter((holding) => compareDecimalStrings(holding.balance, "0") > 0)
                          .map((holding) => (
                            <option
                              key={holding.issuance_id}
                              value={holding.issuance_id}
                            >
                              {holding.token_symbol} - {holding.asset_name}
                              {" | Balance: "}
                              {formatDecimalString(holding.balance, 8)}
                            </option>
                          ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Recipient Investor</label>

                      <select
                        value={transferForm.recipient_user_id}
                        onChange={(event) =>
                          setTransferForm({
                            ...transferForm,
                            recipient_user_id: event.target.value
                          })
                        }
                        required
                      >
                        <option value="">Select recipient</option>

                        {investors.map((investor) => (
                          <option key={investor.id} value={investor.id}>
                            {investor.full_name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Number of Tokens</label>

                      <input
                        type="number"
                        min="0.00000001"
                        step="0.00000001"
                        max={holdings.find(
                          (holding) =>
                            String(holding.issuance_id) === transferForm.issuance_id
                        )?.balance}
                        value={transferForm.amount}
                        onChange={(event) =>
                          setTransferForm({
                            ...transferForm,
                            amount: event.target.value
                          })
                        }
                        placeholder="Enter amount"
                        required
                      />
                    </div>

                  </div>

                  <button
                    type="submit"
                    className="primary-button"
                    disabled={isTransferring}
                  >
                    {isTransferring ? "Transferring..." : "Transfer Tokens"}
                  </button>

                </form>

              </>

            )}

          </section>
        )}

        {/* TRANSACTION LEDGER */}

        {activePage === "ledger" && (
          <section className="panel asset-panel">

            <div className="panel-heading">
              <div>
                <h2>Transaction Ledger</h2>

                <p>
                  {isAdmin
                    ? "Complete record of all token issuance and transfer transactions."
                    : "Your token issuance and transfer history."}
                </p>
              </div>

              <span className="tag">TRANSACTION RECORDS</span>
            </div>

            <div className="ledger-filters">
              <label>
                Search reference
                <input
                  type="search"
                  value={ledgerSearch}
                  onChange={(event) => setLedgerSearch(event.target.value)}
                  placeholder="Search transaction reference"
                />
              </label>
              <label>
                Transaction type
                <select
                  value={ledgerTypeFilter}
                  onChange={(event) => setLedgerTypeFilter(event.target.value)}
                >
                  <option value="">All types</option>
                  {[...new Set(transactions.map((item) => item.transaction_type))]
                    .filter(Boolean)
                    .sort()
                    .map((type) => (
                      <option key={type} value={type.toUpperCase()}>{type}</option>
                    ))}
                </select>
              </label>
              <label>
                Asset or token
                <select
                  value={ledgerAssetFilter}
                  onChange={(event) => setLedgerAssetFilter(event.target.value)}
                >
                  <option value="">All assets and tokens</option>
                  {[...new Set(
                    transactions.map(
                      (item) => `${item.asset_name} ${item.token_symbol}`
                    )
                  )]
                    .sort()
                    .map((assetToken) => (
                      <option key={assetToken} value={assetToken}>{assetToken}</option>
                    ))}
                </select>
              </label>
              <label>
                Sort by date
                <select
                  value={ledgerSortOrder}
                  onChange={(event) => setLedgerSortOrder(event.target.value)}
                >
                  <option value="newest">Newest first</option>
                  <option value="oldest">Oldest first</option>
                </select>
              </label>
              <button
                type="button"
                className="secondary-button"
                onClick={loadTransactions}
              >
                Refresh Ledger
              </button>
            </div>

            <div className="table-wrapper">

              <table className="asset-table">

                <thead>
                  <tr>
                    <th>Transaction Reference</th>
                    <th>Type</th>
                    <th>Asset</th>
                    <th>Token</th>
                    <th>Amount</th>
                    <th>From</th>
                    <th>To</th>

                    {!isAdmin && <th>Direction</th>}

                    <th>Date</th>
                  </tr>
                </thead>

                <tbody>

                  {filteredTransactions.map((transaction, index) => (
                    <tr key={transaction.transaction_ref || index}>

                      <td className="reference-text">{transaction.transaction_ref}</td>

                      <td>{transaction.transaction_type}</td>

                      <td>{transaction.asset_name}</td>

                      <td>{transaction.token_symbol}</td>

                      <td>
                        {formatDecimalString(transaction.amount, 8)}
                      </td>

                      <td>
                        {transaction.from_user?.full_name || "Token Issuance"}
                      </td>

                      <td>
                        {transaction.to_user?.full_name || "N/A"}
                      </td>

                      {!isAdmin && (
                        <td>{transaction.direction}</td>
                      )}

                      <td>
                        {transaction.created_at
                          ? new Date(transaction.created_at).toLocaleString()
                          : "Not available"}
                      </td>

                    </tr>
                  ))}

                  {filteredTransactions.length === 0 && (
                    <tr>
                      <td colSpan={isAdmin ? 8 : 9}>
                        {transactions.length === 0
                          ? "No transaction records available."
                          : "No transactions match the selected filters."}
                      </td>
                    </tr>
                  )}

                </tbody>

              </table>

            </div>

          </section>
        )}

 

        <footer>
          <span>NEXA Tokenisation Platform</span>
          <span>Demonstration Build · Version 1.0.0</span>
        </footer>

      </main>
    </div>
  );
}

export default App;