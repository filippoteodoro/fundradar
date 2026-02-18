import { redirect } from 'next/navigation';
import { getCurrentUser } from '@/lib/auth';
import { SignupForm } from './SignupForm';

export default async function SignupPage() {
  if (process.env.VERCEL === '1') {
    return (
      <div style={{ maxWidth: '400px', margin: '0 auto', padding: '48px 0', textAlign: 'center' }}>
        <h1 style={{ marginBottom: '8px' }}>Coming Soon</h1>
        <p style={{ color: '#666', marginBottom: '24px' }}>
          User accounts coming soon. All fund data is freely accessible.
        </p>
        <a href="/" style={{ color: '#0066cc' }}>
          &larr; Back to all funds
        </a>
      </div>
    );
  }

  const user = await getCurrentUser();

  if (user) {
    redirect('/watchlists');
  }

  return (
    <div style={{ maxWidth: '400px', margin: '0 auto', padding: '48px 0' }}>
      <h1 style={{ textAlign: 'center', marginBottom: '8px' }}>Create Account</h1>
      <p style={{ textAlign: 'center', color: '#666', marginBottom: '32px' }}>
        Sign up to create watchlists and receive alerts
      </p>

      <SignupForm />

      <p style={{ textAlign: 'center', marginTop: '24px', fontSize: '14px', color: '#666' }}>
        Already have an account?{' '}
        <a href="/login" style={{ color: '#0066cc' }}>
          Sign in
        </a>
      </p>
    </div>
  );
}
