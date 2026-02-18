import { NextResponse } from 'next/server';
import { logout } from '@/lib/auth';

export async function POST() {
  if (process.env.VERCEL) {
    return NextResponse.json({ error: 'Authentication is not available in this environment' }, { status: 503 });
  }
  try {
    await logout();
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Logout error:', error);
    return NextResponse.json(
      { error: 'An error occurred during logout' },
      { status: 500 }
    );
  }
}
