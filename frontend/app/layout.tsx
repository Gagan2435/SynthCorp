import type { Metadata } from "next";
import Nav from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "SynthCorp",
  description: "Describe a company. Get its data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <Nav />
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
