// 一键安装/校验本机发布服务依赖（幂等：已装齐则直接通过，不重复安装）
const { execSync } = require('child_process');

console.log('🚀 Local Publisher dependency check / install...');
console.log('cwd:', __dirname);

const NPM_ENV = {
  ...process.env,
  npm_config_registry: 'https://registry.npmmirror.com',
  PLAYWRIGHT_DOWNLOAD_HOST: 'https://npmmirror.com/mirrors/playwright',
  // 跳过 audit 与 fund（npmmirror 不支持 audit 接口，会导致误报失败）
  npm_config_audit: 'false',
  npm_config_fund: 'false'
};

function depsReady() {
  try {
    // 仅校验顶层依赖是否存在；不联网、不写文件，可安全重复执行
    execSync('npm ls express playwright --depth=0', {
      cwd: __dirname,
      stdio: 'pipe',
      shell: true,
      env: NPM_ENV
    });
    return true;
  } catch (e) {
    return false;
  }
}

try {
  if (depsReady()) {
    console.log('✅ Dependencies already complete (express + playwright). Nothing to do.');
  } else {
    console.log('📦 Dependencies incomplete, installing (1-3 min on normal network)...');
    execSync('npm install', {
      cwd: __dirname,
      stdio: 'inherit',
      shell: true,
      env: NPM_ENV
    });
    if (!depsReady()) {
      console.error('❌ Still missing packages after install.');
      process.exit(1);
    }
    console.log('✅ Dependency install complete.');
  }
} catch (err) {
  console.error('❌ Install failed:', err.message);
  process.exit(1);
}
