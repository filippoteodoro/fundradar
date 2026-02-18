import { redirect } from 'next/navigation';
import { getCurrentUser } from '@/lib/auth';
import { getUserWatchlists } from '@/lib/watchlist';
import { getAllFunds } from '@/lib/data';
import { WatchlistManager } from './WatchlistManager';

export default async function WatchlistsPage() {
  const user = await getCurrentUser();

  if (!user) {
    redirect('/login');
  }

  const watchlists = getUserWatchlists(user.id);
  const funds = getAllFunds();

  // Get fund details for each watchlist
  const watchlistsWithFunds = watchlists.map(w => ({
    ...w,
    funds: w.fund_slugs
      .map(slug => funds.find(f => f.slug === slug))
      .filter(Boolean),
  }));

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ margin: '0 0 8px 0', fontSize: '24px' }}>My Watchlists</h1>
          <p style={{ margin: 0, color: '#666' }}>
            Track funds and receive alerts when new signals are detected.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <span style={{ color: '#666', fontSize: '14px' }}>
            {user.name} ({user.subscription_status})
          </span>
          <form action="/api/auth/logout" method="POST">
            <button
              type="submit"
              style={{
                padding: '8px 16px',
                background: 'white',
                border: '1px solid #ddd',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '14px',
              }}
            >
              Sign Out
            </button>
          </form>
        </div>
      </div>

      <WatchlistManager
        watchlists={watchlistsWithFunds}
        allFunds={funds}
        userId={user.id}
      />
    </div>
  );
}
