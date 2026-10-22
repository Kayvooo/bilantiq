import { AuthFlow } from "./features/auth/AuthFlow";
import { BestaetigungsDialog } from "./features/auth/BestaetigungsDialog";
import { DemoApp } from "./features/demo/DemoApp";
import { ErrorBoundary } from "./components/ErrorBoundary";

export default function App() {
  return (
    <ErrorBoundary>
      {import.meta.env.VITE_PUBLIC_PREVIEW === "true" ? (
        <DemoApp />
      ) : (
        <>
          <AuthFlow />
          <BestaetigungsDialog />
        </>
      )}
    </ErrorBoundary>
  );
}
