import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUpIcon, SparkleIcon } from "../../components/icons";
import { ApiError } from "../auth/api";
import { askAssistant } from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
}

interface Message {
  role: "user" | "assistant";
  text: string;
  tool?: string;
  fehler?: boolean;
}

const VORSCHLAEGE = [
  "Welche Rechnungen sind überfällig?",
  "Wie hoch war mein Gewinn dieses Jahr?",
  "Wie viel habe ich für Software ausgegeben?",
  "Wie sieht meine Umsatzsteuer-Voranmeldung aus?",
];

const MAX_HOEHE = 200;

export function AssistantPage({ accessToken, onBack }: Props) {
  const [frage, setFrage] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [laedt, setLaedt] = useState(false);
  const eingabeRef = useRef<HTMLTextAreaElement>(null);
  const endeRef = useRef<HTMLDivElement>(null);

  const leer = messages.length === 0;

  useEffect(() => {
    endeRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, laedt]);

  useEffect(() => {
    const feld = eingabeRef.current;
    if (!feld) return;
    feld.style.height = "auto";
    feld.style.height = `${Math.min(feld.scrollHeight, MAX_HOEHE)}px`;
    feld.style.overflowY = feld.scrollHeight > MAX_HOEHE ? "auto" : "hidden";
  }, [frage]);

  async function sende(text: string) {
    const bereinigt = text.trim();
    if (!bereinigt || laedt) return;
    setMessages((prev) => [...prev, { role: "user", text: bereinigt }]);
    setFrage("");
    setLaedt(true);
    try {
      const result = await askAssistant(accessToken, bereinigt);
      setMessages((prev) => [...prev, { role: "assistant", text: result.antwort, tool: result.tool }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", fehler: true, text: err instanceof ApiError ? err.message : "Der KI-Assistent konnte nicht antworten." },
      ]);
    } finally {
      setLaedt(false);
      eingabeRef.current?.focus();
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void sende(frage);
  }

  function handleKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void sende(frage);
    }
  }

  const eingabe = (
    <form className="chat-eingabe" onSubmit={handleSubmit}>
      <textarea
        ref={eingabeRef}
        rows={1}
        value={frage}
        onChange={(e) => setFrage(e.target.value)}
        onKeyDown={handleKey}
        placeholder="Frag Bilantiq …"
        aria-label="Frage an Bilantiq"
        maxLength={2000}
        autoFocus
      />
      <button type="submit" className="chat-senden" disabled={laedt || !frage.trim()} aria-label="Frage senden">
        <ArrowUpIcon width={20} height={20} />
      </button>
    </form>
  );

  return (
    <div className={`chat-seite${leer ? " chat-seite--leer" : ""}`}>
      <div className="chat-kopf">
        <button type="button" className="auth-link back-link" onClick={onBack}>← Zurück</button>
        {!leer && (
          <button type="button" className="auth-link" onClick={() => { setMessages([]); setFrage(""); }}>
            Neuer Chat
          </button>
        )}
      </div>

      {leer ? (
        <div className="chat-start">
          <span className="chat-start-symbol" aria-hidden="true"><SparkleIcon width={28} height={28} /></span>
          <h1>Wie kann ich dir helfen?</h1>
          <p className="chat-start-hinweis">Ich lese deine Bilantiq-Daten und erkläre sie. Ich ändere nichts.</p>
          {eingabe}
          <div className="chat-vorschlaege">
            {VORSCHLAEGE.map((vorschlag) => (
              <button key={vorschlag} type="button" className="chat-vorschlag" onClick={() => void sende(vorschlag)} disabled={laedt}>
                {vorschlag}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
          <div className="chat-verlauf" aria-live="polite">
            {messages.map((message, index) => (
              <div key={index} className={`chat-nachricht chat-nachricht--${message.role}${message.fehler ? " chat-nachricht--fehler" : ""}`}>
                {message.role === "assistant" && (
                  <span className="chat-avatar" aria-hidden="true"><SparkleIcon width={16} height={16} /></span>
                )}
                <div className="chat-inhalt">
                  <p role={message.fehler ? "alert" : undefined}>{message.text}</p>
                  {message.tool && message.tool !== "keine" && <span className="chat-quelle">Datenquelle: {message.tool.replace(/_/g, " ")}</span>}
                </div>
              </div>
            ))}
            {laedt && (
              <div className="chat-nachricht chat-nachricht--assistant">
                <span className="chat-avatar" aria-hidden="true"><SparkleIcon width={16} height={16} /></span>
                <div className="chat-inhalt chat-tippt" role="status" aria-label="Bilantiq antwortet">
                  <span /><span /><span />
                </div>
              </div>
            )}
            
            <div ref={endeRef} />
          </div>
          <div className="chat-fuss">
            {eingabe}
            <p className="chat-haftung">Bilantiq liest nur freigegebene Daten. Antworten können Fehler enthalten, bitte prüfe wichtige Zahlen.</p>
          </div>
        </>
      )}
    </div>
  );
}
