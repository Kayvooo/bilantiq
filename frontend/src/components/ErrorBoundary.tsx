import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  fehler: boolean;
}

/** Fängt unerwartete Darstellungsfehler (z. B. eine Serverantwort in unerwarteter Form) ab. Ohne diese Grenze
 * entfernt React bei einem Fehler im Rendern die gesamte Oberfläche und es bleibt eine leere Seite. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { fehler: false };

  static getDerivedStateFromError(): State {
    return { fehler: true };
  }

  componentDidCatch(fehler: Error, info: ErrorInfo) {
    console.error("Unerwarteter Darstellungsfehler", fehler, info.componentStack);
  }

  render() {
    if (!this.state.fehler) return this.props.children;
    return (
      <main className="app-shell app-shell--auth" id="main-content">
        <div className="auth-card">
          <h1>Das hat nicht geklappt</h1>
          <p className="auth-hint">Beim Anzeigen der Seite ist ein unerwarteter Fehler aufgetreten. Bereits gespeicherte Daten sind nicht betroffen, nicht gespeicherte Eingaben können aber verloren gehen. Lade die Seite neu und versuche es noch einmal.</p>
          <button type="button" className="button-primary" onClick={() => window.location.reload()}>Seite neu laden</button>
        </div>
      </main>
    );
  }
}
