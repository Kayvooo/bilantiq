import { GroupedListRow, GroupedListSection } from "../../components/GroupedList";
import { InstallAppSection } from "../../components/InstallAppSection";
import { PageHeader } from "../../components/PageHeader";

interface Props {
  onOpenAssistant: () => void;
  onOpenEuer: () => void;
  onOpenCashflow: () => void;
  onOpenUstva: () => void;
  onOpenPayroll: () => void;
  onOpenSettings: () => void;
  onOpenContacts: () => void;
  onOpenProdukte: () => void;
  onOpenUmzug: () => void;
  onOpenEinnahmen: () => void;
  onOpenBuchhaltungseinstellungen: () => void;
  onOpenMahnungen: () => void;
  onOpenSusa: () => void;
  onOpenBwa: () => void;
  onOpenWiederkehrend: () => void;
  onOpenGutschriften: () => void;
  onOpenWiederkehrendAusgaben: () => void;
  onOpenAnlagen: () => void;
  onOpenKassenbuch: () => void;
  onOpenBank: () => void;
  onOpenErsteSchritte: () => void;
  onOpenBenutzer: () => void;
  onOpenSecurity: () => void;
  onOpenSteuerberater: () => void;
  onOpenAuftragsbestaetigung: () => void;
  onOpenLieferscheine: () => void;
  onOpenRechnungsvorlage: () => void;
  onLogout: () => void;
  /** true, sobald feststeht, dass der Nutzer nur Mitglied ist: der Lohn-Bereich wird ausgeblendet. */
  istMitglied?: boolean;
}

