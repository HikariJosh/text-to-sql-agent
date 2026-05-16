<template>
  <div class="chat">
    <div ref="messagesEl" class="messages">
      <!-- 空状态 -->
      <div v-if="messages.length === 0" class="empty">
        <div class="empty-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M4 7h16M4 12h16M4 17h10"/>
          </svg>
        </div>
        <h1>Data Agent</h1>
        <p>输入自然语言，查询你的数据</p>
        <div v-if="examples.length" class="examples">
          <button v-for="ex in examples" :key="ex" @click="fillExample(ex)">{{ ex }}</button>
          <button class="refresh-btn" @click="fetchSuggestions" :disabled="suggestionsLoading" title="换一批">
            <svg :class="{spinning: suggestionsLoading}" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- 消息 -->
      <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
        <div v-if="msg.role === 'user'" class="bubble-user">{{ msg.content }}</div>

        <template v-else>
          <div v-if="msg.type === 'steps'" class="steps">
            <template v-for="(s, j) in msg.steps" :key="j">
              <span :class="['step', s.status === 'success' ? 'done' : '']"><span class="dot" :class="s.status"></span>{{ s.text }}</span>
              <span v-if="j < msg.steps.length - 1" class="sep">→</span>
            </template>
          </div>

          <!-- 思考：流式逐字输出，支持 markdown 渲染 -->
          <div v-else-if="msg.type === 'thinking'" class="card think-card">
            <button class="card-head" @click="msg.expanded = !msg.expanded">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" :class="{open: msg.expanded}"><polyline points="9 18 15 12 9 6"/></svg>
              思考过程
              <span v-if="msg.streaming" class="think-live">●</span>
            </button>
            <div v-if="msg.expanded" class="card-body md-body" v-html="renderMd(msg.content)"></div>
          </div>

          <div v-else-if="msg.type === 'sql'" class="card sql-card">
            <div class="card-top"><span class="tag">SQL</span>
              <button class="copy" @click="copySql(msg.sql)">{{ copied ? '✓' : '复制' }}</button>
            </div>
            <pre><code>{{ msg.sql }}</code></pre>
          </div>

          <!-- 表格：右侧可折叠面板 -->
          <div v-else-if="msg.type === 'table'" class="table-panel">
            <button class="table-toggle" @click="msg.expanded = !msg.expanded">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" :class="{open: msg.expanded}"><polyline points="9 18 15 12 9 6"/></svg>
              <span>{{ msg.rows.length }} 条结果</span>
            </button>
            <Transition name="expand">
              <div v-if="msg.expanded" class="card tbl-card">
                <div class="tbl-wrap">
                  <table>
                    <thead><tr><th v-for="c in msg.columns" :key="c">{{ c }}</th></tr></thead>
                    <tbody><tr v-for="(r, ri) in msg.rows" :key="ri">
                      <td v-for="c in msg.columns" :key="c" :class="{num: typeof r[c]==='number'}">{{ fmt(r[c]) }}</td>
                    </tr></tbody>
                  </table>
                </div>
              </div>
            </Transition>
          </div>

          <div v-else-if="msg.type === 'text'" class="text">{{ msg.content }}</div>

          <div v-else-if="msg.type === 'error'" class="err">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ msg.content }}
          </div>
        </template>
      </div>
      <div class="bottom-pad"></div>
    </div>

    <!-- 输入 -->
    <div class="input-wrap">
      <div class="input-bar">
        <textarea ref="inputEl" v-model="question" @keydown.enter.exact.prevent="send" placeholder="输入你的问题..." rows="1" :disabled="loading"></textarea>
        <button class="send-btn" @click="send" :disabled="loading || !question.trim()">
          <svg v-if="!loading" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>
          <span v-else class="spin"></span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import {nextTick, onMounted, ref} from "vue";
import {marked} from "marked";

const API_URL = "/api/query";

