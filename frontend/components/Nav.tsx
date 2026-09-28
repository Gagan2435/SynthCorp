"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Nav() {
  const path = usePathname();
  const item = (href: string, label: string, active: boolean) => (
    <Link href={href} aria-current={active ? "page" : undefined}>
      {label}
    </Link>
  );
  return (
    <aside className="rail">
      <div>
        <p className="wordmark">SynthCorp</p>
        <p className="tagline">Describe a company. Get its data.</p>
      </div>
      <nav className="nav" aria-label="Main">
        {item("/", "New dataset", path === "/")}
        {item("/runs", "Past runs", path.startsWith("/runs"))}
      </nav>
    </aside>
  );
}
