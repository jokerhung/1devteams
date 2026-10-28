import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Providers } from "@/components/providers";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";
const inter = Inter({
  subsets: ["latin", "vietnamese"],
  variable: "--font-inter",
});
const mono = JetBrains_Mono({
  subsets: ["latin", "vietnamese"],
  variable: "--font-jetbrains",
});
export const metadata: Metadata = {
  title: "1devTeams — Multi-Agent Workspace",
  description: "Quản lý AI Agent, Team và dự án trong workspace của bạn.",
  icons: {
    icon: "/favicon.ico?v=1devteams",
  },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <body className={`${inter.variable} ${mono.variable} antialiased`}>
        <Providers>
          <TooltipProvider>{children}</TooltipProvider>
        </Providers>
      </body>
    </html>
  );
}