const question = ref("");
const loading = ref(false);
const messages = ref([]);
const chatHistory = ref([]);
const messagesEl = ref(null);
const inputEl = ref(null);
const copied = ref(false);
const examples = ref([]);
const suggestionsLoading = ref(false);

async function fetchSuggestions() {
  suggestionsLoading.value = true;
  try {
    const res = await fetch("/api/suggestions");
    const data = await res.json();
    if (data.suggestions?.length) examples.value = data.suggestions;
  } catch {} finally {
    suggestionsLoading.value = false;
  }
}

onMounted(fetchSuggestions);

const ALL_STEPS = [
  "抽取关键字", "召回字段", "召回字段取值", "召回指标",
  "合并召回信息", "过滤表格", "过滤指标", "添加额外上下文信息",
  "思考分析", "生成SQL", "验证SQL", "执行SQL", "生成总结",
];

function fillExample(ex) { question.value = ex; inputEl.value?.focus(); }
function newChat() { messages.value = []; chatHistory.value = []; fetchSuggestions(); }
function fmt(v) { return v == null ? "—" : typeof v === "number" ? v.toLocaleString() : v; }
async function copySql(sql) { await navigator.clipboard.writeText(sql); copied.value = true; setTimeout(() => copied.value = false, 2000); }
function scroll() { const el = messagesEl.value; if (el) el.scrollTop = el.scrollHeight; }
function renderMd(text) { return marked.parse(text || ""); }

async function send() {
  if (!question.value.trim() || loading.value) return;
  const q = question.value.trim();
  question.value = "";
  loading.value = true;
  messages.value.push({role: "user", type: "text", content: q});
  const si = messages.value.push({role: "assistant", type: "steps", steps: ALL_STEPS.map(t => ({text: t, status: "pending"}))}) - 1;
  await nextTick(); scroll();

  // 记录当前思考消息的索引（用于流式追加）
  let thinkingIdx = -1;

  try {
    const res = await fetch(API_URL, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({query: q, chat_history: chatHistory.value})});
    if (!res.body) throw new Error("服务器未返回流");
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream: true});
      const parts = buf.split("\n\n"); buf = parts.pop();
      for (const p of parts) {
        const line = p.trim();
        if (!line.startsWith("data:")) continue;
        let d; try { d = JSON.parse(line.replace(/^data:\s*/, "")); } catch { continue; }
        const steps = messages.value[si].steps;

        if (d.type === "progress") {
          let s = steps.find(s => s.text === d.step);
          if (s) s.status = d.status;
          // 思考完成：关闭流式状态并自动折叠
          if (d.step === "思考分析" && d.status === "success" && thinkingIdx >= 0) {
            messages.value[thinkingIdx].streaming = false;
            messages.value[thinkingIdx].expanded = false;
            thinkingIdx = -1;
          }
        }
        else if (d.type === "thinking") {
          if (d.stream) {
            // 流式追加
            if (thinkingIdx < 0) {
              thinkingIdx = messages.value.length;
              messages.value.push({role: "assistant", type: "thinking", content: d.content, expanded: true, streaming: true});
            } else {
              messages.value[thinkingIdx].content += d.content;
            }
          } else {
            // 一次性输出（兼容）
            messages.value.push({role: "assistant", type: "thinking", content: d.content, expanded: false, streaming: false});
          }
        }
        else if (d.type === "sql") { chatHistory.value.push({role: "user", content: q}, {role: "assistant", content: d.sql}); messages.value.push({role: "assistant", type: "sql", sql: d.sql}); }
        else if (d.type === "clarify") messages.value.push({role: "assistant", type: "text", content: d.message});
        else if (d.type === "result" && Array.isArray(d.data)) messages.value.push({role: "assistant", type: "table", columns: Object.keys(d.data[0] || {}), rows: d.data, expanded: true});
        else if (d.type === "summary") messages.value.push({role: "assistant", type: "text", content: d.content});
        else if (d.type === "error") messages.value.push({role: "assistant", type: "error", content: d.message || "发生错误"});
        await nextTick(); scroll();
      }
    }
  } catch (e) {
    messages.value.push({role: "assistant", type: "error", content: e?.message || "请求失败"});
  } finally { loading.value = false; await nextTick(); scroll(); }
}
</script>

