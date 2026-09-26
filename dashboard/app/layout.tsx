import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ATLAS — money, time, agent",
  description:
    "An agentic chief of staff you drive by voice. ATLAS scores financial risk with a real trained model, plans study weeks, and composes your daily brief.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
