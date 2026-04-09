/**
 * TruthScan — main.js  v3.0
 * 9.7/10 build — all improvements implemented
 */
'use strict';

/* ── Constants ── */
const EXAMPLES = [
  'NASA successfully launched the Artemis II mission carrying four astronauts on a lunar flyby trajectory. The crew includes Commander Reid Wiseman and mission specialists from Canada and Japan.',
  'SHOCKING: Scientists CONFIRM 5G towers are secretly controlling human brain waves — government is HIDING the truth about what these signals REALLY do to your body and your children!!',
  'The UN Intergovernmental Panel on Climate Change released its latest assessment report indicating that global surface temperatures have risen by approximately 1.1°C above pre-industrial levels.',
];

const MODEL_ABBR = {
  'BERT':                'BE',
  'Logistic Regression': 'LR',
  'XGBoost':             'XG',
  'LightGBM':            'LG',
  'Ensemble (top-3)':    'EN',
};

/* ── State ── */
let sourceType   = 'news';
let typingTimer  = null;
let hasResult    = false;

/* ── DOM refs ── */
const $ = id => document.getElementById(id);
const inputText    = $('inputText');
const scanBtn      = $('scanBtn');
const scanLabel    = $('scanLabel');
const charCount    = $('ip-charcount') || document.querySelector('.ip-charcount');
const charCountEl  = document.querySelector('.ip-charcount');
const resultCard   = $('resultCard');
const skeletonCard = $('skeletonCard');
const errorPanel   = $('errorPanel');
const miniVerdict  = $('miniVerdict');
const mainHeader   = $('mainHeader');

/* ── Canvas particle background ── */
(function initCanvas() {
  const canvas = $('bgCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let W, H, particles = [];

  const COLORS = [
    'rgba(99,102,241,',
    'rgba(16,185,129,',
    'rgba(139,92,246,',
  ];

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function makeParticle() {
    return {
      x: Math.random() * W,
      y: Math.random() * H,
      r: Math.random() * 1.8 + 0.4,
      vx: (Math.random() - 0.5) * 0.18,
      vy: (Math.random() - 0.5) * 0.18,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      alpha: Math.random() * 0.5 + 0.15,
    };
  }

  function init() {
    resize();
    particles = Array.from({ length: 90 }, makeParticle);
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    particles.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = p.color + p.alpha + ')';
      ctx.fill();
      p.x += p.vx; p.y += p.vy;
      if (p.x < -5)  p.x = W + 5;
      if (p.x > W+5) p.x = -5;
      if (p.y < -5)  p.y = H + 5;
      if (p.y > H+5) p.y = -5;
    });
    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  init(); draw();
})();

/* ── Counter animation for hero stats ── */
(function animateCounters() {
  const els = document.querySelectorAll('.sbar-n[data-count]');
  els.forEach(el => {
    const target   = parseFloat(el.dataset.count);
    const suffix   = el.dataset.suffix || '';
    const decimals = parseInt(el.dataset.decimals || '1', 10);
    const duration = 1800;
    const start    = performance.now();

    function step(now) {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      const val  = target * ease;
      el.textContent = val.toFixed(decimals) + suffix;
      if (t < 1) requestAnimationFrame(step);
    }
    // Delay slightly so page loads first
    setTimeout(() => requestAnimationFrame(step), 400);
  });
})();

/* ── Animated textarea placeholder ── */
(function rotatePlaceholder() {
  const snippets = [
    'Paste a news headline or article here…',
    '"Scientists discover breakthrough in cancer research…"',
    '"BREAKING: Government confirms alien contact — sources say…"',
    '"Central bank raises interest rates by 0.25 percentage points…"',
  ];
  let idx = 0;
  setInterval(() => {
    if (document.activeElement !== inputText && !inputText.value) {
      idx = (idx + 1) % snippets.length;
      inputText.placeholder = snippets[idx];
    }
  }, 3500);
})();

/* ── Intersection observer for how-it-works cards ── */
const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      const delay = e.target.style.getPropertyValue('--d') || '0s';
      setTimeout(() => e.target.classList.add('visible'), parseFloat(delay) * 1000);
      revealObserver.unobserve(e.target);
    }
  });
}, { threshold: 0.15 });

document.querySelectorAll('.hs-reveal').forEach(el => revealObserver.observe(el));

