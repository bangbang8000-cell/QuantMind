/**
 * Sanitize HTML content from RSS feeds to prevent XSS attacks.
 *
 * RSS articles may contain malicious scripts, iframes, or other dangerous
 * elements. This utility strips them while preserving safe formatting.
 */
import DOMPurify from 'dompurify';

/** Allow common safe HTML tags for article rendering */
const ALLOWED_TAGS = [
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'p', 'br', 'hr', 'blockquote', 'pre', 'code',
  'ul', 'ol', 'li', 'dl', 'dt', 'dd',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
  'a', 'img', 'figure', 'figcaption',
  'strong', 'em', 'b', 'i', 'u', 's', 'mark', 'small', 'sub', 'sup',
  'span', 'div', 'section', 'article', 'aside', 'details', 'summary',
  'audio', 'video', 'source',
];

const ALLOWED_ATTR = [
  'href', 'src', 'alt', 'title', 'class', 'id', 'target', 'rel',
  'width', 'height', 'loading', 'controls', 'autoplay', 'loop', 'muted',
  'colspan', 'rowspan', 'scope',
  'datetime', 'cite',
];

/**
 * Sanitize untrusted HTML (e.g. RSS article body).
 * Strips scripts, iframes, forms, and other dangerous elements.
 */
export function sanitizeHtml(html: string): string {
  if (!html) return '';
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    // Force all links to open in new tab with noopener
    ADD_ATTR: ['target'],
    FORBID_TAGS: ['style', 'form', 'input', 'button', 'textarea', 'select', 'option'],
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover'],
  });
}

/**
 * Configure DOMPurify to force target="_blank" on all anchor tags
 * so external links never navigate the app shell.
 */
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});
