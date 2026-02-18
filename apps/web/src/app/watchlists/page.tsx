import { redirect } from 'next/navigation';

export default async function WatchlistsPage() {
  // No user accounts — redirect to subscribe page
  redirect('/subscribe');
}