/* ── Tab toggle ── */
function setTab(type, btn) {
  sourceType = type;
  document.querySelectorAll('.iptab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  inputText.placeholder = type === 'news'
    ? 'Paste a news headline or article here…'
    : 'Paste a tweet, Facebook post, or WhatsApp forward…';
  inputText.focus();
}

/* ── Load example ── */
function loadEx(idx) {
  inputText.value = EXAMPLES[idx];
  onInput();
  inputText.focus();
  inputText.scrollTop = 0;
}

/* ── Input handler ── */
function onInput() {
  const text = inputText.value;
  const len  = text.length;

  // Char counter
  charCountEl.textContent = `${len.toLocaleString()} / 5,000`;

  // Scan button
  scanBtn.disabled = len < 10;

  // Typing border pulse
  const panel = document.querySelector('.input-panel');
  panel.classList.toggle('typing', len > 0);

  // Inline stats badge
  const badge = $('taBadge');
  if (len > 0) {
    const words = text.trim().split(/\s+/).filter(Boolean).length;
    const sents = (text.match(/[.!?]+/g) || []).length;
    $('wordBadge').textContent = `${words} word${words !== 1 ? 's' : ''}`;
    $('sentBadge').textContent = `${sents} sentence${sents !== 1 ? 's' : ''}`;
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }

  // Debounced clear result on new input
  clearTimeout(typingTimer);
  if (hasResult && len > 0) {
    typingTimer = setTimeout(() => {
      // don't auto-clear; let user decide
    }, 1000);
  }
}

function onKeyDown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') doScan();
}

/* ── Clear ── */
function clearAll() {
  inputText.value = '';
  onInput();
  resultCard.classList.add('hidden');
  errorPanel.classList.add('hidden');
  skeletonCard.classList.add('hidden');
  hideMiniVerdict();
  hasResult = false;
  document.title = 'TruthScan — AI Fake News Detector';
  inputText.focus();
}

/* ── Main scan function ── */
async function doScan() {
  const text = inputText.value.trim();
  if (text.length < 10) return;

  setLoading(true);
  resultCard.classList.add('hidden');
  errorPanel.classList.add('hidden');
  skeletonCard.classList.remove('hidden');

  // Scroll to skeleton
  setTimeout(() => skeletonCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 60);

  try {
    const res  = await fetch('/api/predict', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text, source_type: sourceType }),
    });
    const data = await res.json();
    if (!res.ok) { showError(data.error || `Server error ${res.status}`); return; }
    renderResult(data);
  } catch {
    showError('Cannot reach the server. Make sure app.py is running on localhost.');
  } finally {
    setLoading(false);
    skeletonCard.classList.add('hidden');
  }
}

