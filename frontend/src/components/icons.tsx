import type { SVGProps } from "react";

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function HomeIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M3.5 10.5 12 4l8.5 6.5" />
      <path d="M5.5 9v10a1 1 0 0 0 1 1H9v-6h6v6h2.5a1 1 0 0 0 1-1V9" />
    </svg>
  );
}

export function InvoiceIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M6 3h9l3 3v15a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M9 9h6M9 13h6M9 17h3" />
    </svg>
  );
}

export function ReceiptIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M6 3h12v17l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3Z" />
      <path d="M9 8h6M9 12h6" />
    </svg>
  );
}

export function QuoteIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 6.5 12 12l8-5.5" />
      <rect x="4" y="5" width="16" height="14" rx="1.5" />
      <path d="m9 16 2.2 2.2L15.5 14" />
    </svg>
  );
}

export function MoreIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <rect x="4" y="4" width="7" height="7" rx="1.2" />
      <rect x="13" y="4" width="7" height="7" rx="1.2" />
      <rect x="4" y="13" width="7" height="7" rx="1.2" />
      <rect x="13" y="13" width="7" height="7" rx="1.2" />
    </svg>
  );
}

export function ChevronRightIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="m9 5 7 7-7 7" />
    </svg>
  );
}

export function CheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4.5 12.5 9 17l10.5-10.5" />
    </svg>
  );
}

export function PlusIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function ScanIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 8V6a2 2 0 0 1 2-2h2M4 16v2a2 2 0 0 0 2 2h2M20 8V6a2 2 0 0 0-2-2h-2M20 16v2a2 2 0 0 1-2 2h-2" />
      <circle cx="12" cy="12" r="3.2" />
    </svg>
  );
}

export function ArrowLeftIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M19 12H5M11 6l-6 6 6 6" />
    </svg>
  );
}

export function RocketIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M12 15c-2.5 0-5-3-5-7 3-2.5 7-2.5 10 0 0 4-2.5 7-5 7Z" />
      <path d="M9 14.5 6.5 17M15 14.5 17.5 17M9.5 19.5 12 22l2.5-2.5" />
    </svg>
  );
}

export function BankIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 10.5 12 5l8 5.5" />
      <path d="M5.5 10.5v8M9.5 10.5v8M14.5 10.5v8M18.5 10.5v8" />
      <path d="M4 18.5h16" />
    </svg>
  );
}

export function TaxIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M7 3h10a1 1 0 0 1 1 1v17l-3-2-2.5 2-2.5-2-2.5 2L5 21V4a1 1 0 0 1 1-1Z" />
      <path d="m9 15 6-6M9.5 9.5h.01M14.5 14.5h.01" />
    </svg>
  );
}

export function ChartIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </svg>
  );
}

export function WalletIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 7a1 1 0 0 1 1-1h13a1 1 0 0 1 1 1v3M4 7v11a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1H8" />
      <circle cx="16.5" cy="14" r="1.2" />
    </svg>
  );
}

export function ContactIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 19c0-3.3 2.5-5.5 5.5-5.5s5.5 2.2 5.5 5.5M16 8.5c1.4.2 2.5 1.4 2.5 2.9M17 13.2c2 .5 3.5 2.4 3.5 4.8" />
    </svg>
  );
}

export function BoxIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M3.5 8 12 4l8.5 4-8.5 4-8.5-4Z" />
      <path d="M3.5 8v8l8.5 4 8.5-4V8M12 12v8" />
    </svg>
  );
}

export function TagIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M11.5 3.5H5a1.5 1.5 0 0 0-1.5 1.5v6.5L13 21l8-8-9.5-9.5Z" />
      <circle cx="8" cy="8" r="1.3" />
    </svg>
  );
}

export function PuzzleIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <rect x="4" y="4" width="8" height="8" rx="1.5" />
      <rect x="12" y="12" width="8" height="8" rx="1.5" />
      <path d="M12 8h4a2 2 0 0 1 0 4h-4M8 12v4a2 2 0 0 0 4 0v-4" />
    </svg>
  );
}

export function GearIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3.5v2.3M12 18.2v2.3M20.5 12h-2.3M5.8 12H3.5M17.8 6.2l-1.6 1.6M7.8 16.2l-1.6 1.6M17.8 17.8l-1.6-1.6M7.8 7.8 6.2 6.2" />
    </svg>
  );
}

export function ArrowUpIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M12 19V5" />
      <path d="m5.5 11.5 6.5-6.5 6.5 6.5" />
    </svg>
  );
}

export function SparkleIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3.5v4M12 16.5v4M3.5 12h4M16.5 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18" />
    </svg>
  );
}

export function SearchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4.5 4.5" />
    </svg>
  );
}

export function SwapIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 8h13" />
      <path d="m13.5 4.5 3.5 3.5-3.5 3.5" />
      <path d="M20 16H7" />
      <path d="m10.5 12.5L7 16l3.5 3.5" />
    </svg>
  );
}
