async (page) => {
  const loadResult = await page.evaluate(async () => {
    const viewport = document.querySelector('[data-tid="channel-replies-viewport"]');
    if (!viewport) {
      return { ok: false, reason: 'thread-not-open' };
    }

    let stableRounds = 0;
    let previousCount = -1;
    for (let round = 0; round < 12 && stableRounds < 3; round += 1) {
      viewport.scrollTop = 0;
      viewport.dispatchEvent(new Event('scroll', { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 700));
      const count = document.querySelectorAll('[data-tid="channel-replies-pane-message"]').length;
      stableRounds = count === previousCount ? stableRounds + 1 : 0;
      previousCount = count;
    }

    return {
      ok: true,
      renderedMessages: document.querySelectorAll('[data-tid="channel-replies-pane-message"]').length,
      stableRounds,
    };
  });

  if (!loadResult.ok) {
    return loadResult;
  }

  return await page.evaluate((loadInfo) => {
    const cleanText = (value) => (value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').trim();
    const idFrom = (element) => {
      const body = element.querySelector('[data-tid="message-body"]');
      const match = body?.id?.match(/content-(\d{10,})/);
      return match?.[1] || null;
    };
    const isoFrom = (element, messageId) => {
      const explicit = element.querySelector('time[data-tid="timestamp"]')?.getAttribute('aria-label');
      if (messageId && /^\d{13}$/.test(messageId)) {
        const parsed = new Date(Number(messageId));
        if (!Number.isNaN(parsed.getTime())) return parsed.toISOString();
      }
      return explicit || null;
    };
    const authorFrom = (element) => {
      const avatar = element.querySelector(
        '[data-tid="post-message-header-avatar"][aria-label], [data-tid="reply-message-header-avatar"][aria-label]'
      );
      return avatar?.getAttribute('aria-label')?.replace(/^Profile picture of /, '').replace(/\.$/, '') || null;
    };
    const attachmentFrom = (element) => {
      const found = [];
      const seen = new Set();
      for (const candidate of element.querySelectorAll('[aria-label*="http"]')) {
        const label = candidate.getAttribute('aria-label') || '';
        const urlMatch = label.match(/https?:\/\/\S+/);
        if (!urlMatch) continue;
        const url = urlMatch[0];
        const name = cleanText(label.slice(0, urlMatch.index));
        const key = `${name}\n${url}`;
        if (seen.has(key)) continue;
        seen.add(key);
        found.push({ name, url });
      }
      return found;
    };
    const imagesFrom = (element) =>
      [...element.querySelectorAll('[data-tid="message-body"] img')].map((image) => ({
        alt: image.getAttribute('alt') || '',
        src: image.getAttribute('src') || '',
        width: image.naturalWidth || null,
        height: image.naturalHeight || null,
      }));

    const messageElements = [...document.querySelectorAll('[data-tid="channel-replies-pane-message"]')];
    const messages = messageElements.map((element, index) => {
      const messageId = idFrom(element);
      const body = element.querySelector('[data-tid="message-body"]');
      const deleted = Boolean(element.querySelector('[data-tid="message-tombstone"]'));
      return {
        id: messageId,
        kind: index === 0 ? 'root' : 'reply',
        author: authorFrom(element),
        timestamp: isoFrom(element, messageId),
        timestampLabel: element.querySelector('time[data-tid="timestamp"]')?.getAttribute('aria-label') || null,
        subject: cleanText(element.querySelector('[data-tid="subject-line"]')?.textContent),
        text: deleted ? '[This message has been deleted.]' : cleanText(body?.innerText),
        html: deleted ? '' : (body?.innerHTML || ''),
        deleted,
        attachments: attachmentFrom(element),
        images: imagesFrom(element),
      };
    });

    const responseSurface = document.querySelector('[data-tid="response-surface"]');
    const replyMatch = responseSurface?.getAttribute('aria-label')?.match(/(\d+)\s+repl/i);
    const expectedReplies = replyMatch ? Number(replyMatch[1]) : null;
    const uniqueIds = new Set(messages.map((message) => message.id).filter(Boolean));

    return {
      schemaVersion: 1,
      capturedAt: new Date().toISOString(),
      source: {
        url: location.href,
        pageTitle: document.title,
        channel: cleanText(document.querySelector('[data-tid="channelTitle-text"]')?.textContent),
        thread: cleanText(document.querySelector('[data-tid="postTitle-text"]')?.textContent),
      },
      evidence: {
        expectedReplies,
        renderedMessages: loadInfo.renderedMessages,
        capturedMessages: messages.length,
        capturedReplies: Math.max(0, messages.length - 1),
        uniqueMessageIds: uniqueIds.size,
        stableRounds: loadInfo.stableRounds,
        countMatches: expectedReplies === null ? null : expectedReplies === messages.length - 1,
      },
      messages,
    };
  }, loadResult);
}
