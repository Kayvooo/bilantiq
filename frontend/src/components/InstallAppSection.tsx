import { useInstallState } from "../lib/pwa";
import { GroupedListRow, GroupedListSection } from "./GroupedList";

export function InstallAppSection() {
  const state = useInstallState();
  if (state.kind === "installed" || state.kind === "unavailable") return null;

  return (
    <GroupedListSection title="App">
      {state.kind === "prompt" ? (
        <GroupedListRow
          label="Bilantiq installieren"
          description="Als App auf dem Startbildschirm, ohne Browserleiste"
          onClick={() => void state.install()}
        />
      ) : (
        <p className="auth-hint install-hint">
          Bilantiq als App nutzen: In Safari auf das Teilen-Symbol tippen und „Zum Home-Bildschirm“ wählen.
        </p>
      )}
    </GroupedListSection>
  );
}
