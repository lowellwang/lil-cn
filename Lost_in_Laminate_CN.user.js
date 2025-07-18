// ==UserScript==
// @name         Lost in Laminate zhCN Translation (10.0f)
// @namespace    mailto:aboutmetal@sina.com
// @version      1.1.2
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

  /* -------- CONFIG -------- */
  const REMOTE_URL        = 'https://raw.githubusercontent.com/zacmerkl/lil-cn/main/LiL-10.0f-zhCN.json';
  const CACHE_DICT_KEY    = 'LiL-10.0f-zhCN_dict';
  const CACHE_ETAG_KEY    = 'LiL-10.0f-zhCN_hash';
  const ASK_BEFORE_RELOAD = true;
  const REMOTE_TIMEOUT_MS = 15000;
  /* ------------------------ */

  /* ---------- 工具 ---------- */
  const normalize = s => String(s).replace(/\r\n?/g, '\n');
  const tryRes    = name => { try { return GM_getResourceText(name); } catch { return null; } };

  /* ---------- 加载译文 ---------- */
  let dict = {};
  try{
    const cacheStr = GM_getValue(CACHE_DICT_KEY,null);
    if(cacheStr){ dict=JSON.parse(cacheStr);}
    else{
      const dev = tryRes('translations_dev');
      dict = dev ? JSON.parse(dev) : JSON.parse(tryRes('translations_init')||'{}');
    }
  }catch(e){console.error('[LiL-CN] 译文解析失败',e);}

  /* ---------- 翻译函数 ---------- */
  function translateOne(el){
    if(!el?.matches?.('tw-passagedata[name]'))return;
    const cn = dict[el.getAttribute('name')];
    if(cn==null)return;
    while(el.firstChild)el.removeChild(el.firstChild);
    el.appendChild(document.createTextNode(normalize(cn)));
  }
  const translateAll=()=>document.querySelectorAll('tw-passagedata[name]').forEach(translateOne);

  /* ---------- 监听 & 初次翻译 ---------- */
  new MutationObserver(m=>m.forEach(mu=>mu.addedNodes.forEach(translateOne)))
    .observe(document.documentElement,{childList:true,subtree:true});

  translateAll();
  document.addEventListener('DOMContentLoaded',translateAll,{once:true});
  window.addEventListener('load',translateAll,{once:true});
  let k=0;const id=setInterval(()=>{translateAll();if(++k>10)clearInterval(id);},100);

  /* ---------- 远程检查 (ETag) ---------- */
  const etag = GM_getValue(CACHE_ETAG_KEY,null);
  GM_xmlhttpRequest({
    method:'GET',
    url:REMOTE_URL,
    timeout:REMOTE_TIMEOUT_MS,
    headers: etag ? {'If-None-Match':etag} : {},
    anonymous:true,
    onload:r=>{
      if(r.status===304) return;            // 无更新
      if(r.status!==200){console.warn('[LiL-CN] 译文请求失败',r.status);return;}
      const newEtag = getHeader(r,'etag');
      const body=r.responseText;
      try{
        JSON.parse(body);  // 验证格式
        GM_setValue(CACHE_DICT_KEY,body);
        if(newEtag)GM_setValue(CACHE_ETAG_KEY,newEtag);
        console.log('[LiL-CN] 译文已更新');
        if(!ASK_BEFORE_RELOAD||document.visibilityState==='hidden'||confirm('发现新版译文，刷新应用？')){
          location.reload();
        }
      }catch(e){console.warn('[LiL-CN] 远程译文解析失败',e);}
    }
  });

  function getHeader(resp,key){
    if(typeof resp.getResponseHeader==='function') return resp.getResponseHeader(key);
    const m=resp.responseHeaders?.match(new RegExp(`^${key}:\\s*(.*)$`,'im'));
    return m?m[1].trim():null;
  }

})();