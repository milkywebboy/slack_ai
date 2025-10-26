// ①SSEブリッジを起動
// uvx mcp-proxy --transport sse --host 127.0.0.1 --port 3000 -- npx -y @modelcontextprotocol/server-filesystem /Users/yuta/slack_ai/src/asset/notion_export_md

// ①'停止
// lsof -i :3000 | awk 'NR>1{print $2}' | xargs -r kill

// ②ngrokで公開（Basic認証付き）
// ngrok http 3000 --basic-auth 'techfund:aJWCydQaJKZUx8sxVgBC'

import { serve } from "@modelcontextprotocol/server-filesystem";

serve({
  root: "/Users/yuta/slack_ai/src/asset/notion_export_md/", // ←あなたの実パス
  port: 3000
});