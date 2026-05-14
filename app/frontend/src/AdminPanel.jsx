import React, { useEffect, useState } from "react";
import styles from "./style/Admin.module.css";

const AdminPanel = ({ token, onBack }) => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchUsers = async () => {
    try {
      const res = await fetch("http://localhost:8000/users/all_users", {
        headers: { Authorization: `Bearer ${token}` },
      });
      console.log("Users:", res);
      const data = await res.json();
      setUsers(data);
      setLoading(false);
    } catch (err) {
      alert("Failed to load users");
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleDelete = async (userId) => {
    if (!window.confirm("Delete this user?")) return;
    await fetch(`http://localhost:8000/users/${userId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    fetchUsers(); // Refresh list
  };

  const toggleAdmin = async (user) => {
    const newRole = user.role === "admin" ? "user" : "admin";
    await fetch(`http://localhost:8000/users/${user.id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ role: newRole }),
    });
    fetchUsers();
  };

  if (loading) return <div>Loading Admin Dashboard...</div>;

  return (
    <div className={styles.adminContainer}>
      <header className={styles.header}>
        <button onClick={onBack}>← Back</button>
        <h2>User Management</h2>
      </header>
      <table className={styles.userTable}>
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Translations</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td>
              <td>
                <span className={styles.roleBadge}>{u.role}</span>
              </td>
              <td>{u.translations?.length || 0}</td>
              <td>
                <button onClick={() => toggleAdmin(u)}>Change Role</button>
                <button
                  className={styles.deleteBtn}
                  onClick={() => handleDelete(u.id)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default AdminPanel;
