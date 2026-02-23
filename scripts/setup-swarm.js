const { chromium } = require('playwright');
const { execSync } = require('child_process');
const path = require('path');

(async () => {
  let repo = "LokiMetaSmith/keystone-polyphony"; // Default fallback

  // Try to detect repo from git config
  try {
    const remoteUrl = execSync('git config --get remote.origin.url', { encoding: 'utf8' }).trim();
    // Handles https://github.com/user/repo.git and git@github.com:user/repo.git
    const match = remoteUrl.match(/github\.com[:\/]([^\/]+\/[^\.]+)(\.git)?$/);
    if (match && match[1]) {
      repo = match[1];
      console.log(`>>> Detected repository: ${repo}`);
    }
  } catch (error) {
    console.log(">>> Could not detect repository from git config. Using default.");
  }

  // Allow override via argument
  if (process.argv[2]) {
    repo = process.argv[2];
    console.log(`>>> Using repository from argument: ${repo}`);
  }

  const browser = await chromium.launch({ headless: false }); // Headed for manual interaction
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log(">>> Initiating Polyphony Onboarding...");

  // --- Step 1: Configure Jules ---
  // Calculate absolute path for user convenience
  const serverPath = path.resolve(__dirname, '../src/liminal_bridge/server.py');

  await page.goto('https://jules.google.com/settings/mcp');
  console.log(`ACTION: Add the MCP Server.`);
  console.log(`      Command: python`);
  console.log(`      Args: [${serverPath}]`);
  console.log("      (Copy the path above and paste it into the Jules settings)");

  await page.pause(); // Manual step to paste local paths

  // --- Step 2: GitHub Repository Permissions ---
  console.log(`>>> Navigating to GitHub Settings for ${repo}...`);
  await page.goto(`https://github.com/${repo}/settings/actions`);
  console.log("ACTION: Scroll to 'Workflow permissions' and select 'Read and write permissions'.");
  console.log("      Then click 'Save'.");
  await page.pause();

  await browser.close();
  console.log(">>> UI Configuration Complete.");
})();
