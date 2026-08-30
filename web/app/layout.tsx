import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import "./showcase.css";

export const metadata: Metadata = {
  title: "D1 Spend-limited Agent Wallet",
  description: "A LocalNet demo of a Canton wallet with Daml-enforced spending limits, revocation, and ledger receipts.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
