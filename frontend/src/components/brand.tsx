import { AnimatePresence, motion } from "framer-motion";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "../theme";

export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <span className="logo-mark" style={{ width: size, height: size }}>
      <svg viewBox="0 0 32 32" width={size * 0.62} height={size * 0.62} aria-hidden>
        <path d="M16 3.5l9.5 3.8v7.4c0 5.8-4 10.5-9.5 12.4-5.5-1.9-9.5-6.6-9.5-12.4V7.3z" fill="none" stroke="currentColor" strokeWidth="2.4" />
        <path d="M11.4 15.6l3.3 3.3 6-6.3" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function ThemeToggle({ compact }: { compact?: boolean }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      className={`theme-toggle ${compact ? "compact" : ""}`}
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
    >
      <span className={`theme-toggle-track ${dark ? "is-dark" : ""}`}>
        <motion.span className="theme-toggle-thumb" layout transition={{ type: "spring", stiffness: 600, damping: 32 }}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={theme}
              initial={{ rotate: -90, opacity: 0, scale: 0.5 }}
              animate={{ rotate: 0, opacity: 1, scale: 1 }}
              exit={{ rotate: 90, opacity: 0, scale: 0.5 }}
              transition={{ duration: 0.2 }}
              style={{ display: "grid" }}
            >
              {dark ? <Moon size={13} strokeWidth={2.4} /> : <Sun size={13} strokeWidth={2.4} />}
            </motion.span>
          </AnimatePresence>
        </motion.span>
      </span>
      {!compact && <span>{dark ? "Dark" : "Light"} mode</span>}
    </button>
  );
}
