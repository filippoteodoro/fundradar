import { NextResponse } from 'next/server';
import { getCurrentUser } from '@/lib/auth';
import { createWatchlist, getUserWatchlists } from '@/lib/watchlist';

export async function GET() {
  const user = await getCurrentUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const watchlists = getUserWatchlists(user.id);
  return NextResponse.json({ watchlists });
}

export async function POST(request: Request) {
  if (process.env.VERCEL) {
    return NextResponse.json({ error: 'Watchlists are not available in this environment' }, { status: 503 });
  }
  const user = await getCurrentUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { name } = await request.json();

    if (!name || typeof name !== 'string') {
      return NextResponse.json({ error: 'Name is required' }, { status: 400 });
    }

    const watchlist = createWatchlist(user.id, name);
    return NextResponse.json({ watchlist });
  } catch {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }
}
