// ==UserScript==
// @name         Lost in Laminate zhCN Translation (10.0f)
// @namespace    mailto:aboutmetal@sina.com
// @version      2.0-10.0f
// @description  Lost in Laminate 8.0 GPT 汉化 + 人工润色，by aboutmetal (zacmerkl)
// @match        https://iconoclast.neocities.org/Lost%20in%20Laminate%2010.0f/Lost%20in%20Laminate%2010.0f
// @run-at       document-start
// @grant        GM_getResourceText
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_deleteValue
// @connect      raw.githubusercontent.com
// @connect      localhost
// @updateURL    https://raw.githubusercontent.com/zacmerkl/lil-cn/main/Lost_in_Laminate_CN.user.js
// @downloadURL  https://raw.githubusercontent.com/zacmerkl/lil-cn/main/Lost_in_Laminate_CN.user.js
// @supportURL   https://github.com/zacmerkl/lil-cn/issues
// @homepage     https://github.com/zacmerkl/lil-cn
// @resource     translations_init  https://raw.githubusercontent.com/zacmerkl/lil-cn/main/LiL-10.0f-zhCN.json
// ==/UserScript==

/* ------------------------------------------------------------------
 * 排版增强
 * ---------------------------------------------------------------- */
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

(function () {
  'use strict';

  const REMOTE_URL        = 'https://raw.githubusercontent.com/zacmerkl/lil-cn/main/LiL-10.0f-zhCN.json';
  const CACHE_KEY_DICT    = 'LiL-10.0f-zhCN_dict';
  const CACHE_KEY_HASH    = 'LiL-10.0f-zhCN_hash';
  const ASK_BEFORE_RELOAD = true;
  const REMOTE_TIMEOUT_MS = 15000;

  let dict = {};
  try {
    const cachedStr = GM_getValue(CACHE_KEY_DICT, null);
    if (cachedStr) {
      dict = JSON.parse(cachedStr);
    } else {
      const initStr = GM_getResourceText('translations_init');
      dict = initStr ? JSON.parse(initStr) : {};
    }
  } catch (e) {
    console.error('[LiL‑CN] 本地翻译加载失败:', e);
    dict = {};
  }

  function normalize(str) { return String(str).replace(/\r\n?/g, '\n'); }

  function translateOne(el) {
    if (!el || el.nodeType !== 1) return;
    const name = el.getAttribute('name');
    if (!name) return;
    const cnEscaped = dict[name];
    if (cnEscaped == null) return; // 没翻译
    // Twine 读取 .textContent 时自动反转义实体
    // 因此我们直接把 escaped 源写进去
    if (normalize(el.textContent) !== normalize(cnEscaped)) {
      el.textContent = cnEscaped;
    }
  }

  function translateAllExisting() {
    document.querySelectorAll('tw-passagedata[name]').forEach(translateOne);
  }

  const mo = new MutationObserver(muts => {
    for (const mu of muts) {
      for (const n of mu.addedNodes) {
        if (n.nodeType === 1) {
          if (n.matches?.('tw-passagedata[name]')) {
            translateOne(n);
          } else {
            n.querySelectorAll?.('tw-passagedata[name]').forEach(translateOne);
          }
        }
      }
    }
  });
  mo.observe(document.documentElement, { childList: true, subtree: true });

  translateAllExisting();
  document.addEventListener('DOMContentLoaded', translateAllExisting, { once: true });
  window.addEventListener('load', translateAllExisting, { once: true });

  let pollCount = 0;
  const pollMax = 10;
  const pollTimer = setInterval(() => {
    translateAllExisting();
    if (++pollCount >= pollMax) clearInterval(pollTimer);
  }, 100);

  checkRemoteTranslations();

  function checkRemoteTranslations() {
    GM_xmlhttpRequest({
      method: 'GET',
      url: REMOTE_URL + '?_=' + Date.now(),  // cache-bust
      timeout: REMOTE_TIMEOUT_MS,
      onload: (r) => {
        if (r.status !== 200) {
          console.warn('[LiL-CN] 远程译文请求失败:', r.status, r.statusText);
          return;
        }
        const txt = r.responseText;
        let remoteDict;
        try {
          remoteDict = JSON.parse(txt);
        } catch (e) {
          console.warn('[LiL-CN] 远程译文解析失败:', e);
          return;
        }
        const remoteHash = simpleHash(txt);
        const localHash  = GM_getValue(CACHE_KEY_HASH, null);

        if (remoteHash !== localHash) {
          console.log('[LiL-CN] 检测到新译文，写缓存…');
          GM_setValue(CACHE_KEY_DICT, txt);
          GM_setValue(CACHE_KEY_HASH, remoteHash);

          if (ASK_BEFORE_RELOAD) {
            if (document.visibilityState === 'hidden' || confirm('发现新版中文译文，刷新以应用？')) {
              location.reload();
            }
          } else {
            location.reload();
          }
        }
      },
      onerror: () => {
        console.warn('[LiL-CN] 远程译文请求错误。');
      }
    });
  }

  /* ----------------------------------------------------------------
   * 简易哈希：用于判断译文是否更新
   * ---------------------------------------------------------------- */
  function simpleHash(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) {
      h = (h * 31 + str.charCodeAt(i)) | 0;
    }
    return (h >>> 0).toString(16);
  }

})();
