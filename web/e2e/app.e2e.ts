import { expect, healthPayload, test } from './fixtures'

test.describe('Dashboard and search', () => {
  test('the dashboard shows the headline, the chosen ticker and the movers', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Measure')
    await expect(page.getByText('123.45').first()).toBeVisible() // AAPL's price from the mock
    await expect(page.getByRole('heading', { name: 'Market movers' })).toBeVisible()
    await expect(page.getByText('Where the model stands')).toBeVisible()
  })

  test('Ctrl+K opens search, filters as you type, and Enter opens the stock page', async ({ page }) => {
    await page.goto('/')
    await page.keyboard.press('Control+k')
    const dialog = page.getByRole('dialog', { name: 'Search tickers' })
    await expect(dialog).toBeVisible()
    await dialog.getByLabel('Ticker').fill('nv')
    await expect(dialog.getByRole('button', { name: /NVDA/ })).toBeVisible()
    await expect(dialog.getByRole('button', { name: /MSFT/ })).toHaveCount(0)
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/#stock\/NVDA$/)
    await expect(dialog).toBeHidden()
  })

  test('Escape closes search and a bad symbol is explained, not opened', async ({ page }) => {
    await page.goto('/')
    await page.keyboard.press('Control+k')
    const dialog = page.getByRole('dialog', { name: 'Search tickers' })
    await dialog.getByLabel('Ticker').fill('!!')
    await page.keyboard.press('Enter')
    await expect(dialog.getByText('Enter a ticker such as AAPL.')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
  })
})

