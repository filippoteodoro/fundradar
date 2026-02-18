import { NextResponse } from 'next/server';
import { getCurrentUser } from '@/lib/auth';
import { getWatchlistById, updateWatchlist, deleteWatchlist } from '@/lib/watchlist';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const user = await getCurrentUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { id } = await params;
  const watchlist = getWatchlistById(id, user.id);

  if (!watchlist) {
    return NextResponse.json({ error: 'Watchlist not found' }, { status: 404 });
  }

  return NextResponse.json({ watchlist });
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  if (process.env.VERCEL) {
    return NextResponse.json({ error: 'Watchlists are not available in this environment' }, { status: 503 });
  }
  const user = await getCurrentUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { id } = await params;

  try {
    const { name, fund_slugs } = await request.json();
    const watchlist = updateWatchlist(id, user.id, { name, fund_slugs });

    if (!watchlist) {
      return NextResponse.json({ error: 'Watchlist not found' }, { status: 404 });
    }

    return NextResponse.json({ watchlist });
  } catch {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  if (process.env.VERCEL) {
    return NextResponse.json({ error: 'Watchlists are not available in this environment' }, { status: 503 });
  }
  const user = await getCurrentUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { id } = await params;
  const deleted = deleteWatchlist(id, user.id);

  if (!deleted) {
    return NextResponse.json({ error: 'Watchlist not found' }, { status: 404 });
  }

  return NextResponse.json({ success: true });
}
