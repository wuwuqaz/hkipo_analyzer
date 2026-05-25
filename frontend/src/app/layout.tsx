import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/Navbar";
import { CacheProvider } from "@/lib/CacheContext";

export const metadata: Metadata = {
  title: "HK IPO Analyzer",
  description: "FastAPI + Next.js console for the HK IPO Analyzer",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col">
        <CacheProvider>
          <Navbar />
          <div className="flex-1">{children}</div>
        </CacheProvider>
      </body>
    </html>
  );
}