<style>
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, sans-serif;
  color: #1a1a1a;
  background: #fff;
  -webkit-font-smoothing: antialiased;
}
</style>

<style scoped>
.chat { height: 100%; display: flex; flex-direction: column; }

.messages { flex: 1; overflow-y: auto; }
.messages::-webkit-scrollbar { width: 5px; }
.messages::-webkit-scrollbar-thumb { background: #d4d4d4; border-radius: 4px; }
.messages::-webkit-scrollbar-track { background: transparent; }

/* ── empty ── */
.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 8px; }
.empty-icon { width: 52px; height: 52px; border-radius: 14px; background: #f5f5f7; display: flex; align-items: center; justify-content: center; color: #1a1a1a; margin-bottom: 12px; }
.empty h1 { font-size: 26px; font-weight: 600; letter-spacing: -0.3px; }
.empty p { font-size: 14px; color: #999; margin-bottom: 28px; }
.examples { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; align-items: center; }
.examples button { padding: 7px 16px; border-radius: 100px; border: 1px solid #e5e5e5; background: #fff; font-size: 13px; color: #1a1a1a; cursor: pointer; transition: background .12s, border-color .12s; }
.examples button:hover { background: #f7f7f7; border-color: #ccc; }
.refresh-btn { width: 32px; height: 32px; padding: 0; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #999; }
.refresh-btn:hover { color: #1a1a1a; }
.spinning { animation: spin .8s linear infinite; }

/* ── messages ── */
.msg { max-width: 700px; margin: 0 auto; padding: 6px 24px; width: 100%; }
.msg.user { display: flex; justify-content: flex-end; }

.bubble-user { background: #1a1a1a; color: #fff; padding: 10px 16px; border-radius: 18px 18px 4px 18px; font-size: 14px; line-height: 1.5; max-width: 420px; word-break: break-word; }

.msg.assistant { font-size: 14px; line-height: 1.65; }

/* steps */
.steps { display: flex; flex-wrap: wrap; align-items: center; gap: 3px 6px; font-size: 12px; color: #aaa; padding: 4px 0; }
.step { display: inline-flex; align-items: center; gap: 4px; }
.dot { width: 7px; height: 7px; border-radius: 50%; transition: background .2s; }
.dot.pending { background: #e0e0e0; }
.dot.running { background: #f5a623; animation: pulse-dot 1s ease-in-out infinite; }
@keyframes pulse-dot { 0%,100% { opacity:1; } 50% { opacity:.4; } }
.dot.success { background: #34c759; }
.dot.error { background: #ff3b30; }
.step.done { color: #bbb; }
.sep { color: #eee; margin: 0 1px; font-size: 9px; }

/* card */
.card { border: 1px solid #eaeaea; border-radius: 10px; overflow: hidden; margin: 8px 0; }
.card-top { display: flex; align-items: center; justify-content: space-between; padding: 8px 14px; background: #fafafa; border-bottom: 1px solid #eaeaea; }
.tag { font-size: 11px; font-weight: 600; color: #999; text-transform: uppercase; letter-spacing: .04em; }
.copy { font-size: 11px; color: #999; background: none; border: 1px solid #ddd; border-radius: 5px; padding: 2px 8px; cursor: pointer; transition: all .12s; }
.copy:hover { color: #1a1a1a; border-color: #bbb; }

/* thinking */
.think-card { background: #fafafa; border-color: #eee; overflow: visible; }
.card-head { display: flex; align-items: center; gap: 5px; width: 100%; padding: 8px 14px; border: none; background: none; font-size: 12.5px; font-weight: 500; color: #999; cursor: pointer; transition: color .12s; }
.card-head:hover { color: #555; }
.card-head svg { transition: transform .2s; }
.card-head svg.open { transform: rotate(90deg); }
.card-body { padding: 8px 14px 12px; font-size: 13px; line-height: 1.7; color: #666; }
.md-body p { margin: 0 0 8px; }
.md-body p:last-child { margin-bottom: 0; }
.md-body strong { font-weight: 600; color: #444; }
.md-body ul, .md-body ol { margin: 4px 0 4px 16px; padding-left: 16px; }
.md-body li { margin: 2px 0; }
.md-body code { background: #e8e8e8; padding: 1px 4px; border-radius: 3px; font-size: 12px; font-family: "SF Mono", Menlo, Consolas, monospace; }

.think-live { color: #34c759; font-size: 8px; margin-left: 4px; animation: pulse 1s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }

.cursor { color: #999; animation: blink 0.8s step-end infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

/* sql */
.sql-card pre { background: #1a1a1a; color: #ddd; padding: 14px; overflow-x: auto; font-size: 12.5px; line-height: 1.6; margin: 0; }
.sql-card code { font-family: "SF Mono", Menlo, Consolas, monospace; }

/* table panel */
.table-panel { margin: 8px 0; }
.table-toggle { display: flex; align-items: center; gap: 5px; padding: 6px 0; border: none; background: none; font-size: 12.5px; font-weight: 500; color: #999; cursor: pointer; transition: color .12s; }
.table-toggle:hover { color: #555; }
.table-toggle svg { transition: transform .2s; }
.table-toggle svg.open { transform: rotate(90deg); }

.tbl-card { margin-top: 4px; }
.tbl-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { padding: 8px 14px; text-align: left; font-weight: 600; font-size: 11px; color: #999; background: #fafafa; border-bottom: 1px solid #eaeaea; white-space: nowrap; text-transform: uppercase; letter-spacing: .03em; position: sticky; top: 0; }
td { padding: 7px 14px; border-bottom: 1px solid #f2f2f2; white-space: nowrap; }
td.num { font-variant-numeric: tabular-nums; text-align: right; }
tr:last-child td { border-bottom: none; }
tbody tr:hover { background: #f8f8fa; }

/* expand transition */
.expand-enter-active, .expand-leave-active { transition: all .2s ease; overflow: hidden; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; }

/* text */
.text { padding: 4px 0; font-size: 14px; }

/* error */
.err { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 8px; background: #fff5f5; color: #d00; font-size: 13px; }

.bottom-pad { height: 80px; }

/* ── input ── */
.input-wrap { padding: 0 24px 20px; background: linear-gradient(to top, #fff 60%, transparent); }
.input-bar { max-width: 700px; margin: 0 auto; display: flex; align-items: flex-end; gap: 8px; padding: 10px 10px 10px 16px; border: 1px solid #e0e0e0; border-radius: 14px; background: #fff; box-shadow: 0 2px 12px rgba(0,0,0,.04); transition: border-color .15s, box-shadow .15s; }
.input-bar:focus-within { border-color: #1a1a1a; box-shadow: 0 2px 16px rgba(0,0,0,.08); }

textarea { flex: 1; border: none; outline: none; background: none; font-size: 14px; font-family: inherit; color: #1a1a1a; resize: none; line-height: 1.45; max-height: 120px; }
textarea::placeholder { color: #bbb; }

.send-btn { width: 32px; height: 32px; border-radius: 9px; border: none; background: #1a1a1a; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: opacity .12s, transform .1s; }
.send-btn:active:not(:disabled) { transform: scale(.93); }
.send-btn:disabled { opacity: .2; cursor: default; }

.spin { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; border-radius: 50%; animation: sp .6s linear infinite; }
@keyframes sp { to { transform: rotate(360deg); } }

@media (max-width: 640px) { .msg { padding: 6px 16px; } .input-wrap { padding: 0 16px 16px; } .bubble-user { max-width: 85%; } }
</style>
