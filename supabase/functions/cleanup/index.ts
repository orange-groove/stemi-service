// Follow this setup guide to integrate the Deno language server with your editor:
// https://deno.land/manual/getting_started/setup_your_environment
// This enables autocomplete, go to definition, etc.

// @ts-nocheck
// Setup type definitions for built-in Supabase Runtime APIs
import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

/**
 * Scheduled cleanup function
 * - Intended to be invoked by Supabase Scheduled Functions (cron)
 * - Triggers your app's cleanup endpoint to remove local temp sessions older than 24h
 * - Optionally configurable window via ?hours= query param (default 24)
 *
 * Environment variables to set via `supabase secrets set`:
 * - APP_CLEANUP_URL=https://your-api.example.com/api/v1/cleanup
 * - CRON_SECRET=strong-shared-secret  (used for authenticating the request)
 *
 * Example schedule: hourly
 */

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

async function cleanupFromDB(hours: number) {
  const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
  const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const BUCKET = "stems";
  const client = createClient(SUPABASE_URL, SERVICE_ROLE);

  const cutoff = new Date(Date.now() - hours * 60 * 60 * 1000);

  // 1) find sessions older than cutoff
  const { data: sessions, error } = await client
    .from("sessions")
    .select("session_id, storage_prefix")
    .lt("created_at", cutoff.toISOString());
  if (error) throw new Error(error.message);

  if (!sessions || sessions.length === 0) {
    return { deletedObjects: 0, deletedSessions: 0 };
  }

  let deletedObjects = 0;

  // 2) delete objects under each storage_prefix
  for (const row of sessions) {
    const prefix: string = row.storage_prefix;
    // list files under prefix (paginate if needed later)
    const list = await client.storage.from(BUCKET).list(prefix, { limit: 1000 });
    if (list.error) continue;
    const files = list.data ?? [];
    if (files.length === 0) continue;
    const removePaths = files.map((f) => `${prefix}/${f.name}`);
    const { error: remErr } = await client.storage.from(BUCKET).remove(removePaths);
    if (!remErr) deletedObjects += removePaths.length;
  }

  // 3) delete session rows
  const ids = sessions.map((s) => s.session_id);
  const { error: delErr } = await client.from("sessions").delete().in("session_id", ids);
  if (delErr) throw new Error(delErr.message);

  return { deletedObjects, deletedSessions: ids.length };
}

Deno.serve(async (req) => {
  try {
    let hours = 24
    // Allow overriding via query (?hours=)
    try {
      const url = new URL(req.url)
      const q = url.searchParams.get("hours")
      if (q) hours = Math.max(1, parseInt(q)) || 24
    } catch (_) {}

    const result = await cleanupFromDB(hours)
    return jsonResponse({ message: "cleanup completed", hours, result })
  } catch (e) {
    return jsonResponse({ error: (e as Error).message }, 500)
  }
})

/* To invoke locally:

  1. Run `supabase start` (see: https://supabase.com/docs/reference/cli/supabase-start)
  2. Make an HTTP request:

  curl -i --location --request POST 'http://127.0.0.1:54321/functions/v1/cleanup?hours=24' \
    --header 'Authorization: Bearer ANON_OR_SERVICE_ROLE_TOKEN' \
    --header 'Content-Type: application/json'

*/
