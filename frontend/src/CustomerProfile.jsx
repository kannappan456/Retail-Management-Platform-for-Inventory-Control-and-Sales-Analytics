import { useCallback, useEffect, useState } from "react";
import { Users } from "lucide-react";
import api from "./services/api";

function CustomerProfile({ onProfileUpdate }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  // Edit form state
  const [editEmail, setEditEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [saveError, setSaveError] = useState("");

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const response = await api.get("/auth/me");
      setProfile(response.data);
      setEditEmail(response.data.email || "");
    } catch (err) {
      setLoadError(
        err.response?.data?.detail ||
          "Could not load your profile. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadProfile);
  }, [loadProfile]);

  async function handleSave(event) {
    event.preventDefault();
    setSaveError("");
    setSaveMessage("");

    const isChangingEmail =
      editEmail.trim() && editEmail.trim() !== profile?.email;
    const isChangingPassword = newPassword.length > 0;

    if (!isChangingEmail && !isChangingPassword) {
      setSaveMessage("No changes to save.");
      return;
    }

    if (isChangingPassword) {
      if (!currentPassword) {
        setSaveError("Enter your current password to set a new one.");
        return;
      }
      if (newPassword.length < 8) {
        setSaveError("New password must be at least 8 characters.");
        return;
      }
      if (newPassword !== confirmPassword) {
        setSaveError("New passwords do not match.");
        return;
      }
    }

    const payload = {};
    if (isChangingEmail) payload.email = editEmail.trim();
    if (isChangingPassword) {
      payload.current_password = currentPassword;
      payload.new_password = newPassword;
    }

    setSaving(true);
    try {
      const response = await api.patch("/auth/me", payload);
      setProfile(response.data);
      setEditEmail(response.data.email || "");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setSaveMessage(response.data.message || "Profile updated.");
      // Let the parent know so the top-bar avatar can re-read the email.
      if (onProfileUpdate) onProfileUpdate(response.data);
    } catch (err) {
      setSaveError(
        err.response?.data?.detail || "Could not save profile changes."
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="activity-card" role="status">
        <p style={{ color: "#9296aa" }}>Loading your profile…</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="activity-card" role="alert">
        <p style={{ color: "#ff9ba4" }}>{loadError}</p>
        <button className="secondary-button" onClick={loadProfile}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="profile-page">
      <div className="form-card profile-card">
        <div className="profile-avatar-row">
          <div className="profile-avatar">
            {profile?.email?.charAt(0).toUpperCase() || "?"}
          </div>
          <div>
            <h2>My Profile</h2>
            <p>
              Account type:{" "}
              <strong style={{ color: "#c1b8ff" }}>{profile?.role}</strong>
            </p>
          </div>
        </div>

        <div className="profile-info-row">
          <Users size={16} />
          <span>
            User ID: <strong>{profile?.user_id}</strong>
          </span>
        </div>

        <form onSubmit={handleSave}>
          <label>Email address</label>
          <input
            type="email"
            value={editEmail}
            onChange={(e) => setEditEmail(e.target.value)}
            required
            maxLength={150}
            placeholder="you@example.com"
          />

          <p className="profile-section-label">Change password (optional)</p>

          <label>Current password</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            maxLength={72}
            placeholder="Required only when changing password"
            autoComplete="current-password"
          />

          <label>New password</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            minLength={newPassword ? 8 : undefined}
            maxLength={72}
            placeholder="8+ characters"
            autoComplete="new-password"
          />

          <label>Confirm new password</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            maxLength={72}
            placeholder="Repeat new password"
            autoComplete="new-password"
          />

          {saveError && (
            <p
              role="alert"
              style={{ color: "#ff9ba4", fontSize: "13px", margin: "4px 0" }}
            >
              {saveError}
            </p>
          )}

          {saveMessage && (
            <p
              role="status"
              style={{ color: "#65d5a1", fontSize: "13px", margin: "4px 0" }}
            >
              {saveMessage}
            </p>
          )}

          <div className="form-actions">
            <button
              type="submit"
              className="primary-button"
              disabled={saving}
            >
              {saving ? "Saving…" : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default CustomerProfile;
