'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Fund } from '@fundradar/shared';
import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';

interface WatchlistWithFunds {
  id: string;
  user_id: string;
  name: string;
  fund_slugs: string[];
  funds: (Fund | undefined)[];
  created_at: string;
  updated_at: string;
}

interface Props {
  watchlists: WatchlistWithFunds[];
  allFunds: Fund[];
  userId: string;
}

export function WatchlistManager({ watchlists, allFunds, userId }: Props) {
  const router = useRouter();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  async function createWatchlist(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;

    setLoading(true);
    try {
      const res = await fetch('/api/watchlists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName }),
      });

      if (res.ok) {
        setNewName('');
        setShowCreate(false);
        router.refresh();
      }
    } finally {
      setLoading(false);
    }
  }

  async function deleteWatchlist(id: string) {
    if (!confirm('Delete this watchlist?')) return;

    try {
      const res = await fetch(`/api/watchlists/${id}`, { method: 'DELETE' });
      if (res.ok) {
        router.refresh();
      }
    } catch (e) {
      console.error('Delete failed:', e);
    }
  }

  async function addFund(watchlistId: string, fundSlug: string) {
    try {
      const res = await fetch(`/api/watchlists/${watchlistId}/funds`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fundSlug }),
      });
      if (res.ok) {
        router.refresh();
      }
    } catch (e) {
      console.error('Add fund failed:', e);
    }
  }

  async function removeFund(watchlistId: string, fundSlug: string) {
    try {
      const res = await fetch(`/api/watchlists/${watchlistId}/funds/${fundSlug}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        router.refresh();
      }
    } catch (e) {
      console.error('Remove fund failed:', e);
    }
  }

  const filteredFunds = allFunds.filter(
    f =>
      f.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.slug.includes(searchQuery.toLowerCase())
  );

  return (
    <div>
      {/* Create button */}
      {!showCreate && (
        <button
          onClick={() => setShowCreate(true)}
          style={{
            padding: '12px 24px',
            background: '#1a1a2e',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '14px',
            marginBottom: '24px',
          }}
        >
          + Create New Watchlist
        </button>
      )}

      {/* Create form */}
      {showCreate && (
        <form
          onSubmit={createWatchlist}
          style={{
            ...CARD_STYLE,
            padding: CARD_PADDING,
            marginBottom: '24px',
          }}
        >
          <input
            type="text"
            placeholder="Watchlist name..."
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{
              width: '100%',
              padding: '12px',
              border: '1px solid #ddd',
              borderRadius: '8px',
              fontSize: '14px',
              marginBottom: '12px',
              boxSizing: 'border-box',
            }}
          />
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="submit"
              disabled={loading || !newName.trim()}
              style={{
                padding: '8px 16px',
                background: '#1a1a2e',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                cursor: 'pointer',
              }}
            >
              {loading ? 'Creating...' : 'Create'}
            </button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              style={{
                padding: '8px 16px',
                background: 'white',
                border: '1px solid #ddd',
                borderRadius: '8px',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Watchlists */}
      {watchlists.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            ...CARD_STYLE,
            padding: '48px',
          }}
        >
          <p style={{ color: '#666', marginBottom: '16px' }}>
            You don&apos;t have any watchlists yet.
          </p>
          <p style={{ color: '#888', fontSize: '14px' }}>
            Create a watchlist to track funds and receive alerts.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {watchlists.map((watchlist) => (
            <div
              key={watchlist.id}
              style={{
                ...CARD_STYLE,
                overflow: 'hidden',
              }}
            >
              {/* Header */}
              <div
                style={{
                  padding: CARD_PADDING,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  cursor: 'pointer',
                  background: expandedId === watchlist.id ? '#f9f9f9' : 'white',
                }}
                onClick={() => setExpandedId(expandedId === watchlist.id ? null : watchlist.id)}
              >
                <div>
                  <h3 style={{ margin: 0, fontSize: '16px' }}>{watchlist.name}</h3>
                  <p style={{ margin: '4px 0 0', color: '#666', fontSize: '13px' }}>
                    {watchlist.fund_slugs.length} fund{watchlist.fund_slugs.length !== 1 ? 's' : ''}
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteWatchlist(watchlist.id);
                    }}
                    style={{
                      padding: '6px 12px',
                      background: 'white',
                      border: '1px solid #ddd',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      fontSize: '12px',
                      color: '#c00',
                    }}
                  >
                    Delete
                  </button>
                  <span style={{ color: '#888' }}>{expandedId === watchlist.id ? '▲' : '▼'}</span>
                </div>
              </div>

              {/* Expanded content */}
              {expandedId === watchlist.id && (
                <div style={{ borderTop: '1px solid #eee', padding: CARD_PADDING }}>
                  {/* Current funds */}
                  {watchlist.funds.length > 0 && (
                    <div style={{ marginBottom: '16px' }}>
                      <h4 style={{ margin: '0 0 8px', fontSize: '14px', color: '#666' }}>
                        Tracked Funds
                      </h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {watchlist.funds.map(
                          (fund) =>
                            fund && (
                              <div
                                key={fund.slug}
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                  padding: '8px 12px',
                                  background: '#f5f5f5',
                                  borderRadius: '8px',
                                }}
                              >
                                <a
                                  href={`/funds/${fund.slug}`}
                                  style={{ color: '#0066cc', textDecoration: 'none' }}
                                >
                                  {fund.name}
                                </a>
                                <button
                                  onClick={() => removeFund(watchlist.id, fund.slug)}
                                  style={{
                                    padding: '4px 8px',
                                    background: 'white',
                                    border: '1px solid #ddd',
                                    borderRadius: '8px',
                                    cursor: 'pointer',
                                    fontSize: '12px',
                                  }}
                                >
                                  Remove
                                </button>
                              </div>
                            )
                        )}
                      </div>
                    </div>
                  )}

                  {/* Add fund */}
                  <div>
                    <h4 style={{ margin: '0 0 8px', fontSize: '14px', color: '#666' }}>Add Fund</h4>
                    <input
                      type="text"
                      placeholder="Search funds..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        border: '1px solid #ddd',
                        borderRadius: '8px',
                        fontSize: '14px',
                        marginBottom: '8px',
                        boxSizing: 'border-box',
                      }}
                    />
                    {searchQuery && (
                      <div
                        style={{
                          maxHeight: '200px',
                          overflowY: 'auto',
                          border: '1px solid #eee',
                          borderRadius: '8px',
                        }}
                      >
                        {filteredFunds.slice(0, 10).map((fund) => (
                          <div
                            key={fund.slug}
                            style={{
                              padding: '8px 12px',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              borderBottom: '1px solid #eee',
                            }}
                          >
                            <span>{fund.name}</span>
                            {watchlist.fund_slugs.includes(fund.slug) ? (
                              <span style={{ color: '#888', fontSize: '12px' }}>Added</span>
                            ) : (
                              <button
                                onClick={() => addFund(watchlist.id, fund.slug)}
                                style={{
                                  padding: '4px 8px',
                                  background: '#1a1a2e',
                                  color: 'white',
                                  border: 'none',
                                  borderRadius: '8px',
                                  cursor: 'pointer',
                                  fontSize: '12px',
                                }}
                              >
                                Add
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
