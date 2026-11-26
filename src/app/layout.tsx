import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "냉장고를 부탁해",
  description: "유통기한 임박 재료부터 쓰는 레시피를 추천하는 냉장고 에이전트",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#2f8f5b",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
