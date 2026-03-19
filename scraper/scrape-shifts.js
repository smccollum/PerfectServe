const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const AUTH_FILE = path.join(__dirname, 'auth.json');

// MAPPING OF TEAM NAMES TO PERFECT SERVE 'SCHEDULE' IDs
const TEAM_IDS = {
    'Team1': 'SCH-8VUUWSB69',
    'Team6': 'SCH-8VUUWSD3B'
};

(async () => {
  if (!fs.existsSync(AUTH_FILE)) {
    console.error('❌ auth.json not found. Please run "node setup-auth.js" first to log in.');
    process.exit(1);
  }

  console.log('🚀 Launching headless scraper abstraction...');
  
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ storageState: AUTH_FILE });
    const page = await context.newPage();

    const TEAM_PREFIX = process.argv[2] || 'Team1';
    let targetMonth = process.argv[3]; // e.g., 'March 2026'

    const scheduleId = TEAM_IDS[TEAM_PREFIX] || TEAM_IDS['Team1'];

    // Formulate the target date formatting expected by the API (e.g., "Thu Feb 26 2026")
    let apiDateStr;
    if (targetMonth) {
        // If the user said "March 2026", JS Date parser handles it gracefully (defaulting to 1st relative to timezone)
        const d = new Date(Date.parse(targetMonth + " 1"));
        apiDateStr = d.toDateString(); 
    } else {
        apiDateStr = new Date().toDateString();
    }

    const apiUrl = `https://practitionerapi.perfectserve.com/api/schedules/GetCalendarData/${scheduleId}/${encodeURIComponent(apiDateStr)}`;
    
    let bearerToken = null;
    // Intercept the outgoing requests from the page load to steal the Authorization token
    page.on('request', request => {
        const authHeader = request.headers()['authorization'];
        if (authHeader && !bearerToken) {
            bearerToken = authHeader;
            console.log('🔑 Intercepted Bearer Token from page load!');
        }
    });

    console.log(`\nNavigating to portal briefly to steal the Session Token...`);
    await page.goto('https://practitioner.perfectserve.com/conversations');
    
    let attempts = 0;
    while (!bearerToken && attempts < 10) {
        await page.waitForTimeout(1000);
        attempts++;
    }

    if (!bearerToken) {
        console.log('❌ Failed to intercept the Authorization header.');
        process.exitCode = 1;
        return;
    }

    console.log(`\nExecuting direct graphical abstraction against:`);
    console.log(` -> ${apiUrl}`);

    try {
        // Use Playwright's context to execute a fetch request leveraging our stolen Bearer token!
        // This bypasses ALL the fragile UI clicks, dropdown menus, and CSS selectors!
        const response = await page.request.get(apiUrl, {
            headers: {
                'Accept': 'application/json, text/plain, */*',
                'Authorization': bearerToken
            }
        });
        
        if (response.ok()) {
            const json = await response.json();
            console.log(`\n🎉 CAUGHT DIRECT CALENDAR API RESPONSE!`);
            
            if (json && json.Events) {
                const extractedShifts = json.Events.map(event => {
                    return {
                        id: event.scheduleEventId,
                        provider: event.title,
                        startDate: event.startDateTime,
                        endDate: event.endDateTime,
                        startTimeCode: event.startTime,
                        endTimeCode: event.endTime,
                        type: event.type
                    };
                });

                console.log(`✅ Success! We extracted ${extractedShifts.length} structured shifts.`);
        
                const safeFilename = `${TEAM_PREFIX.replace(/\s+/g, '')}${targetMonth ? '-' + targetMonth.replace(/\s+/g, '') : ''}-shifts.json`;
                const outputPath = path.join(__dirname, safeFilename);
                fs.writeFileSync(outputPath, JSON.stringify(extractedShifts, null, 2));
                
                console.log(`💾 Saved clean schedule to ${outputPath}`);
            } else {
                console.log('❌ Request succeeded, but payload did not contain calendar Events.');
            }
        } else {
            console.log(`❌ API Request failed with status code: ${response.status()}`);
        }
    } catch (error) {
        console.log(`❌ API Request execution error: ${error.message}`);
    }

  } catch (error) {
      console.log(`❌ Script execution error: ${error.message}`);
  } finally {
      if (browser) {
          console.log('Closing browser...');
          await browser.close();
      }
  }
})();
