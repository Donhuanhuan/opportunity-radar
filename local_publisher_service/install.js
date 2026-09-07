// 一键安装依赖
const { execSync } = require('child_process');
const path = require('path');

console.log('🚀 安装本机发布服务依赖...');
console.log('工作目录:', __dirname);

try {
  execSync('npm install', {
    cwd: __dirname,
    stdio: 'inherit',
    shell: true,
    env: {
      ...process.env,
      npm_config_registry: 'https://registry.npmmirror.com',
      PLAYWRIGHT_DOWNLOAD_HOST: 'https://npmmirror.com/mirrors/playwright'
    }
  });
  console.log('✅ 依赖安装完成');
} catch (err) {
  console.error('❌ 安装失败:', err.message);
  process.exit(1);
}
