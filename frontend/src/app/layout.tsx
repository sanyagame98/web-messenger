import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Roof",
  description: "Roof messenger",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
