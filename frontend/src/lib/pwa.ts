import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export function registerServiceWorker() {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Ohne Service Worker laeuft Bilantiq normal im Browser weiter.
    });
  });
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function isIosSafari(): boolean {
  const ua = navigator.userAgent;
  const isIos = /iPad|iPhone|iPod/.test(ua) || (ua.includes("Mac") && navigator.maxTouchPoints > 1);
  return isIos && !/CriOS|FxiOS|EdgiOS/.test(ua);
}

export type InstallState =
  | { kind: "installed" }
  | { kind: "prompt"; install: () => Promise<void> }
  | { kind: "ios-hint" }
  | { kind: "unavailable" };

export function useInstallState(): InstallState {
  const [installed, setInstalled] = useState(isStandalone);
  const [promptEvent, setPromptEvent] = useState<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    function onBeforeInstallPrompt(event: Event) {
      event.preventDefault();
      setPromptEvent(event as BeforeInstallPromptEvent);
    }
    function onInstalled() {
      setInstalled(true);
      setPromptEvent(null);
    }
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (installed) return { kind: "installed" };
  if (promptEvent) {
    return {
      kind: "prompt",
      install: async () => {
        await promptEvent.prompt();
        await promptEvent.userChoice;
        setPromptEvent(null);
      },
    };
  }
  if (isIosSafari()) return { kind: "ios-hint" };
  return { kind: "unavailable" };
}
