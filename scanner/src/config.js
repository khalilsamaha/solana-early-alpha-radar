import fs from 'node:fs';
import path from 'node:path';
if (fs.existsSync('.env')) process.loadEnvFile('.env');
export function readConfig(env = process.env) {
  const num = (key, fallback, min = 1, max = Infinity) => {
    if (env[key] == null || env[key] === '') return fallback;
    const n = Number(env[key]);
    if (!Number.isFinite(n) || n < min || n > max || !Number.isInteger(n)) throw new Error(`Invalid ${key}`);
    return n;
  };
  const bool = (key, fallback) => {
    if (!env[key]) return fallback;
    if (!['true', 'false'].includes(env[key])) throw new Error(`Invalid ${key}: use true or false`);
    return env[key] === 'true';
  };
  const c = {
    pumpPortalSource: env.PUMPPORTAL_SOURCE || 'direct', pumpPortalSocket: env.PUMPPORTAL_SOCKET || '',
    pumpPortalApiKey: env.PUMPPORTAL_API_KEY || '', jupiterApiKey: env.JUPITER_API_KEY || '',
    heliusApiKey: env.HELIUS_API_KEY || '', telegramBotToken: env.TELEGRAM_BOT_TOKEN || '',
    telegramChatId: env.TELEGRAM_CHAT_ID || '', dashboardToken: env.DASHBOARD_TOKEN || '',
    dashboardHost: env.DASHBOARD_HOST || '127.0.0.1', dashboardPort: num('DASHBOARD_PORT', 8787, 1, 65535),
    alertScore: num('ALERT_SCORE', 72, 1, 100), strongAlertScore: num('STRONG_ALERT_SCORE', 82, 1, 100),
    maxCandidateAgeMin: num('MAX_CANDIDATE_AGE_MIN', 120), maxCandidates: num('MAX_CANDIDATES', 1000, 10, 10000),
    enrichIntervalMs: num('ENRICH_INTERVAL_MS', 15000, 1000), batchSize: num('BATCH_SIZE', 30, 1, 80),
    marketBatchPauseMs: num('MARKET_BATCH_PAUSE_MS', 1000, 250),
    metadataPauseMs: num('METADATA_PAUSE_MS', 2000, 1000),
    jupiterPollMs: num('JUPITER_POLL_MS', 60000, 10000), dexProfilePollMs: num('DEX_PROFILE_POLL_MS', 60000, 10000),
    securityTtlMs: num('SECURITY_TTL_MS', 300000, 10000), jupiterTtlMs: num('JUPITER_TTL_MS', 120000, 10000),
    freshMs: num('FRESH_MS', 120000, 1000), horizonToleranceMs: num('HORIZON_TOLERANCE_MS', 90000, 1000),
    dexRpm: num('DEX_RPM', 120, 1, 240), jupiterRpm: num('JUPITER_RPM', 30, 1, 1000), heliusRpm: num('HELIUS_RPM', 60, 1, 1000),
    snapshotIntervalMs: num('SNAPSHOT_INTERVAL_MS', 60000, 1000),
    thinSnapshotIntervalMs: num('THIN_SNAPSHOT_INTERVAL_MS', 300000, 1000),
    snapshotDays: num('SNAPSHOT_RETENTION_DAYS', 7), notifyTtlMs: num('NOTIFICATION_TTL_MS', 900000, 1000),
    requireSecurity: bool('REQUIRE_SECURITY', true), notificationsEnabled: bool('NOTIFICATIONS_ENABLED', false),
    operationalNotifications: bool('OPERATIONAL_NOTIFICATIONS', false),
    researchFocusLimit: num('RESEARCH_FOCUS_LIMIT', 60, 1, 120),
    researchEnabled: bool('RESEARCH_ENABLED', true), researchNotifications: bool('RESEARCH_NOTIFICATIONS', false),
    dataDir: path.resolve(env.DATA_DIR || './data'),
  };
  if(!['direct','shared'].includes(c.pumpPortalSource)||
     (c.pumpPortalSource==='direct'&&c.pumpPortalSocket)||
     (c.pumpPortalSource==='shared'&&(!path.isAbsolute(c.pumpPortalSocket)||
       path.normalize(c.pumpPortalSocket)!==c.pumpPortalSocket||Buffer.byteLength(c.pumpPortalSocket)>100)))
    throw new Error('Invalid PumpPortal source configuration');
  if(c.researchNotifications&&!c.researchEnabled)throw new Error('RESEARCH_NOTIFICATIONS requires RESEARCH_ENABLED=true');
  if (c.strongAlertScore < c.alertScore) throw new Error('STRONG_ALERT_SCORE must be >= ALERT_SCORE');
  if (!['127.0.0.1', '::1', 'localhost'].includes(c.dashboardHost) && c.dashboardToken.length < 24) throw new Error('Non-loopback hosting requires DASHBOARD_TOKEN of at least 24 characters');
  if (c.notificationsEnabled && (!c.telegramBotToken || !c.telegramChatId)) throw new Error('Enabled notifications require Telegram token and chat ID');
  return c;
}
export const config = readConfig();