test.describe('Markets', () => {
  test('the heatmap has one tile per stock and a tile opens that stock', async ({ page }) => {
    await page.goto('/#markets')
    const map = page.getByRole('group', { name: 'Market heatmap' })
    await expect(map.getByRole('button')).toHaveCount(25)
    await map.getByRole('button', { name: /^AAPL/ }).click()
    await expect(page).toHaveURL(/#stock\/AAPL$/)
  })

  test('index ETFs and movers are shown', async ({ page }) => {
    await page.goto('/#markets')
    for (const etf of ['SPY', 'QQQ', 'DIA', 'IWM']) await expect(page.getByRole('button', { name: new RegExp(`^${etf}`) }).first()).toBeVisible()
  })
})

test.describe('Stock page', () => {
  test('shows the stock, its stats and the model score for a universe stock', async ({ page }) => {
    await page.goto('/#stock/AAPL')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('AAPL Inc.')
    await expect(page.getByText(/Model score 0\.58/)).toBeVisible()
    await expect(page.getByText('52W HIGH')).toBeVisible()
    await expect(page.getByRole('img', { name: /Candlestick chart/ })).toBeVisible()
  })

  test('changing the interval and the overlay asks for the right data', async ({ page, api }) => {
    await page.goto('/#stock/AAPL')
    const hour = page.getByRole('button', { name: '1h', exact: true })
    await expect(hour).toHaveAttribute('aria-pressed', 'false')
    await hour.click()
    await expect(hour).toHaveAttribute('aria-pressed', 'true')
    await page.getByRole('button', { name: 'SPY OVERLAY' }).click()
    await expect(page.getByText(/rescaled to start at the same price/)).toBeVisible()
    await page.getByRole('button', { name: 'LINE' }).click()
    await expect(page.getByRole('img', { name: /Line chart/ })).toBeVisible()
    const history = api.calls.filter((c) => c.path.startsWith('/api/market/history/')).map((c) => c.query)
    expect(history.some((q) => q.includes('interval=1h') && q.includes('spy=true'))).toBe(true)
  })

  test('hovering the chart shows exact values', async ({ page }) => {
    await page.goto('/#stock/AAPL')
    const chart = page.getByRole('img', { name: /Candlestick chart/ })
    await expect(page.getByText('Hover the chart for exact values')).toBeVisible()
    await chart.hover({ position: { x: 400, y: 150 } }) // scrolls the chart into view first
    await expect(page.getByText(/O \d+\.\d+/).first()).toBeVisible()
    await expect(page.getByText('Hover the chart for exact values')).toHaveCount(0)
  })

  test('an invalid symbol in the address is explained', async ({ page }) => {
    await page.goto('/#stock/NOT%20A%20SYMBOL')
    await expect(page.getByText(/is not a valid ticker/)).toBeVisible()
  })
})

test.describe('Watchlist and practice portfolio', () => {
  test('a practice position can be added, is labelled as practice, and survives a reload', async ({ page }) => {
    await page.goto('/#watchlist')
    await expect(page.getByText('Practice, not traded by the system')).toBeVisible()
    await page.getByLabel('Ticker', { exact: true }).fill('aapl')
    await page.getByLabel('Shares').fill('10')
    await page.getByLabel('Average cost').fill('90')
    await page.getByRole('button', { name: 'ADD POSITION' }).click()
    await expect(page.getByRole('button', { name: /^AAPL/ }).first()).toBeVisible()
    await page.reload()
    await expect(page.getByRole('table').first().getByRole('button', { name: /^AAPL/ })).toBeVisible()
  })

  test('bad input is rejected with a reason and adds nothing', async ({ page }) => {
    await page.goto('/#watchlist')
    await page.getByLabel('Ticker', { exact: true }).fill('???')
    await page.getByRole('button', { name: 'ADD POSITION' }).click()
    await expect(page.getByText('Enter a ticker such as AAPL.')).toBeVisible()
    await page.getByLabel('Ticker', { exact: true }).fill('AAPL')
    await page.getByRole('button', { name: 'ADD POSITION' }).click()
    await expect(page.getByText('Enter shares and an average cost above zero.')).toBeVisible()
    await expect(page.getByText('No practice positions')).toBeVisible()
  })

  test('nothing here can reach the trading system', async ({ page, api }) => {
    await page.goto('/#watchlist')
    await page.getByLabel('Ticker', { exact: true }).fill('MSFT')
    await page.getByLabel('Shares').fill('1')
    await page.getByLabel('Average cost').fill('1')
    await page.getByRole('button', { name: 'ADD POSITION' }).click()
    expect(api.calls.filter((c) => c.method !== 'GET')).toEqual([])
  })
})

test.describe('Approvals and kill switch', () => {
  test('buys wait for a decision, sells never do', async ({ page }) => {
    await page.goto('/#approvals')
    const buy = page.getByRole('row', { name: /AAPL/ })
    const sell = page.getByRole('row', { name: /META/ })
    await expect(buy.getByRole('button', { name: 'Approve' })).toBeVisible()
    await expect(sell.getByRole('button')).toHaveCount(0)
    await expect(sell.getByText('Runs automatically')).toBeVisible()
  })

  test('approving sends the marker header and updates the status', async ({ page, api }) => {
    await page.goto('/#approvals')
    await page.getByRole('row', { name: /AAPL/ }).getByRole('button', { name: 'Approve' }).click()
    await expect(page.getByRole('row', { name: /AAPL/ }).getByText('Approved')).toBeVisible()
    const post = api.calls.find((c) => c.method === 'POST' && c.path.endsWith('/approve'))!
    expect(post.path).toContain(encodeURIComponent('2026-11-25:BUY:AAPL'))
    expect(post.headers['x-requested-with']).toBe('paper-trader')
  })

  test('rejecting works and the decision can be changed', async ({ page }) => {
    await page.goto('/#approvals')
    const row = page.getByRole('row', { name: /AAPL/ })
    await row.getByRole('button', { name: 'Reject' }).click()
    await expect(row.getByText('Rejected')).toBeVisible()
    await row.getByRole('button', { name: 'Approve' }).click()
    await expect(row.getByText('Approved')).toBeVisible()
  })

  test('the kill switch needs a reason and a confirmation before it sends anything', async ({ page, api }) => {
    await page.goto('/#approvals')
    const turnOn = page.getByRole('button', { name: 'Turn the kill switch on' })
    await turnOn.click()
    await expect(page.getByText('Say why, so the log can explain the halt later.')).toBeVisible()
    await page.getByLabel('Reason for turning the kill switch on').fill('testing')
    await turnOn.click()
    await expect(page.getByText('Tick the box to confirm you understand.')).toBeVisible()
    expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/kill-switch')).toBe(false)
    await page.getByRole('checkbox').check()
    await turnOn.click()
    await expect(page.getByText(/ON: the nightly run does nothing/)).toBeVisible()
    const post = api.calls.find((c) => c.method === 'POST' && c.path === '/api/kill-switch')!
    expect(JSON.parse(post.body!)).toEqual({ enabled: true, reason: 'testing' })
    expect(post.headers['x-requested-with']).toBe('paper-trader')
  })

  test('the page says plainly what the kill switch does to stop-losses', async ({ page }) => {
    await page.goto('/#approvals')
    await expect(page.getByText(/stop-losses are not checked/i).first()).toBeVisible()
  })
})

test.describe('Health', () => {
  test('crashed and missed runs raise a visible warning', async ({ page, api }) => {
    api.health = healthPayload(['SUCCESS', 'FAILED', 'FAILED', 'MISSED', 'DEGRADED'])
    await page.goto('/#health')
    await expect(page.getByText('Needs attention')).toBeVisible()
    await expect(page.getByText(/2 nightly run\(s\) crashed/)).toBeVisible()
    await expect(page.getByRole('list', { name: /Nightly runs/ }).getByRole('listitem')).toHaveCount(5)
  })

  test('a healthy history shows no warning banner', async ({ page }) => {
    await page.goto('/#health')
    await expect(page.getByText('Needs attention')).toHaveCount(0)
    await expect(page.getByText("Dead man's switch is not set up")).toBeVisible()
  })
})

test.describe('Theme and safety', () => {
  test('the dark theme can be switched on, and it is remembered', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Switch to dark theme' }).click()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await page.reload()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await page.getByRole('button', { name: 'Switch to light theme' }).click()
    await expect(page.locator('html')).not.toHaveClass(/dark/)
  })

  test('visiting every page makes no change-making request and no external request', async ({ page, api }) => {
    const external: string[] = []
    page.on('request', (r) => {
      const u = new URL(r.url())
      if (!['127.0.0.1', 'localhost'].includes(u.hostname)) external.push(r.url())
    })
    for (const route of ['dashboard', 'markets', 'watchlist', 'stock/AAPL', 'overview', 'approvals', 'health']) {
      await page.goto(`/#${route}`)
      await page.waitForLoadState('networkidle')
    }
    expect(api.calls.filter((c) => c.method !== 'GET')).toEqual([])
    expect(external).toEqual([])
  })
})
