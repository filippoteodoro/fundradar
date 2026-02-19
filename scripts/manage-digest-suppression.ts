import { existsSync, readFileSync, writeFileSync } from 'fs';
import { join, resolve } from 'path';

interface SuppressionFile {
  updated_at: string;
  emails: string[];
}

function usage(): never {
  console.log('Usage: pnpm -F scripts digest:suppress <list|add|remove> [email ...]');
  console.log('');
  console.log('Examples:');
  console.log('  pnpm -F scripts digest:suppress list');
  console.log('  pnpm -F scripts digest:suppress add user@example.com');
  console.log('  pnpm -F scripts digest:suppress remove user@example.com');
  process.exit(1);
}

function resolveProjectRoot(): string {
  const candidates = [
    process.cwd(),
    join(process.cwd(), '..'),
  ];

  for (const candidate of candidates) {
    const absolute = resolve(candidate);
    if (existsSync(join(absolute, 'data')) && existsSync(join(absolute, 'scripts'))) {
      return absolute;
    }
  }

  throw new Error('Could not resolve project root');
}

function loadSuppression(path: string): SuppressionFile {
  if (!existsSync(path)) {
    return { updated_at: new Date(0).toISOString(), emails: [] };
  }
  const parsed = JSON.parse(readFileSync(path, 'utf-8')) as Partial<SuppressionFile> | string[];
  if (Array.isArray(parsed)) {
    return {
      updated_at: new Date(0).toISOString(),
      emails: parsed
        .filter((v): v is string => typeof v === 'string')
        .map((v) => v.trim().toLowerCase())
        .filter(Boolean),
    };
  }

  return {
    updated_at: typeof parsed.updated_at === 'string' ? parsed.updated_at : new Date(0).toISOString(),
    emails: Array.isArray(parsed.emails)
      ? parsed.emails
        .filter((v): v is string => typeof v === 'string')
        .map((v) => v.trim().toLowerCase())
        .filter(Boolean)
      : [],
  };
}

function saveSuppression(path: string, emails: Set<string>): void {
  const payload: SuppressionFile = {
    updated_at: new Date().toISOString(),
    emails: Array.from(emails).sort(),
  };
  writeFileSync(path, JSON.stringify(payload, null, 2));
}

function normalizeEmails(values: string[]): string[] {
  return values
    .map((value) => value.trim().toLowerCase())
    .filter((value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value));
}

function main(): void {
  const [command, ...args] = process.argv.slice(2);
  if (!command || !['list', 'add', 'remove'].includes(command)) usage();

  const projectRoot = resolveProjectRoot();
  const filePath = join(projectRoot, 'data', 'digest_unsubscribed_emails.json');
  const data = loadSuppression(filePath);
  const emails = new Set(data.emails);

  if (command === 'list') {
    if (emails.size === 0) {
      console.log('Suppression list is empty.');
      return;
    }
    console.log(`Suppressed recipients (${emails.size}):`);
    for (const email of Array.from(emails).sort()) {
      console.log(`- ${email}`);
    }
    return;
  }

  const normalized = normalizeEmails(args);
  if (normalized.length === 0) {
    console.log('No valid email arguments provided.');
    usage();
  }

  let changed = 0;
  if (command === 'add') {
    for (const email of normalized) {
      if (emails.has(email)) continue;
      emails.add(email);
      changed += 1;
    }
  } else {
    for (const email of normalized) {
      if (!emails.has(email)) continue;
      emails.delete(email);
      changed += 1;
    }
  }

  saveSuppression(filePath, emails);
  console.log(`${command === 'add' ? 'Added' : 'Removed'} ${changed} email(s).`);
  console.log(`Suppression list size: ${emails.size}`);
  console.log(`File: ${filePath}`);
}

main();