/* ── Render result ── */
function renderResult(d) {
  const isReal = d.verdict === 'REAL';
  hasResult = true;

  /* Page title update */
  document.title = isReal
    ? `✓ Real — TruthScan`
    : `✗ Fake — TruthScan`;

  /* Mini verdict bar */
  showMiniVerdict(isReal);

  /* Verdict strip */
  const strip = $('rcVerdict');
  strip.className = 'rc-verdict ' + (isReal ? 'vr-real' : 'vr-fake');
  $('rcvIcon').textContent  = isReal ? '✓' : '✗';
  $('rcvLabel').textContent = isReal ? 'Real News' : 'Fake News';
  $('rcvMeta').textContent  = `${d.word_count} words · via BERT`;
  $('rcvBadge').textContent = isReal ? 'Verified' : 'Suspicious';

  /* Gauge */
  const pct      = isReal ? d.real_pct : d.fake_pct;
  const arcColor = isReal ? '#10b981' : '#ef4444';
  const fill     = $('gaugeFill');
  fill.setAttribute('stroke', arcColor);
  $('goPct').textContent = pct + '%';
  $('goPct').style.color = arcColor;
  $('goLbl').textContent = isReal ? 'REAL' : 'FAKE';

  // Animate gauge arc (277 = full arc length)
  fill.style.transition = 'none';
  fill.setAttribute('stroke-dashoffset', '277');
  const offset = 277 - (pct / 100) * 277;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      fill.style.transition = 'stroke-dashoffset 1.1s cubic-bezier(0.16,1,0.3,1)';
      fill.setAttribute('stroke-dashoffset', String(offset));
    });
  });

  /* Bars */
  $('realPct').textContent = d.real_pct + '%';
  $('fakePct').textContent = d.fake_pct + '%';
  $('realBar').style.width = '0%';
  $('fakeBar').style.width = '0%';

  /* Confidence note */
  $('rcConfNote').textContent = confInterpretation(d.confidence, isReal);

  /* Show card with entrance animation */
  resultCard.classList.remove('hidden');
  resultCard.classList.remove('entering');
  void resultCard.offsetWidth; // force reflow
  resultCard.classList.add('entering');

  setTimeout(() => resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 80);

  /* Animate bars after short delay */
  setTimeout(() => {
    $('realBar').style.width = d.real_pct + '%';
    $('fakeBar').style.width = d.fake_pct + '%';
  }, 150);

  /* Signals */
  const sigSec = $('signalSec');
  const sigTags = $('sigTags');
  if (d.signals && d.signals.length) {
    $('sigCount').textContent = d.signals.length;
    sigTags.innerHTML = d.signals.map((s, i) =>
      `<span class="rc-tag" style="animation-delay:${i * 0.06}s">
        <svg width="9" height="9" viewBox="0 0 9 9" fill="none" style="flex-shrink:0">
          <circle cx="4.5" cy="4.5" r="3.5" stroke="currentColor" stroke-width="1.2"/>
          <path d="M4.5 2.5v2.5M4.5 6.5v.2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
        </svg>
        ${esc(s)}
      </span>`
    ).join('');
    sigSec.classList.remove('hidden');
  } else {
    sigSec.classList.add('hidden');
  }

  /* Models — staggered entrance */
  $('rcModels').innerHTML = Object.entries(d.per_model).map(([name, v], i) => {
    const abbr = MODEL_ABBR[name] || name.slice(0, 2).toUpperCase();
    const mc   = v === 'REAL' ? 'mr' : 'mf';
    const vc   = v === 'REAL' ? 'rv' : 'fv';
    return `<div class="rc-model ${mc}" style="
        opacity:0;
        transform:translateY(12px);
        animation: modelIn 0.4s cubic-bezier(0.16,1,0.3,1) both;
        animation-delay:${0.05 + i * 0.07}s
      ">
      <style>.rc-model { animation-fill-mode: both; }
      @keyframes modelIn { to { opacity:1; transform:translateY(0); } }</style>
      <div class="rc-mod-chip">${esc(abbr)}</div>
      <div class="rc-mod-info">
        <span class="rc-mod-name">${esc(name)}</span>
        <span class="rc-mod-verdict ${vc}">${esc(v)}</span>
      </div>
    </div>`;
  }).join('');

  /* Meta chips — no Confidence chip */
  $('rcMeta').innerHTML = [
    ['Words',   d.word_count,      ''],
    ['Primary', 'BERT',            ''],
    ['Real',    d.real_pct + '%',  'rv'],
    ['Fake',    d.fake_pct + '%',  'fv'],
  ].map(([k, v, cls]) => `
    <div class="rc-chip">
      <span class="rc-chip-k">${esc(k)}</span>
      <span class="rc-chip-v ${cls}">${esc(String(v))}</span>
    </div>`).join('');
}

/* ── Mini verdict bar ── */
function showMiniVerdict(isReal) {
  miniVerdict.className = 'mini-verdict ' + (isReal ? 'mv-real' : 'mv-fake');
  $('mvIcon').textContent  = isReal ? '✓' : '✗';
  $('mvLabel').textContent = isReal ? 'Real News' : 'Fake News';
  $('mvConf').textContent  = '';
  miniVerdict.classList.remove('hidden');
  mainHeader.classList.add('pushed');

  // Reveal with slight delay
  requestAnimationFrame(() => {
    requestAnimationFrame(() => miniVerdict.classList.add('show'));
  });
}

function hideMiniVerdict() {
  miniVerdict.classList.remove('show');
  mainHeader.classList.remove('pushed');
  setTimeout(() => miniVerdict.classList.add('hidden'), 420);
}

/* ── Confidence interpretation ── */
function confInterpretation(conf, isReal) {
  if (conf >= 90) return isReal ? '✦ Very high confidence — strong real indicators' : '✦ Very high confidence — strong fake indicators';
  if (conf >= 75) return isReal ? '◈ High confidence — likely authentic' : '◈ High confidence — likely fabricated';
  if (conf >= 60) return '◇ Moderate confidence — review signals carefully';
  return '○ Low confidence — borderline case, verify independently';
}

/* ── Loading state ── */
function setLoading(on) {
  scanBtn.disabled = on;
  scanLabel.textContent = on ? 'Analysing…' : 'Analyse';
  scanBtn.classList.toggle('scanning', on);
}

/* ── Error ── */
function showError(msg) {
  $('errMsg').textContent = msg;
  errorPanel.classList.remove('hidden');
  skeletonCard.classList.add('hidden');
  errorPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ── Escape HTML ── */
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ── Scroll: hide mini verdict when back at top ── */
window.addEventListener('scroll', () => {
  if (!hasResult) return;
  const scanner = document.getElementById('scannerSection');
  if (!scanner) return;
  const rect = scanner.getBoundingClientRect();
  if (rect.top > window.innerHeight * 0.6) {
    hideMiniVerdict();
  }
});

/* ── Init focus ── */
inputText.focus();