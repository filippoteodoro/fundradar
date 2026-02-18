import { NextRequest, NextResponse } from 'next/server';

// Simple in-memory rate limiting (resets on server restart)
const rateLimitMap = new Map<string, { count: number; resetTime: number }>();
const RATE_LIMIT_WINDOW = 60 * 60 * 1000; // 1 hour
const MAX_REQUESTS_PER_WINDOW = 5;

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const record = rateLimitMap.get(ip);

  if (!record || now > record.resetTime) {
    rateLimitMap.set(ip, { count: 1, resetTime: now + RATE_LIMIT_WINDOW });
    return false;
  }

  if (record.count >= MAX_REQUESTS_PER_WINDOW) {
    return true;
  }

  record.count++;
  return false;
}

export async function POST(request: NextRequest) {
  try {
    // Get client IP for rate limiting (x-real-ip is set by Vercel and cannot be spoofed)
    const ip = request.headers.get('x-real-ip') || request.headers.get('x-forwarded-for')?.split(',')[0] || 'unknown';

    // Check rate limit
    if (isRateLimited(ip)) {
      return NextResponse.json(
        { error: 'Too many requests. Please try again later.' },
        { status: 429 }
      );
    }

    const body = await request.json();
    const { name, email, message, honeypot, recaptchaToken, timeSpent } = body;

    // Anti-spam check 1: Honeypot field should be empty
    if (honeypot && honeypot.length > 0) {
      // Silently reject but return success to not tip off bots
      console.log('Spam detected: honeypot field filled');
      return NextResponse.json({ success: true });
    }

    // Anti-spam check 2: Google reCAPTCHA
    const recaptchaSecret = process.env.RECAPTCHA_SECRET_KEY;
    if (!recaptchaSecret) {
      return NextResponse.json({ error: 'Anti-spam verification is not configured.' }, { status: 500 });
    }
    if (!recaptchaToken) {
      return NextResponse.json({ error: 'Please complete the anti-spam check.' }, { status: 400 });
    }

    const recaptchaRes = await fetch('https://www.google.com/recaptcha/api/siteverify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        secret: recaptchaSecret,
        response: recaptchaToken,
        remoteip: ip,
      }),
    });
    const recaptchaData = await recaptchaRes.json();
    if (!recaptchaData?.success || (recaptchaData.score ?? 1) < 0.5) {
      console.warn('reCAPTCHA failed:', recaptchaData);
      return NextResponse.json({ error: 'Anti-spam verification failed.' }, { status: 400 });
    }

    // Anti-spam check 3: Minimum time check (at least 3 seconds)
    if (timeSpent < 3000) {
      return NextResponse.json({ error: 'Please take your time filling out the form.' }, { status: 400 });
    }

    // Validate required fields
    if (!name || !email || !message) {
      return NextResponse.json({ error: 'All fields are required.' }, { status: 400 });
    }

    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return NextResponse.json({ error: 'Please enter a valid email address.' }, { status: 400 });
    }

    // Sanitize inputs (XSS + email header injection prevention)
    const sanitize = (str: string) =>
      str.replace(/[<>]/g, '').replace(/[\r\n]/g, ' ').trim().substring(0, 5000);

    const sanitizedName = sanitize(name);
    const sanitizedEmail = sanitize(email);
    const sanitizedMessage = sanitize(message);

    // Log the contact message (in production, you'd send an email or store in DB)
    console.log('=== Contact Form Submission ===');
    console.log('Time:', new Date().toISOString());
    console.log('From:', sanitizedName, `<${sanitizedEmail}>`);
    console.log('Message:', sanitizedMessage);
    console.log('IP:', ip);
    console.log('Time spent on form:', Math.round(timeSpent / 1000), 'seconds');
    console.log('==============================');

    // In a real production app, you would:
    // 1. Send an email using a service like SendGrid, Resend, or Postmark
    // 2. Store the message in a database
    // 3. Maybe send a Slack/Discord notification
    //
    // Example with Resend (if configured):
    // await resend.emails.send({
    //   from: 'Fundradar <noreply@fundradar.io>',
    //   to: 'hello@fundradar.io',
    //   subject: `Contact form: ${sanitizedName}`,
    //   text: `From: ${sanitizedName} <${sanitizedEmail}>\n\n${sanitizedMessage}`,
    // });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Contact form error:', error);
    return NextResponse.json({ error: 'Failed to process your request.' }, { status: 500 });
  }
}
