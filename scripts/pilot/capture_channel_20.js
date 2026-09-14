async (page) => {
  const MAX_POSTS = 20;
  const WAIT_AFTER_SCROLL_MS = 900;

  const wait = (milliseconds) => page.waitForTimeout(milliseconds);

  const extractMessages = async (selector) =>
    page.evaluate((messageSelector) => {
      const cleanText = (value) =>
        (value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').trim();
      const idFrom = (element) => {
        const body = element.querySelector('[data-tid="message-body"]');
        const match = body?.id?.match(/content-(\d{10,})/);
        return match?.[1] || null;
      };
      const authorFrom = (element) => {
        const avatar = element.querySelector(
          '[data-tid="post-message-header-avatar"][aria-label], [data-tid="reply-message-header-avatar"][aria-label]'
        );
        return avatar?.getAttribute('aria-label')?.replace(/^Profile picture of /, '').replace(/\.$/, '') || null;
      };
      const attachmentsFrom = (element) => {
        const found = [];
        const seen = new Set();
        for (const candidate of element.querySelectorAll('[aria-label*="http"]')) {
          const label = candidate.getAttribute('aria-label') || '';
          const match = label.match(/https?:\/\/\S+/);
          if (!match) continue;
          const url = match[0];
          const name = cleanText(label.slice(0, match.index));
          const key = `${name}\n${url}`;
          if (seen.has(key)) continue;
          seen.add(key);
          found.push({ name, url });
        }
        return found;
      };

      return [...document.querySelectorAll(messageSelector)].map((element, index) => {
        const id = idFrom(element);
        const body = element.querySelector('[data-tid="message-body"]');
        const explicitTime = element.querySelector('time[data-tid="timestamp"]')?.getAttribute('aria-label') || null;
        const parsedTime = id && /^\d{13}$/.test(id) ? new Date(Number(id)) : null;
        const deleted = Boolean(element.querySelector('[data-tid="message-tombstone"]'));
        return {
          id,
          order: index,
          author: authorFrom(element),
          timestamp: parsedTime && !Number.isNaN(parsedTime.getTime()) ? parsedTime.toISOString() : explicitTime,
          timestampLabel: explicitTime,
          subject: cleanText(element.querySelector('[data-tid="subject-line"]')?.textContent),
          text: deleted ? '[This message has been deleted.]' : cleanText(body?.innerText),
          html: deleted ? '' : (body?.innerHTML || ''),
          deleted,
          attachments: attachmentsFrom(element),
          images: [...element.querySelectorAll('[data-tid="message-body"] img')].map((image) => ({
            alt: image.getAttribute('alt') || '',
            src: image.getAttribute('src') || '',
            width: image.naturalWidth || null,
            height: image.naturalHeight || null,
          })),
        };
      });
    }, selector);

  const loadWholeOpenThread = async () => {
    const viewport = page.locator('[data-tid="channel-replies-viewport"]');
    await viewport.waitFor({ state: 'visible', timeout: 15_000 });
    let previousCount = -1;
    let stableRounds = 0;
    for (let round = 0; round < 16 && stableRounds < 3; round += 1) {
      await viewport.evaluate((element) => {
        element.scrollTop = 0;
        element.dispatchEvent(new Event('scroll', { bubbles: true }));
      });
      await wait(650);
      const count = await page.locator('[data-tid="channel-replies-pane-message"]').count();
      stableRounds = count === previousCount ? stableRounds + 1 : 0;
      previousCount = count;
    }
    return { stableRounds, messages: await extractMessages('[data-tid="channel-replies-pane-message"]') };
  };

  const channelTitle = (await page.locator('[data-tid="channelTitle-text"]').textContent())?.trim() || null;
  const pageTitle = await page.title();
  const sourceUrl = page.url();
  const channelViewport = page.locator('[data-tid="channel-pane-viewport"]');
  await channelViewport.waitFor({ state: 'visible', timeout: 15_000 });
  await channelViewport.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
    element.dispatchEvent(new Event('scroll', { bubbles: true }));
  });
  await wait(1_200);

  const captured = new Map();
  const errors = [];
  let unchangedRounds = 0;

  for (let scanRound = 0; scanRound < 60 && captured.size < MAX_POSTS && unchangedRounds < 8; scanRound += 1) {
    const visibleRoots = await page.evaluate(() =>
      [...document.querySelectorAll('[data-tid="channel-pane-message"]')].map((element) => {
        const idMatch = element.id.match(/reply-chain-summary-(\d{10,})/);
        const expectedMatch = element
          .querySelector('[data-tid="response-surface"]')
          ?.getAttribute('aria-label')
          ?.match(/(\d+)\s+repl/i);
        return {
          id: idMatch?.[1] || null,
          expectedReplies: expectedMatch ? Number(expectedMatch[1]) : 0,
          hasReplyButton: Boolean(element.querySelector('[data-tid="response-summary-button"]')),
        };
      })
    );

    let addedThisRound = 0;
    for (const summary of visibleRoots) {
      if (!summary.id || captured.has(summary.id) || captured.size >= MAX_POSTS) continue;
      const root = page.locator(`#reply-chain-summary-${summary.id}`);
      if ((await root.count()) === 0) continue;

      try {
        if (summary.hasReplyButton && summary.expectedReplies > 0) {
          await root.locator('[data-tid="response-summary-button"]').click({ timeout: 10_000 });
          const loaded = await loadWholeOpenThread();
          const messages = loaded.messages;
          captured.set(summary.id, {
            id: summary.id,
            expectedReplies: summary.expectedReplies,
            capturedReplies: Math.max(0, messages.length - 1),
            countMatches: messages.length - 1 === summary.expectedReplies,
            stableRounds: loaded.stableRounds,
            messages,
          });
          await page.locator('[data-tid="close-l2-view-button"]').click({ timeout: 10_000 });
          await channelViewport.waitFor({ state: 'visible', timeout: 15_000 });
          await wait(550);
        } else {
          const messages = await root.evaluate((element) => {
            const body = element.querySelector('[data-tid="message-body"]');
            const idMatch = body?.id?.match(/content-(\d{10,})/);
            const id = idMatch?.[1] || null;
            const avatar = element.querySelector('[data-tid="post-message-header-avatar"][aria-label]');
            const author = avatar?.getAttribute('aria-label')?.replace(/^Profile picture of /, '').replace(/\.$/, '') || null;
            const explicitTime = element.querySelector('time[data-tid="timestamp"]')?.getAttribute('aria-label') || null;
            const parsedTime = id && /^\d{13}$/.test(id) ? new Date(Number(id)) : null;
            const clean = (value) => (value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').trim();
            const attachments = [];
            const attachmentKeys = new Set();
            for (const candidate of element.querySelectorAll('[aria-label*="http"]')) {
              const label = candidate.getAttribute('aria-label') || '';
              const urlMatch = label.match(/https?:\/\/\S+/);
              if (!urlMatch) continue;
              const url = urlMatch[0];
              const name = clean(label.slice(0, urlMatch.index));
              const key = `${name}\n${url}`;
              if (attachmentKeys.has(key)) continue;
              attachmentKeys.add(key);
              attachments.push({ name, url });
            }
            return [{
              id,
              order: 0,
              author,
              timestamp: parsedTime && !Number.isNaN(parsedTime.getTime()) ? parsedTime.toISOString() : explicitTime,
              timestampLabel: explicitTime,
              subject: clean(element.querySelector('[data-tid="subject-line"]')?.textContent),
              text: clean(body?.innerText),
              html: body?.innerHTML || '',
              deleted: false,
              attachments,
              images: [...element.querySelectorAll('[data-tid="message-body"] img')].map((image) => ({
                alt: image.getAttribute('alt') || '',
                src: image.getAttribute('src') || '',
                width: image.naturalWidth || null,
                height: image.naturalHeight || null,
              })),
            }];
          });
          captured.set(summary.id, {
            id: summary.id,
            expectedReplies: 0,
            capturedReplies: 0,
            countMatches: true,
            stableRounds: 0,
            messages,
          });
        }
        addedThisRound += 1;
      } catch (error) {
        errors.push({ postId: summary.id, message: String(error).slice(0, 500) });
        if (await page.locator('[data-tid="close-l2-view-button"]').count()) {
          await page.locator('[data-tid="close-l2-view-button"]').click().catch(() => {});
          await wait(500);
        }
      }
    }

    unchangedRounds = addedThisRound === 0 ? unchangedRounds + 1 : 0;
    await channelViewport.evaluate((element) => {
      element.scrollTop = Math.max(0, element.scrollTop - Math.max(500, element.clientHeight * 0.8));
      element.dispatchEvent(new Event('scroll', { bubbles: true }));
    });
    await wait(WAIT_AFTER_SCROLL_MS);
  }

  const posts = [...captured.values()];
  const allMessages = posts.flatMap((post) => post.messages);
  return {
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    source: { url: sourceUrl, pageTitle, channel: channelTitle },
    limit: MAX_POSTS,
    evidence: {
      capturedPosts: posts.length,
      expectedReplies: posts.reduce((sum, post) => sum + post.expectedReplies, 0),
      capturedReplies: posts.reduce((sum, post) => sum + post.capturedReplies, 0),
      postsWithMatchingReplyCount: posts.filter((post) => post.countMatches).length,
      postsWithUncertainReplyCount: posts.filter((post) => !post.countMatches).length,
      attachmentReferences: allMessages.reduce((sum, message) => sum + message.attachments.length, 0),
      embeddedImages: allMessages.reduce((sum, message) => sum + message.images.length, 0),
      errors: errors.length,
    },
    errors,
    posts,
  };
}
