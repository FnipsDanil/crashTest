import { useState, lazy, Suspense, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { FooterNav } from '../components/FooterNav/FooterNav';
import ErrorBoundary from '../components/ErrorBoundary/ErrorBoundary';

// Lazy load components for better performance
import Game from '../components/Game/GameWebSocket';
import Profile from '../components/Profile/Profile';
import Leaderboard from '../components/Leaderboard/Leaderboard';
import Store from '../components/Store/Store';

export const pages = [
  { labelKey: 'nav.home', Component: Game, icon: '🎮' },
  { labelKey: 'nav.profile', Component: Profile, icon: '👤' },
  { labelKey: 'nav.leaderboard', Component: Leaderboard, icon: '🏆' },
  { labelKey: 'nav.store', Component: Store, icon: '🎁' }
];

export default function IndexPage() {
  const [page, setPage] = useState(0);
  const { Component } = pages[page];
  const { t } = useTranslation();

  // Reset scroll position when tab changes
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [page]);

  return (
    <div className="app-wrapper">
      <Suspense fallback={
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>{t('common.loading')}</p>
          {/* <p>Если это занимает долго, пожалуйста, попробуйте перезапустить приложение.</p> */}
        </div>
      }>
        <Component key={page} />
      </Suspense>
      <FooterNav
        value={page}
        onChange={setPage}
        items={pages.map(({ labelKey, icon }) => ({ labelKey, icon }))}
      />
    </div>
  );
}
