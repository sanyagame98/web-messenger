import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Web Messenger",
  description: "A Telegram-like web messenger",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
