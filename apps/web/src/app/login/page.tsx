import { redirect } from 'next/navigation';

export default async function LoginPage() {
  // No user accounts — redirect to subscribe page
  redirect('/subscribe');
}
