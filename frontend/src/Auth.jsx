import { useState } from "react";
import api from "./services/api";
import "./Auth.css";

function Auth({ onLogin }) {
  const [isLogin, setIsLogin] = useState(true);
  const [role, setRole] = useState("Customer");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [businessName, setBusinessName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [phone, setPhone] = useState("");
  const [category, setCategory] = useState("");

  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage("");
    setLoading(true);

    try {
      if (isLogin) {
        const response = await api.post("/auth/login", {
          email,
          password,
        });

        onLogin(response.data);
      } else {
        const registrationData = {
          email,
          password,
          role,
        };

        if (role === "Vendor") {
          registrationData.business_name = businessName;
          registrationData.owner_name = ownerName;
          registrationData.phone = phone || null;
          registrationData.category = category || null;
        }

        await api.post("/auth/register", registrationData);

        if (role === "Vendor") {
          setMessage(
            "Vendor registration submitted! Your account is pending approval."
          );
        } else {
          setMessage("Account created successfully! Please log in.");
        }

        setIsLogin(true);
        setPassword("");
      }
    } catch (error) {
      const detail = error.response?.data?.detail;

      setMessage(
        typeof detail === "string"
          ? detail
          : "Something went wrong. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">ShopSense</div>

        <h1>{isLogin ? "Welcome Back" : "Create Your Account"}</h1>

        <p className="auth-subtitle">
          {isLogin
            ? "Sign in to continue to your marketplace."
            : "Join ShopSense and get started."}
        </p>

        <div className="auth-tabs">
          <button
            type="button"
            className={isLogin ? "active" : ""}
            onClick={() => {
              setIsLogin(true);
              setMessage("");
            }}
          >
            Login
          </button>

          <button
            type="button"
            className={!isLogin ? "active" : ""}
            onClick={() => {
              setIsLogin(false);
              setMessage("");
            }}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {!isLogin && (
            <div className="auth-field">
              <label>Account Type</label>

              <select
                value={role}
                onChange={(event) => {
                  setRole(event.target.value);
                  setMessage("");
                }}
              >
                <option value="Customer">Customer</option>
                <option value="Vendor">Vendor</option>
              </select>
            </div>
          )}

          {!isLogin && role === "Vendor" && (
            <>
              <div className="auth-field">
                <label>Business Name</label>

                <input
                  type="text"
                  placeholder="Enter your business name"
                  value={businessName}
                  onChange={(event) =>
                    setBusinessName(event.target.value)
                  }
                  minLength={2}
                  maxLength={100}
                  required
                />
              </div>

              <div className="auth-field">
                <label>Owner Name</label>

                <input
                  type="text"
                  placeholder="Enter the owner's name"
                  value={ownerName}
                  onChange={(event) =>
                    setOwnerName(event.target.value)
                  }
                  minLength={2}
                  maxLength={100}
                  required
                />
              </div>

              <div className="auth-field">
                <label>Phone Number (Optional)</label>

                <input
                  type="tel"
                  placeholder="Enter your phone number"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  maxLength={20}
                />
              </div>

              <div className="auth-field">
                <label>Business Category (Optional)</label>

                <select
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                >
                  <option value="">Select a category</option>
                  <option value="Electronics">Electronics</option>
                  <option value="Fashion">Fashion</option>
                  <option value="Home & Living">Home & Living</option>
                  <option value="Books">Books</option>
                  <option value="Other">Other</option>
                </select>
              </div>
            </>
          )}

          <div className="auth-field">
            <label>Email Address</label>

            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>

          <div className="auth-field">
            <label>Password</label>

            <input
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={isLogin ? undefined : 8}
              maxLength={72}
              required
            />
          </div>

          {message && (
            <div className="auth-message" role="alert">
              {message}
            </div>
          )}

          <button
            className="auth-submit"
            type="submit"
            disabled={loading}
          >
            {loading
              ? "Please wait..."
              : isLogin
              ? "Sign In"
              : "Create Account"}
          </button>
        </form>

        <p className="auth-footer">
          Multi-Vendor E-Commerce Analytics Platform
        </p>
      </div>
    </div>
  );
}

export default Auth;