export function MorePage({
  onOpenAssistant, onOpenEuer, onOpenCashflow, onOpenUstva, onOpenPayroll, onOpenSettings,
  onOpenContacts, onOpenProdukte, onOpenUmzug, onOpenEinnahmen, onOpenBuchhaltungseinstellungen, onOpenMahnungen, onOpenSusa, onOpenBwa, onOpenWiederkehrend, onOpenGutschriften,
  onOpenWiederkehrendAusgaben, onOpenAnlagen, onOpenKassenbuch, onOpenBank, onOpenErsteSchritte, onOpenBenutzer, onOpenSecurity, onOpenSteuerberater,
  onOpenAuftragsbestaetigung, onOpenLieferscheine, onOpenRechnungsvorlage, onLogout, istMitglied = false,
}: Props) {

  return (
    <div className="dashboard-page">
      <PageHeader title="Mehr" description="Steuern, Auswertungen und Kontoeinstellungen an einem Ort." />

      <GroupedListSection title="Start">
        <GroupedListRow label="Erste Schritte" description="Checkliste zum Einrichten deines Kontos" onClick={onOpenErsteSchritte} />
      </GroupedListSection>

      <GroupedListSection title="Aufträge">
        <GroupedListRow label="Auftragsbestätigung" description="Aus einem angenommenen Angebot erzeugen" onClick={onOpenAuftragsbestaetigung} />
        <GroupedListRow label="Lieferscheine" description="Lieferungen ohne Preise dokumentieren" onClick={onOpenLieferscheine} />
      </GroupedListSection>

      <GroupedListSection title="Rechnungen">
        <GroupedListRow label="Sonstige Einnahmen" description="Weitere betriebliche Einnahmen erfassen" onClick={onOpenEinnahmen} />
        <GroupedListRow label="Wiederkehrend" description="Vorlagen für automatisch erzeugte Entwürfe" onClick={onOpenWiederkehrend} />
        <GroupedListRow label="Mahnungen" description="Alle Zahlungserinnerungen und Mahnstufen" onClick={onOpenMahnungen} />
        <GroupedListRow label="Gutschriften" description="Alle Storno-/Korrekturrechnungen" onClick={onOpenGutschriften} />
      </GroupedListSection>

      <GroupedListSection title="Steuern">
        <GroupedListRow label="Umsatzsteuervoranmeldung" description="Umsätze und Vorsteuer für deinen Zeitraum" onClick={onOpenUstva} />
        <GroupedListRow label="Einnahmen-Überschuss-Rechnung" description="Einnahmen, Ausgaben und DATEV-Export" onClick={onOpenEuer} />
        <GroupedListRow label="Mein Steuerberater" description="Kontakt und Auswertungen für die Kanzlei" onClick={onOpenSteuerberater} />
      </GroupedListSection>

      <GroupedListSection title="Auswertungen">
        <GroupedListRow label="Cashflow-Prognose" description="Erwartete Ein- und Auszahlungen für acht Wochen" onClick={onOpenCashflow} />
        <GroupedListRow label="SuSa" description="Soll, Haben und Saldo je Konto" onClick={onOpenSusa} />
        <GroupedListRow label="BWA" description="Vereinfachte Erlöse-/Kosten-Auswertung" onClick={onOpenBwa} />
      </GroupedListSection>

      <GroupedListSection title="Ausgaben">
        <GroupedListRow label="Wiederkehrend" description="Vorlagen für automatisch gebuchte Kosten" onClick={onOpenWiederkehrendAusgaben} />
        <GroupedListRow label="Anlagen" description="Anlagevermögen mit AfA" onClick={onOpenAnlagen} />
      </GroupedListSection>

      <GroupedListSection title="Bank">
        <GroupedListRow label="Kontoauszug" description="Zahlungen importieren und Rechnungen und Belegen zuordnen" onClick={onOpenBank} />
        <GroupedListRow label="Kassenbuch" description="Manuelle Bar-Ein- und Auszahlungen" onClick={onOpenKassenbuch} />
      </GroupedListSection>

      {!istMitglied && (
        <GroupedListSection title="Lohn">
          <GroupedListRow label="Lohnvorbereitung" description="Mitarbeitende und Monatswerte für die Steuerkanzlei" onClick={onOpenPayroll} />
        </GroupedListSection>
      )}

      <GroupedListSection title="KI">
        <GroupedListRow label="KI-Assistent" description="Eigene Bilantiq-Daten lesen und erklären lassen" onClick={onOpenAssistant} />
      </GroupedListSection>

      <GroupedListSection title="Verwalten">
        <GroupedListRow label="Kontakte" description="Kunden für Rechnungen und Angebote" onClick={onOpenContacts} />
        <GroupedListRow label="Produkte" description="Produkte und Leistungen verwalten" onClick={onOpenProdukte} />
        <GroupedListRow label="Datenumzug" description="Von einem anderen Programm wechseln" onClick={onOpenUmzug} />
        <GroupedListRow label="Erweiterungen" disabled />
      </GroupedListSection>

      <GroupedListSection title="Einstellungen">
        <GroupedListRow label="Benutzer & Rechte" description="Mitglieder und Einladungen" onClick={onOpenBenutzer} />
        <GroupedListRow label="Sicherheit & Datenschutz" description="E-Mail, Passwort, MFA, Sitzungen und Datenexport" onClick={onOpenSecurity} />
        <GroupedListRow label="Buchhaltung" description="Zahlungsziel, USt und Kleinunternehmerregelung" onClick={onOpenBuchhaltungseinstellungen} />
        <GroupedListRow label="Unternehmen" description="USt-IdNr., Steuernummer, DATEV-Nummern" onClick={onOpenSettings} />
        <GroupedListRow label="System" disabled />
        <GroupedListRow label="Rechnungsdesign" description="Vorlage, Logo, Briefpapier, Sprache und Elemente" onClick={onOpenRechnungsvorlage} />
        <GroupedListRow label="Textvorlagen" disabled />
      </GroupedListSection>

      <GroupedListSection title="Konto">
        <GroupedListRow label="Abmelden" description="Beendet diese Sitzung auf diesem Gerät" onClick={onLogout} />
      </GroupedListSection>

      <InstallAppSection />
    </div>
  );
}
