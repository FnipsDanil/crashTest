import type { FC, ReactNode } from "react";
import { useTranslation } from 'react-i18next';
import "./FooterNav.css";

interface FooterNavProps {
  value: number;
  onChange: (idx: number) => void;
  items: { icon: ReactNode; labelKey: string }[];
}

export const FooterNav: FC<FooterNavProps> = ({ value, onChange, items }) => {
  const { t } = useTranslation();
  
  return (
    <nav className="footer-nav">
      {items.map((item, i) => (
        <div
          key={item.labelKey}
          className={`footer-nav-item${i === value ? " active" : ""}`}
          onClick={() => onChange(i)}
        >
          <div className="footer-nav-icon">{item.icon}</div>
          <span>{t(item.labelKey)}</span>
        </div>
      ))}
    </nav>
  );
};