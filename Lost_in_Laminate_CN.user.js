// ==UserScript==
// @name         Lost in Laminate zhCN Translation (10.0f)
// @namespace    mailto:aboutmetal@sina.com
// @version      1.1.1
// @description  Lost in Laminate 10.0f GPT 汉化 + 人工润色，by aboutmetal (zacmerkl)
// @match        https://iconoclast.neocities.org/Lost%20in%20Laminate%2010.0f/Lost%20in%20Laminate%2010.0f
// @run-at       document-start
// @grant        GM_getResourceText
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      raw.githubusercontent.com
// @updateURL    https://raw.githubusercontent.com/zacmerkl/lil-cn/main/Lost_in_Laminate_CN.user.js
// @downloadURL  https://raw.githubusercontent.com/zacmerkl/lil-cn/main/Lost_in_Laminate_CN.user.js
// @supportURL   https://github.com/zacmerkl/lil-cn/issues
// @homepage     https://github.com/zacmerkl/lil-cn
// @resource     translations_init  https://raw.githubusercontent.com/zacmerkl/lil-cn/main/LiL-10.0f-zhCN.json
// ==/UserScript==

/* -------- CONFIG -------- */
const REMOTE_URL        = 'https://raw.githubusercontent.com/zacmerkl/lil-cn/main/LiL-10.0f-zhCN.json';
const CACHE_KEY_DICT    = 'LiL-10.0f-zhCN_dict';
const CACHE_KEY_HASH    = 'LiL-10.0f-zhCN_hash';
const ASK_BEFORE_RELOAD = true;
const REMOTE_TIMEOUT_MS = 15000;
/* ------------------------ */

/* -------- 排版增强 ------- */
GM_addStyle(`
  tw-story tw-passage {
    line-height: 1.8em !important;
    font-size: 14pt;
    font-family: "Open Sans", sans-serif !important;
    letter-spacing: 0.01em;
    color: #E0E0E0;
  }
  tw-story tw-passage p {
    margin: 1em 0 1em 0 !important;
  }
  tw-story tw-passage b,
  tw-story tw-passage strong {
    font-size: 16pt !important;
    letter-spacing: 0.05em !important;
    color: #FFFFFF;
  }
  tw-story tw-passage em,
  tw-story tw-passage i {
    letter-spacing: 0.05em !important;
    border-bottom: 1px dotted currentColor !important;
    padding: 0 1px !important;
  }
`);
/* ------------------------ */

(function () {
  'use strict';

  /* ---------- 加载译文：缓存 → 本地 dev → 初始化快照 ---------- */
  let dict = {};
  try {
    const cached = GM_getValue(CACHE_DICT_KEY, null);
    if (cached) {
      dict = JSON.parse(cached);
    } else {
      const dev = tryRes('translations_dev') || tryRes('translations_init') || '{}';
      dict = JSON.parse(dev);
    }
  } catch (e) { console.error('[LiL-CN] 译文解析失败', e); dict = {}; }

  function tryRes(name) { try { return GM_getResourceText(name); } catch { return null; } }

  /* ---------- 翻译函数 ---------- */
  const normalize = s => String(s).replace(/\r\n?/g, '\n');

  const translateOne = el => {
    if (!el?.matches?.('tw-passagedata[name]')) return;
    const v = dict[el.getAttribute('name')];
    if (v == null) return;
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(document.createTextNode(normalize(v)));
  };

  const translateAll = () => document.querySelectorAll('tw-passagedata[name]').forEach(translateOne);

  /* ---------- MutationObserver 捕捉后续节点 ---------- */
  new MutationObserver(muts => muts.forEach(mu => mu.addedNodes.forEach(translateOne)))
    .observe(document.documentElement, { childList: true, subtree: true });

  /* ---------- 多重兜底扫描 ---------- */
  translateAll();
  document.addEventListener('DOMContentLoaded', translateAll, { once: true });
  window.addEventListener('load', translateAll, { once: true });
  let n = 0; const t = setInterval(() => { translateAll(); if (++n > 10) clearInterval(t); }, 100);

  /* ---------- 后台检查译文（If-None-Match / ETag） ---------- */
  checkRemote();

  function checkRemote() {
    const cachedEtag = GM_getValue(CACHE_ETAG_KEY, null);
    const headers = cachedEtag ? { 'If-None-Match': cachedEtag } : {};
    GM_xmlhttpRequest({
      method: 'GET',
      url: REMOTE_URL,
      headers,
      timeout: REMOTE_TIMEOUT_MS,
      anonymous: true,   // 减少 CORS preflight
      onload: resp => {
        // 304 = 无更新
        if (resp.status === 304) return;

        if (resp.status !== 200) {
          console.warn('[LiL-CN] 远程译文请求失败', resp.status);
          return;
        }
        const newEtag = getHeader(resp, 'etag');
        const body = resp.responseText;
        let remoteDict;
        try {
          remoteDict = JSON.parse(body);
        } catch (e) {
          console.warn('[LiL-CN] 远程JSON解析失败', e);
          return;
        }

        // 写缓存
        GM_setValue(CACHE_DICT_KEY, body);
        if (newEtag) GM_setValue(CACHE_ETAG_KEY, newEtag);

        console.log('[LiL-CN] 译文已更新，刷新以应用。');
        if (ASK_BEFORE_RELOAD) {
          if (document.visibilityState === 'hidden' || confirm('检测到新版中文译文，刷新以应用？')) {
            location.reload();
          }
        } else {
          location.reload();
        }
      },
      onerror: () => console.warn('[LiL-CN] 远程译文请求错误')
    });
  }

  function getHeader(resp, key) {
    if (typeof resp.getResponseHeader === 'function') return resp.getResponseHeader(key);
    const match = resp.responseHeaders?.match(new RegExp(`^${key}:\\s*(.*)$`,`im`));
    return match ? match[1].trim() : null;
  }

})();