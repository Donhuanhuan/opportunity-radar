// 专用 Edge profile 一次性登录助手（知乎 + 小红书创作者平台）
// 用法: node login.js   （默认 180s/站，可用 LOGIN_WAIT_SECONDS 覆盖）
const { chromium } = require('playwright');
const path = require('path');

const EDGE_USER_DATA = process.env.EDGE_USER_DATA
  || path.join(process.env.LOCALAPPDATA, 'Microsoft', 'Edge', 'User Data');
const EDGE_EXE = process.env.EDGE_EXE
  || path.join(process.env['PROGRAMFILES(X86)'] || process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe');
const WAIT = parseInt(process.env.LOGIN_WAIT_SECONDS || '180', 10);
const SITES = (process.env.LOGIN_SITES || 'zhihu,xiaohongshu').split(',').map(s => s.trim()).filter(Boolean);

(async () => {
  console.log('[login] 专用 profile:', EDGE_USER_DATA);
  const browser = await chromium.launchPersistentContext(EDGE_USER_DATA, {
    executablePath: EDGE_EXE, headless: false,
    viewport: { width: 1280, height: 860 },
    args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'],
  });
  const page = await browser.newPage();
  await page.addInitScript(() => Object.defineProperty(navigator, 'webdriver', { get: () => undefined }));
  for (const site of SITES) {
    const url = site === 'xiaohongshu'
      ? 'https://creator.xiaohongshu.com'
      : 'https://www.zhihu.com/creator';
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    console.log(`[login] 请在弹窗登录「${site}」创作者平台，${WAIT} 秒后自动切换/关闭…`);
    await page.waitForTimeout(WAIT * 1000);
  }
  await browser.close();
  console.log('[login] 完成：登录态已保存到专用 profile。');
})().catch(e => { console.error('[login] 失败:', e.message); process.exit(1); });
