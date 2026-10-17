#!/usr/bin/env node
/*
 * render_harness.cjs — 渲染级检测 harness（⑨ E 组升级：子串检查 → 渲染级比对）
 * 用法：node render_harness.cjs <index.html路径> <json数据路径>
 * 输出：JSON {元素id: {innerHTML, textContent, className}}
 * 方法：stub DOM + fetch，真实执行页面 <script>（含 render()），取渲染产物比对。
 */
const fs = require('fs');
const [pagePath, jsonPath] = process.argv.slice(2);
const page = fs.readFileSync(pagePath, 'utf8');
const DATA = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
const m = page.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error('no script block'); process.exit(2); }
const src = m[1];
const reg = {};
function mkEl() {
  return { innerHTML: '', textContent: '', className: '', style: {},
    appendChild(c) { this.children = this.children || []; this.children.push(c); },
    insertAdjacentHTML(pos, html) { this.innerHTML += html; } };
}
const document = {
  getElementById(id) { if (!reg[id]) reg[id] = mkEl(); return reg[id]; },
  createElement(tag) { return mkEl(); },
};
const fetch = () => Promise.resolve({ json: () => Promise.resolve(DATA) });
new Function('document', 'fetch', src)(document, fetch);
Promise.resolve().then(() => Promise.resolve()).then(() => {
  const out = {};
  for (const [id, el] of Object.entries(reg))
    out[id] = { innerHTML: el.innerHTML, textContent: el.textContent, className: el.className };
  console.log('RENDER_JSON_START');
  console.log(JSON.stringify(out));
});
