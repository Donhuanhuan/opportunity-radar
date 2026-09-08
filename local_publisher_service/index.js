// 本地内容发布服务
// 复用本机 Edge 的 userDataDir，保留登录态，避免任何 cookie 导出/注入操作
const { chromium } = require('playwright');
const express = require('express');
const path = require('path');
const fs = require('fs');

const PORT = process.env.PORT || 19000;
const HEADLESS = process.env.HEADLESS === 'true' || process.env.HEADLESS === '1';
// dry-run 命中发布按钮后保持窗口供人工核对的秒数（可被环境变量覆盖）
const DRY_RUN_HOLD = parseInt(process.env.DRY_RUN_HOLD_SECONDS || '60', 10);

// 默认 Edge 用户数据目录（Windows）
const EDGE_USER_DATA = process.env.EDGE_USER_DATA || path.join(process.env.LOCALAPPDATA, 'Microsoft', 'Edge', 'User Data');
// Edge 可执行文件
const EDGE_EXE = process.env.EDGE_EXE || path.join(process.env['PROGRAMFILES(X86)'] || process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe');

const app = express();
app.use(express.json({ limit: '2mb' }));

function log(...args) {
  console.log(`[${new Date().toISOString()}]`, ...args);
}

function randomBetween(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

async function humanDelay(page, ms) {
  const t = ms || randomBetween(800, 2200);
  await page.waitForTimeout(t);
}

// 关闭可能遮挡点击的活动弹窗/浮层（知乎提问大赛、小红书引导等）
async function dismissModals(page) {
  try {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
  } catch (e) { /* ignore */ }
  try {
    const closers = await page.$('.Modal-closeButton')
      || await page.$('[aria-label*="关闭"]')
      || await page.$('[class*="close"]')
      || await page.$('button:has-text("关闭")')
      || await page.$('text=我知道了');
    if (closers) {
      const visible = await closers.isVisible().catch(() => false);
      if (visible) {
        await closers.evaluate((el) => el.click());
        await page.waitForTimeout(800);
      }
    }
  } catch (e) { /* ignore */ }
}

// 可见点击 -> 失败兜底 DOM 直点（绕过广告浮层/backdrop 的 pointer-events 拦截）
async function robustClick(page, handle) {
  try {
    await handle.click({ timeout: 8000 });
  } catch (e) {
    log('可见点击被拦截，改用 DOM click 兜底:', String(e.message).split('\n')[0]);
    await handle.evaluate((el) => el.click());
  }
  await page.waitForTimeout(1200);
}

async function publishXiaohongshu(page, task) {
  log('发布小红书:', task.title);
  await page.goto('https://creator.xiaohongshu.com/new', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await humanDelay(page, 3000);

  // 1. 点击发布图文按钮（新版创作者平台）
  await dismissModals(page);
  const publishBtn = await page.$('text=发布图文') || await page.$('text=发布笔记') || await page.$('text=图文') || await page.$('text=上传图文');
  if (!publishBtn) throw new Error('未找到小红书「发布图文」入口，页面可能已改版');
  await robustClick(page, publishBtn);
  await humanDelay(page, 2000);

  // 2. 上传封面（如提供图片路径）
  if (task.coverImage && fs.existsSync(task.coverImage)) {
    const uploadInput = await page.$('input[type="file"]');
    if (uploadInput) {
      await uploadInput.setInputFiles(task.coverImage);
      await humanDelay(page, 3000);
    }
  }

  // 3. 填写标题
  const titleInput = await page.$('[placeholder*="标题"], input[type="text"]') || await page.$('[placeholder*="填写标题"]');
  if (!titleInput) throw new Error('未找到小红书标题输入框');
  await titleInput.fill(task.title);
  await humanDelay(page, 1500);

  // 4. 填写正文
  const editor = await page.$('[contenteditable="true"]');
  if (!editor) throw new Error('未找到小红书正文编辑器');
  await editor.fill(task.body);
  await humanDelay(page, 1500);

  // 5. 添加话题标签（用 # 方式或点击话题按钮）
  if (task.tags && task.tags.length > 0) {
    const tagText = task.tags.map(t => (t.startsWith('#') ? t : '#' + t)).join(' ');
    await editor.fill(task.body + '\n' + tagText);
    await humanDelay(page, 2000);
  }

  // 6. 发布按钮（先 dry-run 用文本检测）
  const publishAction = await page.$('text=发布笔记') || await page.$('text=立即发布');
  if (!publishAction) throw new Error('未找到小红书发布按钮');

  if (task.dryRun) {
    log('[DRY-RUN] 已填好表单，检测到发布按钮，未点击');
    log(`[DRY-RUN] 窗口保持 ${DRY_RUN_HOLD}s 供人工核对，结束后自动关闭…`);
    await page.waitForTimeout(DRY_RUN_HOLD * 1000);
    log('[DRY-RUN] 核对窗口已关闭');
    return { platform: 'xiaohongshu', status: 'dry_run', title: task.title };
  }

  await dismissModals(page);
  await robustClick(page, publishAction);
  await humanDelay(page, 5000);

  // 7. 校验成功
  const success = await page.$('text=发布成功') || await page.$('text=审核中');
  return {
    platform: 'xiaohongshu',
    status: success ? 'published' : 'unknown',
    title: task.title
  };
}

async function publishZhihu(page, task) {
  log('发布知乎:', task.title);
  await page.goto('https://www.zhihu.com/creator', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await humanDelay(page, 3000);

  // 知乎创作中心 - 写回答/写文章
  const writeBtn = await page.$('text=写文章') || await page.$('text=写回答') || await page.$('[data-za-detail-view-id="3523"]');
  if (!writeBtn) throw new Error('未找到知乎「写文章」入口，页面可能已改版');

  // 关键：知乎点「写文章」会在新标签页打开 zhuanlan.zhihu.com/write
  const popupPromise = page.waitForEvent('popup', { timeout: 12000 }).catch(() => null);
  await robustClick(page, writeBtn);
  const popup = await popupPromise;
  if (popup) log('[zhihu] 检测到新标签页编辑器');

  // 后续操作切换到新标签页；如果未弹新页则回退到当前页（兼容旧版 SPA）
  let wp = popup || page;
  if (wp !== page) await wp.waitForLoadState('domcontentloaded', { timeout: 20000 });
  await humanDelay(wp, 2500);

  // 标题
  const titleInput = await wp.$('[placeholder*="请输入标题"]') || await wp.$('input[aria-label*="标题"]');
  if (!titleInput) throw new Error('未找到知乎标题输入框');
  await titleInput.fill(task.title);
  await humanDelay(wp, 1500);

  // 正文编辑器
  const editor = await wp.$('[contenteditable="true"]');
  if (!editor) throw new Error('未找到知乎正文编辑器');
  await editor.fill(task.body);
  await humanDelay(wp, 1500);

  // 话题标签
  if (task.tags && task.tags.length > 0) {
    const topicInput = await wp.$('[placeholder*="搜索话题"]');
    if (topicInput && await topicInput.isVisible()) {
      for (const tag of task.tags.slice(0, 3)) {
        try {
          await topicInput.fill(tag.replace(/^#/, ''));
          await humanDelay(wp, 1500);
          const firstTopic = await wp.$('.TopicItem');
          if (firstTopic) await robustClick(wp, firstTopic);
          await humanDelay(wp, 1000);
        } catch (e) {
          log('[zhihu] 话题标签失败，跳过:', e.message);
          break;
        }
      }
    } else {
      log('[zhihu] 未检测到可见话题输入框，跳过话题');
    }
  }

  // 发布：知乎编辑器里有多个含「发布」的元素，必须定位右下角提交按钮，避免点到「发布设置」
  let publishBtn = await wp.$('button[class*="PublishButton"]');
  if (!publishBtn) {
    const candidates = await wp.$$('button');
    const matches = [];
    for (const btn of candidates) {
      const text = await btn.evaluate(e => e.innerText || '').catch(() => '');
      const visible = await btn.isVisible().catch(() => false);
      // 精确文本「发布」且不是设置相关
      if (visible && text.trim() === '发布') matches.push(btn);
    }
    if (matches.length > 0) publishBtn = matches[matches.length - 1]; // 通常是最下面/最右侧的提交按钮
  }
  if (!publishBtn) throw new Error('未找到知乎发布按钮');

  if (task.dryRun) {
    log('[DRY-RUN] 已填好标题/正文，检测到发布按钮，未点击');
    log(`[DRY-RUN] 窗口保持 ${DRY_RUN_HOLD}s 供人工核对，结束后自动关闭…`);
    await wp.waitForTimeout(DRY_RUN_HOLD * 1000);
    log('[DRY-RUN] 核对窗口已关闭');
    return { platform: 'zhihu', status: 'dry_run', title: task.title };
  }

  // 抗遮挡：先关活动弹层，再点发布（可见点击失败则 DOM 直点兜底）
  await dismissModals(wp);
  const beforeUrl = wp.url();
  await robustClick(wp, publishBtn);
  await humanDelay(wp, 6000);

  // 成功判定：文本提示 或 URL 从 /write 跳转到 /p/xxxxx
  const afterUrl = wp.url();
  const bodyText = await wp.evaluate(() => document.body ? document.body.innerText : '').catch(() => '');
  const textSuccess = /发布成功|审核中/.test(bodyText);
  const urlSuccess = /zhuanlan\.zhihu\.com\/p\/\d+/.test(afterUrl) && !afterUrl.includes('/edit');
  const ok = textSuccess || urlSuccess;
  if (!ok) {
    log('[zhihu] 发布按钮点击后未检测到成功标志，URL:', afterUrl, 'body前200:', bodyText.slice(0, 200));
  }
  return {
    platform: 'zhihu',
    status: ok ? 'published' : 'unknown',
    url: afterUrl,
    title: task.title
  };
}

async function runTask(task) {
  const browser = await chromium.launchPersistentContext(EDGE_USER_DATA, {
    executablePath: EDGE_EXE,
    headless: HEADLESS,
    viewport: { width: 1280, height: 800 },
    args: ['--no-sandbox', '--disable-blink-features=AutomationControlled']
  });

  const page = await browser.newPage();
  // 隐藏 webdriver 标志
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  });

  let result;
  try {
    if (task.platform === 'xiaohongshu') {
      result = await publishXiaohongshu(page, task);
    } else if (task.platform === 'zhihu') {
      result = await publishZhihu(page, task);
    } else {
      throw new Error(`未知平台: ${task.platform}`);
    }
  } finally {
    await browser.close();
  }
  return result;
}

app.get('/health', (req, res) => {
  res.json({ ok: true, edge: fs.existsSync(EDGE_EXE), userData: fs.existsSync(EDGE_USER_DATA) });
});

app.post('/publish', async (req, res) => {
  const task = req.body;
  log('收到任务:', JSON.stringify(task));

  if (!task.platform || !task.title || !task.body) {
    return res.status(400).json({ ok: false, error: '缺少 platform/title/body' });
  }

  try {
    const result = await runTask(task);
    log('任务结果:', result);
    res.json({ ok: true, result });
  } catch (err) {
    log('任务失败:', err.message);
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.listen(PORT, () => {
  log(`本地发布服务已启动: http://localhost:${PORT}`);
  log(`Edge 路径: ${EDGE_EXE}`);
  log(`Edge 用户数据: ${EDGE_USER_DATA}`);
  log(`模式: ${HEADLESS ? 'headless' : '有窗口（推荐首次用有窗口看登录态）'}`);
});
