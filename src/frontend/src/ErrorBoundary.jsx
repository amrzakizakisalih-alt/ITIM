import { Component } from "react";
import { T } from "./constants";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100vh",
            background: T.darkBg,
            color: T.textPri,
            fontFamily: "'DM Sans', sans-serif",
            padding: 40,
            textAlign: "center",
          }}
        >
          <h1 style={{ fontSize: 48, marginBottom: 16 }}>😵</h1>
          <h2 style={{ fontSize: 20, marginBottom: 8 }}>Something went wrong</h2>
          <p style={{ color: T.textSec, fontSize: 14, maxWidth: 400 }}>
            The application crashed unexpectedly. Try refreshing the page.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: 24,
              padding: "10px 20px",
              background: T.accent,
              color: "#fff",
              border: "none",
              borderRadius: 8,
              cursor: "pointer",
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            Reload Page
          </button>
          {process.env.NODE_ENV === "development" && this.state.error && (
            <pre
              style={{
                marginTop: 24,
                padding: 16,
                background: T.surface,
                borderRadius: 8,
                color: T.redHint,
                fontSize: 11,
                maxWidth: 600,
                overflow: "auto",
                textAlign: "left",
              }}
            >
              {this.state.error.toString()}
            </pre>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}
