import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GPX Terrain Lab｜本地徒步沙盘工作台",
  description: "上传 GPX，配置 TrailPrint3D 真机参数，生成适配 Bambu Studio 的多色徒步沙盘任务。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
