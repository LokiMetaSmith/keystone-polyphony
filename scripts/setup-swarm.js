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

  // --- Step 2: Configure Jules Integrations ---
  console.log(`>>> Navigating to Jules Integrations...`);
  try {
    await page.goto('https://jules.google.com/settings/integrations');
  } catch (e) {
    console.log("Could not navigate automatically. Please click on 'Integrations' in the sidebar.");
  }

  console.log("ACTION: Connect Render (if used) to allow Jules to fix preview deployment errors.");
  console.log("      Paste your Render API key if applicable.");
  await page.pause();

  // --- Step 3: Configure Jules API Key ---
  console.log(`>>> Navigating to Jules API Key settings...`);
  try {
    await page.goto('https://jules.google.com/settings/api-key');
  } catch (e) {
    console.log("Could not navigate automatically. Please click on 'API Key' in the sidebar.");
  }

  console.log("ACTION: Configure your Jules API key if needed.");
  await page.pause();

  // --- Step 4: GitHub Repository Permissions ---
  console.log(`>>> Navigating to GitHub Settings for ${repo}...`);
  await page.goto(`https://github.com/${repo}/settings/actions`);
  console.log("ACTION: Scroll to 'Workflow permissions' and select 'Read and write permissions'.");
  console.log("      Then click 'Save'.");
  await page.pause();

  await browser.close();
  console.log(">>> UI Configuration Complete.");
})();
