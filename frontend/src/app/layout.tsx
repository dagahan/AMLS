import type { Metadata } from "next";
import Script from "next/script";
import { IBM_Plex_Sans, Manrope } from "next/font/google";
import "./globals.css";

const ibmPlexSans = IBM_Plex_Sans({
  variable: "--font-body",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const manrope = Manrope({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "Adaptive Learning Demo",
  description: "Adaptive math learning demo with knowledge graph diagnostics",
};


export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${ibmPlexSans.variable} ${manrope.variable} h-full antialiased light`}
    >
      <body className="min-h-full flex flex-col">
        {children}
        <Script id="mathjax-config" strategy="beforeInteractive">
          {`window.MathJax = {tex: {inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']], processEscapes: true}, svg: {fontCache: 'global'}};`}
        </Script>
        <Script
          id="mathjax-script"
          src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"
          strategy="afterInteractive"
        />
      </body>
    </html>
  );
}
