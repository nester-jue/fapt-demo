import React, { useEffect, useState } from "react";

export default function NotificationCenter({ apiRequest, setError }) {
  const [data, setData] = useState({ items: [], unread_count: 0 });
  const load = () => apiRequest("/notifications?limit=100").then(setData).catch((error) => setError(error.message));
  useEffect(() => { load(); }, []);
  const markRead = async (id) => {
    try {
      await apiRequest(`/notifications/${id}/read`, { method: "POST" });
      await load();
    } catch (error) { setError(error.message); }
  };
  return <section className="panel asset-panel">
    <div className="panel-heading"><div><h2>Notifications</h2><p>In-app workflow, investment and account activity. No email or SMS delivery is simulated.</p></div><span className="tag">{data.unread_count} UNREAD</span></div>
    {data.items.length === 0 ? <div className="empty-state">You have no notifications.</div> : <div className="notification-list">{data.items.map((item) => <article className={item.is_read ? "notification-item read" : "notification-item"} key={item.id}><div><strong>{item.event_type.replaceAll("_", " ")}</strong><p>{item.message}</p><time>{new Date(item.created_at).toLocaleString()}</time></div>{!item.is_read && <button className="secondary-button" onClick={() => markRead(item.id)}>Mark read</button>}</article>)}</div>}
  </section>;
}
