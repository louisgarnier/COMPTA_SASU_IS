#!/usr/bin/env zsh
# Viber hook — forwards Claude Code events to the app
# Always exits 0 so it never blocks Claude

# Ensure common bin dirs are in PATH (node via Homebrew, nvm, fnm, volta, etc.)
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.nvm/versions/node/*/bin:$HOME/.local/bin:$HOME/.volta/bin:$PATH"

RAW=$(cat)

MAPPED=$(node -e "
try {
  const raw = process.argv[1];
  const data = JSON.parse(raw);
  const typeMap = {
    PreToolUse: 'tool_use',
    PostToolUse: 'tool_result',
    PostToolUseFailure: 'tool_failure',
    UserPromptSubmit: 'user_message',
    Stop: 'thinking_end',
    PermissionRequest: 'permission_request',
    Notification: 'notification',
    SessionStart: 'session_start',
    SessionEnd: 'session_end',
    SubagentStop: 'subagent_stop',
    PreCompact: 'pre_compact',
  };
  const hookType = data.hook_event_name || data.event || '';
  const out = {
    agentId: process.env.CLAUDE_AGENT_ID || 'unknown',
    projectId: process.env.CLAUDE_PROJECT_ID || 'unknown',
    eventType: typeMap[hookType] || hookType,
    timestamp: new Date().toISOString(),
    data: data,
    source: 'hook'
  };
  process.stdout.write(JSON.stringify(out));
} catch(e) {
  process.stdout.write('{}');
}
" "$RAW" 2>/dev/null) || MAPPED="{}"

# Fast timeout (500ms), try dev port first then prod, with 1 retry
AUTH_HEADER="Authorization: Bearer ${VIBER_HOOK_TOKEN:-}"
curl -sf --connect-timeout 0.5 --max-time 1 -X POST \
  -H "Content-Type: application/json" -H "$AUTH_HEADER" \
  -d "$MAPPED" "http://127.0.0.1:3061/hooks/agent-event" >/dev/null 2>&1 || \
curl -sf --connect-timeout 0.5 --max-time 1 -X POST \
  -H "Content-Type: application/json" -H "$AUTH_HEADER" \
  -d "$MAPPED" "http://127.0.0.1:3067/hooks/agent-event" >/dev/null 2>&1 || true

exit 0
