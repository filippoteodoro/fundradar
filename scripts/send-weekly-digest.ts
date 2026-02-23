/**
 * Send the pre-built weekly digest to all recipients via Resend.
 *
 * Reads:
 *   data/derived/digest/latest_digest.txt    (subject + body)
 *   data/derived/digest/latest_recipients.csv (recipient list)
 *
 * Workflow:
 *   1. pnpm digest:build --dry-run   → review latest_digest.txt
 *   2. pnpm digest:build             → finalize (updates sent_log)
 *   3. pnpm digest:send              → send
 *   OR use --dry-run on this script to preview recipients without sending.
 */

import { config } from 'dotenv';
import { existsSync, readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { Resend } from 'resend';

const __dirname_local = dirname(fileURLToPath(import.meta.url));
config({ path: join(__dirname_local, '..', '.env') });

const FROM = 'Fundradar <signals@fundradar.co>';
const BATCH_SIZE = 50; // stay well under Resend's 100/batch limit
const BATCH_DELAY_MS = 500;

function resolveProjectRoot(): string {
  const candidates = [
    process.cwd(),
    join(process.cwd(), '..'),
    join(__dirname_local, '..'),
  ];
  for (const candidate of candidates) {
    if (existsSync(join(candidate, 'data')) && existsSync(join(candidate, 'scripts'))) {
      return candidate;
    }
  }
  throw new Error('Could not resolve project root (expected data/ and scripts/ directories).');
}

function parseDigestFile(text: string): { subject: string; body: string } {
  const lines = text.split('\n');
  const subjectLine = lines[0] ?? '';
  if (!subjectLine.startsWith('Subject: ')) {
    throw new Error('Digest file does not start with "Subject: " — run "pnpm digest:build" first.');
  }
  const subject = subjectLine.slice('Subject: '.length).trim();
  // Body starts after the blank line that follows the Subject header
  const blankIndex = lines.findIndex((line, i) => i > 0 && line.trim() === '');
  const body = blankIndex >= 0 ? lines.slice(blankIndex + 1).join('\n').trimEnd() : '';
  return { subject, body };
}

function parseRecipientsFile(csv: string): string[] {
  return csv
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.includes('@') && l !== 'email'); // skip header row
}

function chunk<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    chunks.push(arr.slice(i, i + size));
  }
  return chunks;
}

async function main(): Promise<void> {
  const dryRun = process.argv.includes('--dry-run');
  const testEmailArg = process.argv.find((a) => a.startsWith('--test-email='));
  const testEmail = testEmailArg ? testEmailArg.split('=')[1].trim() : null;

  const projectRoot = resolveProjectRoot();
  const digestDir = join(projectRoot, 'data', 'derived', 'digest');
  const digestPath = join(digestDir, 'latest_digest.txt');
  const recipientsPath = join(digestDir, 'latest_recipients.csv');

  if (!existsSync(digestPath)) {
    throw new Error(`Digest not found: ${digestPath}\nRun "pnpm digest:build" first.`);
  }
  if (!existsSync(recipientsPath)) {
    throw new Error(`Recipients not found: ${recipientsPath}\nRun "pnpm digest:build" first.`);
  }

  const { subject, body } = parseDigestFile(readFileSync(digestPath, 'utf-8'));
  const allRecipients = parseRecipientsFile(readFileSync(recipientsPath, 'utf-8'));
  const recipients = testEmail ? [testEmail] : allRecipients;

  console.log(`From:       ${FROM}`);
  console.log(`Subject:    ${subject}`);
  if (testEmail) {
    console.log(`Mode:       TEST — sending only to ${testEmail}`);
  } else {
    console.log(`Recipients: ${recipients.length}`);
  }
  console.log(`Dry run:    ${dryRun ? 'yes' : 'no'}`);
  console.log('');

  if (recipients.length === 0) {
    console.log('No recipients — nothing to send.');
    return;
  }

  if (dryRun) {
    console.log('DRY RUN — no emails sent.');
    const preview = recipients.slice(0, 5).join(', ');
    const more = recipients.length > 5 ? ` ... +${recipients.length - 5} more` : '';
    console.log(`Recipients preview: ${preview}${more}`);
    return;
  }

  const resendKey = process.env.RESEND_API_KEY;
  if (!resendKey) {
    throw new Error('RESEND_API_KEY not set in .env');
  }

  const resend = new Resend(resendKey);
  const batches = chunk(recipients, BATCH_SIZE);
  let sent = 0;
  let failed = 0;

  for (let i = 0; i < batches.length; i += 1) {
    const batch = batches[i];
    console.log(`Sending batch ${i + 1}/${batches.length} (${batch.length} recipients)...`);

    const messages = batch.map((email) => ({
      from: FROM,
      to: email,
      subject,
      text: body,
    }));

    try {
      const result = await resend.batch.send(messages);
      if (result.error) {
        throw new Error(result.error.message);
      }
      const batchSent = result.data?.length ?? batch.length;
      sent += batchSent;
      console.log(`  ✓ ${batchSent} sent`);
    } catch (err) {
      failed += batch.length;
      console.error(`  ✗ Batch ${i + 1} failed: ${(err as Error).message}`);
    }

    if (i < batches.length - 1) {
      await new Promise((resolve) => { setTimeout(resolve, BATCH_DELAY_MS); });
    }
  }

  console.log('');
  console.log(`Done. Sent: ${sent}  Failed: ${failed}`);
  if (failed > 0) process.exit(1);
}

main().catch((error) => {
  console.error((error as Error).message);
  process.exit(1);
});
