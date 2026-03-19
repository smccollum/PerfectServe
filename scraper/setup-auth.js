const { chromium } = require('playwright');
const path = require('path');

const AUTH_FILE = path.join(__dirname, 'auth.json');

// Credentials are read from environment variables — never hardcode them.
// Set PERFECTSERVE_USERNAME and PERFECTSERVE_PASSWORD before running.
const USERNAME = process.env.PERFECTSERVE_USERNAME;
const PASSWORD = process.env.PERFECTSERVE_PASSWORD;

(async () => {
  if (!USERNAME || !PASSWORD) {
    console.error('❌ Missing credentials. Set PERFECTSERVE_USERNAME and PERFECTSERVE_PASSWORD environment variables.');
    console.error('   Example (PowerShell): $env:PERFECTSERVE_USERNAME="your.username"');
    console.error('   Example (Bash):       export PERFECTSERVE_USERNAME="your.username"');
    process.exit(1);
  }

  console.log('🚀 Launching automated headless authenticator...');

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    console.log('Navigating to PerfectServe login...');
    await page.goto('https://practitioner.perfectserve.com/conversations');

    console.log('Filling in credentials...');
    await page.waitForSelector('#username');
    await page.fill('#username', USERNAME);
    await page.fill('#password', PASSWORD);

    console.log('Submitting login form...');
    await page.click('#login-submit');

    console.log('⏳ Waiting for inbox to load to confirm session token...');
    await page.waitForTimeout(10000);

    console.log('\n🔒 Login complete! Saving authentication state...');
    await context.storageState({ path: AUTH_FILE });

    console.log(`✅ Authentication state successfully saved to ${AUTH_FILE}!`);
    console.log('You can now run the scraper scripts.');
  } catch (error) {
    console.log(`❌ Authentication execution error: ${error.message}`);
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }
})();
