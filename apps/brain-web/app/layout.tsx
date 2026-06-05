import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Zsper Brain",
  description: "Local-first Zsper Brain workspace shell"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
