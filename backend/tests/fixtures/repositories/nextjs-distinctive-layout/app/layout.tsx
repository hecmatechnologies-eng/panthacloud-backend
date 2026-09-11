import type { Metadata } from "next";
import { Fraunces } from "next/font/google";
import { CartProvider } from "@/components/cart/CartProvider";
import { Analytics } from "@/components/analytics/Analytics";
import "./globals.css";

// FIXTURE-SENTINEL: Rwenzori Roasters root layout - must survive integration
const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });

export const metadata: Metadata = {
  title: "Rwenzori Roasters | Single-origin coffee from Fort Portal",
  description: "Small-batch coffee roasted on the slopes of the Rwenzori.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={fraunces.variable}>
        <CartProvider currency="UGX">
          <header data-testid="rr-announcement">Free delivery within Kabarole district</header>
          {children}
        </CartProvider>
        <Analytics siteId="rr-storefront" />
      </body>
    </html>
  );
}
