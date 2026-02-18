import { redirect } from 'next/navigation';

export default async function SignupPage() {
  // No user accounts — redirect to subscribe page
  redirect('/subscribe');
}
